from app import runs
from app.agent import client as agent_client
from app.schemas import BomLine, DesignContext, Mode
from fakes import FakeClient, call, reply
from partfactory import install_catalog, part


DIODES = "Diodes Incorporated"
LINE = BomLine(ref="D1", manufacturer="onsemi", mpn="TST-SCH40", qty=1, req_vrrm_v=32, req_iout_a=0.5)
CONTEXT = DesignContext()
MODEL = "nvidia/test-super"


def _script():
    search = call("search_candidates", {"category": "schottky", "preferred_manufacturer": DIODES,
                                         "original_mpn": "TST-SCH40"})
    compare = call("compare_specs", {"original_mpn": "TST-SCH40", "candidate_mpn": "SAFE40", "ref": "D1"})
    record = call("record_decision", {"ref": "D1", "candidate_mpn": "SAFE40", "verdict": "drop_in",
                                       "confidence": 0.9, "caveats": [], "explanation": "safe"})
    return [reply(search), reply(compare), reply(record)]


def _decisions(events):
    return [data for event, data in events if event == "part_decision"]


def test_cache_hit_replays_agent_events_without_client_call(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "TST-SCH40", manufacturer="onsemi"),
        part("schottky", "SAFE40", manufacturer=DIODES),
    ])
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NEMOTRON_SUPER_MODEL", MODEL)
    live_client = FakeClient(_script())
    monkeypatch.setattr(agent_client, "make_client", lambda settings=None: live_client)
    list(runs.run_events([LINE], CONTEXT, Mode.live))
    assert len(live_client.requests) == 3

    replay_client = FakeClient([])
    monkeypatch.setattr(agent_client, "make_client", lambda settings=None: replay_client)
    events = list(runs.run_events([LINE], CONTEXT, Mode.cache))
    assert replay_client.requests == []
    assert _decisions(events)[0]["source"] == "model"
    assert [data["tool"] for event, data in events if event == "agent_step" and data["kind"] == "tool_call"] == [
        "search_candidates", "compare_specs", "record_decision"
    ]


def test_cache_miss_for_changed_context_or_prompt_version_runs_deterministic(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "TST-SCH40", manufacturer="onsemi"),
        part("schottky", "SAFE40", manufacturer=DIODES),
    ])
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("NEMOTRON_SUPER_MODEL", MODEL)
    monkeypatch.setattr(agent_client, "make_client", lambda settings=None: FakeClient(_script()))
    list(runs.run_events([LINE], CONTEXT, Mode.live))

    changed_context = CONTEXT.model_copy(update={"input_voltage_max_v": 36})
    assert _decisions(list(runs.run_events([LINE], changed_context, Mode.cache)))[0]["source"] == "deterministic"

    monkeypatch.setattr(runs, "PROMPT_VERSION", "v-next")
    assert _decisions(list(runs.run_events([LINE], CONTEXT, Mode.cache)))[0]["source"] == "deterministic"
