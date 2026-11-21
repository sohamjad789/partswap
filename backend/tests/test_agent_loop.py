import json

import pytest

from app import runs
from app.agent import loop
from app.agent.loop import run_part
from app.agent.prompts import SYSTEM_PROMPT
from app.schemas import AgentStep, BomLine, DesignContext, Mode, PartError
from fakes import FakeClient, call, connection_error, reply, status_error
from partfactory import install_catalog, part

DIODES = "Diodes Incorporated"
MODEL = "nvidia/test-super"
CONTEXT = DesignContext()
D1 = BomLine(ref="D1", manufacturer="onsemi", mpn="TST-SCH40", qty=1, req_vrrm_v=32, req_iout_a=0.5)
D2 = BomLine(ref="D2", manufacturer="onsemi", mpn="TST-SCH40", qty=2, req_vrrm_v=32, req_iout_a=0.5)
SEARCH = {"category": "schottky", "preferred_manufacturer": DIODES, "original_mpn": "TST-SCH40"}


@pytest.fixture(autouse=True)
def catalog(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "TST-SCH40", manufacturer="onsemi"),
        part("schottky", "SAFE40", manufacturer=DIODES, specs={"temp_max_c": 150}),
        part("schottky", "TRAP20", manufacturer=DIODES, specs={"vrrm_v": 20}),
        part("schottky", "TRAP30", manufacturer=DIODES, specs={"vrrm_v": 30}),
    ])
    monkeypatch.setattr(loop, "RETRY_WAITS_S", (0, 0, 0))


def compare(mpn):
    return call("compare_specs", {"original_mpn": "TST-SCH40", "candidate_mpn": mpn, "ref": "D1"}, id=f"cmp-{mpn}")


def record(mpn, verdict, confidence=0.9, **extra):
    return call("record_decision", {"ref": "D1", "candidate_mpn": mpn, "verdict": verdict, "confidence": confidence,
                                    "caveats": [], "explanation": f"{mpn} chosen.", **extra}, id=f"rec-{mpn}")


def search():
    return call("search_candidates", SEARCH, id="search")


def run(script, line=D1, **kwargs):
    events = []
    client = FakeClient(script)
    decision = run_part(line, CONTEXT, MODEL, lambda event, data: events.append((event, data)), client=client, **kwargs)
    return decision, events, client


def steps(events):
    return [AgentStep.model_validate(data) for event, data in events if event == "agent_step"]


def tool_messages(request):
    return [m for m in request["messages"] if m["role"] == "tool"]


def test_happy_path():
    decision, events, client = run([
        reply(search()),
        reply(compare("SAFE40"), compare("TRAP20")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model" and decision.model == MODEL
    assert decision.verdict.value == "drop_in" and decision.model_verdict.value == "drop_in"
    assert decision.recommended_mpn == decision.compared_mpn == "SAFE40"
    assert decision.tightened is False and decision.confidence == 0.9
    vrrm = next(c for c in decision.spec_checks if c.spec == "vrrm_v")
    assert vrrm.candidate.value == 40 and vrrm.result.value == "pass"
    assert {(r.mpn, r.headline_match) for r in decision.rejected} == {("TRAP20", True), ("TRAP30", True)}
    assert sorted(decision.candidates_considered) == ["SAFE40", "TRAP20", "TRAP30"]
    assert decision.explanation == "SAFE40 chosen."

    first = client.requests[0]
    assert first["model"] == MODEL and first["tools"] and first["parallel_tool_calls"] is False
    assert first["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    user = first["messages"][1]["content"]
    assert user.startswith("Verify a replacement for BOM line D1.\nLine: ")
    assert "Original part: TST-SCH40, onsemi, category schottky, package SOD-123" in user
    assert "vrrm_v" not in json.dumps(first["messages"][0])

    second = client.requests[2]["messages"]
    assistant = [i for i, m in enumerate(second) if m["role"] == "assistant"][1]
    assert [m["tool_call_id"] for m in second[assistant + 1:assistant + 3]] == ["cmp-SAFE40", "cmp-TRAP20"]

    kinds = [(s.kind, s.tool) for s in steps(events)]
    assert kinds[:2] == [("tool_call", "search_candidates"), ("tool_result", "search_candidates")]
    compare_summaries = [s.summary for s in steps(events) if s.kind == "tool_result" and s.tool == "compare_specs"]
    assert compare_summaries == ["SAFE40: drop_in; 0 fail, 0 caveat", "TRAP20: no_safe_match; 1 fail, 0 caveat"]
    assert [s.step for s in steps(events)] == list(range(1, len(steps(events)) + 1))
    assert not [e for e, _ in events if e == "part_error"]


def test_guardrail_tightens_drop_in():
    decision, events, _ = run([
        reply(search()),
        reply(compare("TRAP20")),
        reply(record("TRAP20", "drop_in", confidence=0.95, vrrm_v=40)),
    ])
    assert decision.source.value == "model"
    assert decision.verdict.value == "no_safe_match" and decision.model_verdict.value == "drop_in"
    assert decision.tightened is True and decision.confidence <= 0.6
    assert decision.compared_mpn == "TRAP20" and decision.recommended_mpn is None
    vrrm = next(c for c in decision.spec_checks if c.spec == "vrrm_v")
    assert vrrm.candidate.value == 20 and vrrm.result.value == "fail"
    caveat = "Verdict tightened by deterministic check: vrrm_v: candidate 20 V is below the required 32 V"
    assert caveat in decision.caveats
    assert any(s.kind == "guardrail" and caveat in s.text for s in steps(events))


def test_model_may_be_stricter():
    decision, _, _ = run([
        reply(search()),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in_with_caveats", confidence=0.7)),
    ])
    assert decision.verdict.value == "drop_in_with_caveats" and decision.model_verdict.value == "drop_in_with_caveats"
    assert decision.tightened is False and decision.confidence == 0.7
    assert decision.recommended_mpn == "SAFE40"


def test_unknown_candidate_rejected():
    decision, events, client = run([
        reply(search()),
        reply(record("NOPE1", "drop_in")),
        reply(record("NOPE2", "drop_in")),
    ])
    assert tool_messages(client.requests[2])[-1]["content"] == json.dumps({"error": "unknown_candidate"})
    assert decision.source.value == "deterministic_fallback"
    assert decision.recommended_mpn == "SAFE40" and decision.verdict.value == "drop_in"
    errors = [d for e, d in events if e == "part_error"]
    assert len(errors) == 1 and PartError.model_validate(errors[0]).ref == "D1"


def test_uncompared_better_candidate_nudge():
    decision, _, client = run([
        reply(search()),
        reply(compare("TRAP20")),
        reply(record("TRAP20", "no_safe_match")),
        reply(record("TRAP20", "no_safe_match")),
    ])
    nudge = json.loads(tool_messages(client.requests[3])[-1]["content"])
    assert nudge["error"] == "uncompared_candidate"
    assert nudge["message"] == "You have not compared SAFE40. Compare it before deciding."
    assert decision.source.value == "model" and decision.verdict.value == "no_safe_match"
    assert decision.compared_mpn == "TRAP20"


def test_invalid_arguments_then_fallback():
    decision, events, client = run([
        reply(search()),
        reply(call("compare_specs", "not json", id="bad1")),
        reply(call("compare_specs", "{still not json", id="bad2")),
    ])
    assert tool_messages(client.requests[2])[-1] == {"role": "tool", "tool_call_id": "bad1",
                                                     "content": json.dumps({"error": "invalid_arguments"})}
    assert decision.source.value == "deterministic_fallback"
    assert [e for e, _ in events].count("part_error") == 1


def test_unknown_tool_error():
    decision, _, client = run([
        reply(search()),
        reply(call("delete_catalog", {}, id="u1")),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert tool_messages(client.requests[2])[-1]["content"] == json.dumps({"error": "unknown_tool"})
    assert decision.source.value == "model"

    decision, _, _ = run([
        reply(search()),
        reply(call("delete_catalog", {}, id="u1")),
        reply(call("delete_catalog", {}, id="u2")),
    ])
    assert decision.source.value == "deterministic_fallback"


def test_invalid_verdict_enum():
    decision, _, client = run([
        reply(search()),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "perfect")),
        reply(record("SAFE40", "perfect")),
    ])
    assert tool_messages(client.requests[3])[-1]["content"] == json.dumps({"error": "invalid_verdict"})
    assert decision.source.value == "deterministic_fallback"
    assert decision.verdict.value in {"drop_in", "drop_in_with_caveats", "needs_redesign", "no_safe_match"}


def test_invalid_verdict_then_corrected():
    decision, _, _ = run([
        reply(search()),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "perfect")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model" and decision.verdict.value == "drop_in"


def test_content_json_recovery():
    as_text = lambda name, args: reply(content=json.dumps({"name": name, "arguments": args}))  # noqa: E731
    decision, events, client = run([
        as_text("search_candidates", SEARCH),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model"
    assert steps(events)[0].tool == "search_candidates"
    messages = client.requests[1]["messages"]
    assert messages[2]["tool_calls"][0]["id"] == messages[3]["tool_call_id"]

    decision, _, client = run([
        as_text("search_candidates", SEARCH),
        as_text("compare_specs", {"original_mpn": "TST-SCH40", "candidate_mpn": "SAFE40", "ref": "D1"}),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model"
    assert len(tool_messages(client.requests[2])) == 1


def test_empty_turn_retried_once_then_fallback():
    decision, _, _ = run([reply(search()), reply(), reply(compare("SAFE40")), reply(record("SAFE40", "drop_in"))])
    assert decision.source.value == "model"
    decision, _, _ = run([reply(search()), reply(), reply()])
    assert decision.source.value == "deterministic_fallback"


def test_timeout_continues(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    script = [connection_error()] * 4 + [
        reply(call("search_candidates", SEARCH)),
        reply(call("compare_specs", {"original_mpn": "TST-SCH40", "candidate_mpn": "SAFE40", "ref": "D2"})),
        reply(call("record_decision", {"ref": "D2", "candidate_mpn": "SAFE40", "verdict": "drop_in",
                                       "confidence": 0.8, "caveats": [], "explanation": "ok"})),
    ]
    client = FakeClient(script)
    monkeypatch.setattr("app.agent.client.make_client", lambda settings=None: client)
    events = list(runs.run_events([D1, D2], CONTEXT, Mode.live))
    names = [e for e, _ in events]
    assert names[0] == "run_started" and names[-1] == "run_completed"
    d1_error = names.index("part_error")
    assert events[d1_error][1]["ref"] == "D1" and names[d1_error + 1] == "part_decision"
    decisions = {d["ref"]: d for e, d in events if e == "part_decision"}
    assert decisions["D1"]["source"] == "deterministic_fallback"
    assert decisions["D2"]["source"] == "model" and decisions["D2"]["model"]
    assert len(client.requests) == 7
    run = runs.get_run(events[0][1]["run_id"])
    assert run.mode == Mode.live and [d.ref for d in run.decisions] == ["D1", "D2"]


def test_rate_limit_retry():
    decision, _, client = run([
        status_error(429), status_error(429), reply(search()),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model"
    assert len(client.requests) == 5


def test_bad_request_is_not_retried():
    decision, _, client = run([status_error(400)])
    assert decision.source.value == "deterministic_fallback"
    assert len(client.requests) == 1


def test_max_turns_fallback():
    specs = call("get_part_specs", {"mpn": "SAFE40"})
    decision, _, client = run([reply(specs) for _ in range(10)])
    assert decision.source.value == "deterministic_fallback"
    assert len(client.requests) == 10


def test_length_retry_disables_thinking_once():
    decision, _, client = run([
        reply(content="thinking ran out", finish_reason="length"),
        reply(search()),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    assert decision.source.value == "model"
    assert client.requests[1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_second_length_falls_back():
    decision, _, client = run([
        reply(content="thinking ran out", finish_reason="length"),
        reply(content="still thinking", finish_reason="length"),
    ])
    assert decision.source.value == "deterministic_fallback"
    assert len(client.requests) == 2


def test_line_time_budget_falls_back(monkeypatch):
    ticks = iter([0, loop.LINE_TIME_BUDGET_S + 1])
    monkeypatch.setattr(loop.time, "monotonic", lambda: next(ticks))
    decision, _, client = run([reply(search())])
    assert decision.source.value == "deterministic_fallback"
    assert client.requests == []


def test_reasoning_emitted():
    long_thought = "Checking Vrrm against the 32 V input. " * 30
    _, events, client = run([
        reply(search(), reasoning=long_thought),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    reasoning = [s for s in steps(events) if s.kind == "reasoning"]
    assert reasoning and reasoning[0].text == long_thought[:500]
    assert long_thought not in json.dumps(client.requests[-1]["messages"])


def test_too_many_calls_in_one_turn():
    calls = [call("get_part_specs", {"mpn": "SAFE40"}, id=f"g{i}") for i in range(5)]
    _, _, client = run([reply(search()), reply(*calls), reply(compare("SAFE40")), reply(record("SAFE40", "drop_in"))])
    results = tool_messages(client.requests[2])[-5:]
    assert [m["tool_call_id"] for m in results] == [f"g{i}" for i in range(5)]
    assert json.loads(results[-1]["content"]) == {"error": "too_many_calls"}
    assert "mpn" in json.loads(results[0]["content"])


def test_record_decision_runs_last_in_its_turn():
    decision, _, _ = run([reply(search()), reply(record("SAFE40", "drop_in"), compare("SAFE40"))])
    assert decision.source.value == "model" and decision.verdict.value == "drop_in"


def test_compare_specs_ignores_model_numbers():
    _, _, client = run([
        reply(search()),
        reply(call("compare_specs", {"original_mpn": "TST-SCH40", "candidate_mpn": "TRAP20", "ref": "D1",
                                     "vrrm_v": 40})),
        reply(compare("SAFE40")),
        reply(record("SAFE40", "drop_in")),
    ])
    comparison = json.loads(tool_messages(client.requests[2])[-1]["content"])
    vrrm = next(c for c in comparison["checks"] if c["spec"] == "vrrm_v")
    assert vrrm["candidate"]["value"] == 20 and comparison["suggested_verdict"] == "no_safe_match"


def test_only_candidates_restricts_search():
    decision, _, client = run([
        reply(search()),
        reply(compare("TRAP30")),
        reply(record("TRAP30", "no_safe_match")),
    ], only_candidates=["TRAP30"])
    result = json.loads(tool_messages(client.requests[1])[-1]["content"])
    assert [c["mpn"] for c in result["candidates"]] == ["TRAP30"]
    assert set(result["candidates"][0]) == {"mpn", "manufacturer", "package_code", "description"}
    assert decision.candidates_considered == ["TRAP30"] and decision.source.value == "model"


def test_unknown_original_makes_no_model_call():
    decision, _, client = run([], line=BomLine(ref="X1", manufacturer="Acme", mpn="ZZZ999", qty=1))
    assert client.requests == []
    assert decision.verdict.value == "no_safe_match" and decision.explanation == "ZZZ999 is not in the local catalog."
