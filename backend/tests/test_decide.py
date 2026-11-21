import pytest

from app.compare import evaluate_pair
from app.decide import build_decision, decide_deterministic
from app.requirements_build import build_requirements
from app.schemas import AgentStep, BomLine, DesignContext
from partfactory import install_catalog, part, pins

DIODES = "Diodes Incorporated"
CONTEXT = DesignContext()
D1 = BomLine(ref="D1", manufacturer="onsemi", mpn="TST-SCH40", qty=1, req_vrrm_v=32, req_iout_a=0.5)
U2 = BomLine(ref="U2", manufacturer="Microchip", mpn="TST-LDO33", qty=1, req_vin_max_v=5.5, req_vout_v=3.3,
             req_iout_a=0.15, req_headroom_vin_v=5)


@pytest.fixture(autouse=True)
def catalog(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "TST-SCH40", manufacturer="onsemi"),
        part("schottky", "SAFE40", manufacturer=DIODES, specs={"temp_max_c": 150}),
        part("schottky", "TRAP20", manufacturer=DIODES, specs={"vrrm_v": 20}),
        part("schottky", "TRAP30", manufacturer=DIODES, specs={"vrrm_v": 30}),
        part("ldo", "TST-LDO33", manufacturer="Microchip"),
        part("ldo", "LDO-SR", manufacturer=DIODES, specs={"iq_a": 55e-6}),
        part("ldo", "LDO-SA", manufacturer=DIODES, specs={"iq_a": 55e-6}, pinout=pins("power_in", "power_out", "ground")),
        part("mosfet", "ONLY-FET", manufacturer="onsemi"),
    ])


def run(line):
    events = []
    decision = decide_deterministic(line, CONTEXT, emit=lambda event, data: events.append((event, data)))
    return decision, events


def test_safe_candidate_recommended_and_traps_rejected():
    decision, events = run(D1)
    assert decision.verdict.value == "drop_in" and decision.source.value == "deterministic"
    assert decision.recommended_mpn == decision.compared_mpn == "SAFE40"
    assert decision.recommended_manufacturer == DIODES
    assert decision.model_verdict is None and decision.confidence is None and decision.tightened is False
    assert {(r.mpn, r.headline_match, r.verdict.value) for r in decision.rejected} == {
        ("TRAP20", True, "no_safe_match"), ("TRAP30", True, "no_safe_match")}
    trap20 = next(r for r in decision.rejected if r.mpn == "TRAP20")
    assert trap20.reason == "vrrm_v: candidate 20 V is below the required 32 V"
    assert sorted(decision.candidates_considered) == ["SAFE40", "TRAP20", "TRAP30"]
    assert [c.spec for c in decision.spec_checks][-2:] == ["package", "pinout"]
    assert decision.package_pinout.package_result.value == "pass"
    assert decision.explanation.startswith("Drop-in: SAFE40.")


def test_steps_emitted_like_the_live_loop():
    _, events = run(D1)
    steps = [AgentStep.model_validate(data) for event, data in events]
    assert {event for event, _ in events} == {"agent_step"}
    calls = [s for s in steps if s.kind == "tool_call"]
    assert calls[0].tool == "search_candidates"
    assert [c.arguments["candidate_mpn"] for c in calls[1:]] == ["SAFE40", "TRAP20", "TRAP30"]
    assert all(c.tool == "compare_specs" and c.arguments["ref"] == "D1" for c in calls[1:])
    results = [s for s in steps if s.kind == "tool_result" and s.tool == "compare_specs"]
    assert results[1].summary == "TRAP20: no_safe_match; 1 fail, 0 caveat"
    assert [s.step for s in steps] == list(range(1, len(steps) + 1))


def test_emit_is_optional():
    assert decide_deterministic(D1, CONTEXT).recommended_mpn == "SAFE40"


def test_caveat_line_and_pinout_trap():
    decision, _ = run(U2)
    assert decision.verdict.value == "drop_in_with_caveats"
    assert decision.recommended_mpn == "LDO-SR"
    assert any(c.startswith("iq_a: ") for c in decision.caveats)
    assert decision.explanation.startswith("Drop-in with caveats: LDO-SR. iq_a: candidate 55 µA")
    (rejected,) = decision.rejected
    assert rejected.mpn == "LDO-SA" and rejected.verdict.value == "needs_redesign" and rejected.headline_match
    assert rejected.reason.startswith("pinout: Same SOT-23-3 package. Pin 1 is ground on the original and power_in")


def test_unknown_mpn():
    decision, events = run(BomLine(ref="U9", manufacturer="Acme", mpn="ZZZ999", qty=1))
    assert decision.verdict.value == "no_safe_match"
    assert decision.compared_mpn is None and decision.recommended_mpn is None and decision.spec_checks == []
    assert decision.explanation == "ZZZ999 is not in the local catalog."
    assert decision.original_manufacturer == "Acme"


def test_empty_category():
    decision, _ = run(BomLine(ref="Q1", manufacturer="onsemi", mpn="only-fet", qty=1))
    assert decision.verdict.value == "no_safe_match" and decision.compared_mpn is None
    assert decision.original_mpn == "ONLY-FET"
    assert decision.explanation == "No candidate in the local catalog for this category."


def test_all_candidates_failing_keeps_compared_but_not_recommended():
    line = D1.model_copy(update={"req_vrrm_v": 100})
    decision, _ = run(line)
    assert decision.verdict.value == "no_safe_match"
    assert decision.compared_mpn is not None and decision.recommended_mpn is None
    assert decision.compared_mpn not in {r.mpn for r in decision.rejected}
    assert decision.explanation.startswith("No safe match: ")


def comparisons_for(line):
    original = part("schottky", "TST-SCH40", manufacturer="onsemi")
    reqs = build_requirements(line, CONTEXT)
    from app.catalog import load_part
    return [evaluate_pair(original, load_part(m), reqs) for m in ("SAFE40", "TRAP20")]


def test_build_decision_model_fields_and_confidence_cap():
    d = build_decision(D1, CONTEXT, comparisons_for(D1), "SAFE40", "drop_in_with_caveats", source="model",
                       model="nvidia/x", model_verdict="drop_in", confidence=0.95, caveats=["c1"], explanation="e",
                       tightened=True)
    assert d.confidence == 0.6 and d.tightened and d.model_verdict.value == "drop_in" and d.model == "nvidia/x"
    assert d.caveats == ["c1"] and d.explanation == "e" and d.verdict.value == "drop_in_with_caveats"
    assert [r.mpn for r in d.rejected] == ["TRAP20"]


def test_build_decision_needs_redesign_keeps_recommendation():
    d = build_decision(D1, CONTEXT, comparisons_for(D1), "SAFE40", "needs_redesign", source="model", explanation="e")
    assert d.recommended_mpn == "SAFE40"


def test_build_decision_no_safe_match_drops_recommendation():
    d = build_decision(D1, CONTEXT, comparisons_for(D1), "SAFE40", "no_safe_match", source="model", explanation="e")
    assert d.recommended_mpn is None and d.compared_mpn == "SAFE40" and d.spec_checks
