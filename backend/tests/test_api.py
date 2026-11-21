import csv
import importlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app import runs
from app.export import BOM_HEADER
from app.main import app
from app.paths import repo_root
from app.schemas import Decision, validate_event

REAL_DATA = repo_root() / "data"
POLICY_FILES = ["categories.json", "package_aliases.json", "pin_functions.json", "topics.json"]


def schottky(mpn, manufacturer, vrrm):
    field = lambda value, raw: {"value": value, "raw": raw, "condition": "test", "page": 2, "table": "test"}  # noqa: E731
    return {
        "mpn": mpn,
        "manufacturer": manufacturer,
        "category": "schottky",
        "description": f"{vrrm} V 0.5 A Schottky, SOD-123",
        "datasheet_filename": None,
        "package": {"code": "SOD-123", "pins": 2, "page": 1},
        "pinout": [
            {"pin": 1, "name": "K", "functions": ["cathode"]},
            {"pin": 2, "name": "A", "functions": ["anode"]},
        ],
        "pinout_page": 1,
        "diode_count": 1,
        "verified": True,
        "synthetic": False,
        "specs": {
            "vrrm_v": field(vrrm, f"{vrrm} V"),
            "if_avg_a": field(0.5, "0.5 A"),
            "vf_v": field(0.5, "0.5 V"),
            "ir_a": field(0.00002, "20 µA"),
            "temp_min_c": field(-65, "-65 °C"),
            "temp_max_c": field(150, "150 °C"),
        },
    }


PARTS = [
    schottky("TEST-ORIG40", "onsemi", 40),
    schottky("TEST-SAFE40", "Diodes Incorporated", 40),
    schottky("TEST-TRAP20", "Diodes Incorporated", 20),
]

D1 = {"ref": "D1", "manufacturer": "onsemi", "mpn": "TEST-ORIG40", "qty": 3, "description": "Input Schottky",
      "req_vrrm_v": 32, "req_iout_a": 0.5}
UNKNOWN = {"ref": "X1", "manufacturer": "Nobody", "mpn": "ZZZ999", "qty": 1}


@pytest.fixture(scope="module", autouse=True)
def test_data_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    for name in POLICY_FILES:
        shutil.copy(REAL_DATA / name, root / name)
    (root / "fixtures").mkdir()
    shutil.copy(REAL_DATA / "fixtures" / "demo_run.json", root / "fixtures" / "demo_run.json")
    (root / "specs").mkdir()
    catalog = []
    for part in PARTS:
        (root / "specs" / f"{part['mpn']}.json").write_text(json.dumps(part), encoding="utf-8")
        catalog.append({k: part[k] for k in ("mpn", "manufacturer", "category", "description")}
                       | {"spec_file": f"specs/{part['mpn']}.json"})
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PARTSWAP_DATA_DIR", str(root))
        clear_catalog_caches()
        yield root
    clear_catalog_caches()


def clear_catalog_caches():
    try:
        catalog = importlib.import_module("app.catalog")
    except ImportError:
        return
    for obj in vars(catalog).values():
        if callable(getattr(obj, "cache_clear", None)):
            obj.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


def stream(client, body, fast=True):
    with client.stream("POST", f"/api/runs{'?fast=1' if fast else ''}", json=body) as response:
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())
    events = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        name_line, data_line = frame.split("\n")
        assert name_line.startswith("event: ") and data_line.startswith("data: ")
        event, data = name_line[len("event: "):], json.loads(data_line[len("data: "):])
        validate_event(event, data)
        events.append((event, data))
    return events


def fixture_run(client, lines=()):
    events = stream(client, {"lines": list(lines), "design_context": {}, "mode": "fixture"})
    return events, events[0][1]["run_id"]


# ---------------------------------------------------------------- BOM parsing


def test_bom_missing_mpn_column_is_400_with_row_error(client):
    pytest.importorskip("app.bom")
    response = client.post("/api/bom/parse", content="ref,manufacturer,part,qty\nD1,onsemi,X,1\n",
                           headers={"content-type": "text/csv"})
    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors and all(set(e) == {"row", "message"} and e["row"] >= 1 for e in errors)


def test_bom_demo_parses(client):
    pytest.importorskip("app.bom")
    csv_text = (REAL_DATA / "bom" / "demo_bom.csv").read_text(encoding="utf-8")
    response = client.post("/api/bom/parse", content=csv_text, headers={"content-type": "text/csv"})
    assert response.status_code == 200
    assert [line["ref"] for line in response.json()["lines"]][:2] == ["D1", "U2"]


def test_bom_non_utf8_is_400(client):
    pytest.importorskip("app.bom")
    response = client.post("/api/bom/parse", content=b"ref\xff\n", headers={"content-type": "text/csv"})
    assert response.status_code == 400


# ---------------------------------------------------------------- runs


def test_fixture_run_ends_with_run_completed_and_is_stored(client):
    events, run_id = fixture_run(client)
    assert events[0][0] == "run_started"
    assert events[-1] == ("run_completed", events[-1][1]) and events[-1][1]["run_id"] == run_id
    streamed = [Decision.model_validate(d) for e, d in events if e == "part_decision"]

    run = client.get(f"/api/runs/{run_id}").json()
    assert run["mode"] == "fixture"
    assert [Decision.model_validate(d) for d in run["decisions"]] == streamed


def test_each_fixture_run_gets_its_own_id(client):
    assert fixture_run(client)[1] != fixture_run(client)[1]


def test_deterministic_run_decides_every_line(client):
    pytest.importorskip("app.decide")
    events = stream(client, {"lines": [D1, UNKNOWN], "design_context": {}, "mode": "deterministic"})
    assert events[0] == ("run_started", {"run_id": events[0][1]["run_id"], "part_count": 2, "mode": "deterministic"})
    assert events[-1][0] == "run_completed"
    decisions = {d["ref"]: Decision.model_validate(d) for e, d in events if e == "part_decision"}
    assert set(decisions) == {"D1", "X1"}

    d1 = decisions["D1"]
    assert d1.source.value == "deterministic"
    assert d1.recommended_mpn == "TEST-SAFE40"
    assert [(r.mpn, r.headline_match) for r in d1.rejected] == [("TEST-TRAP20", True)]
    d1_tools = [d.get("tool") for e, d in events if e == "agent_step" and d["ref"] == "D1" and d["kind"] == "tool_call"]
    assert d1_tools[0] == "search_candidates" and d1_tools.count("compare_specs") == 2

    assert decisions["X1"].verdict.value == "no_safe_match"
    assert decisions["X1"].explanation == "ZZZ999 is not in the local catalog."

    run = client.get(f"/api/runs/{events[0][1]['run_id']}").json()
    assert [d["ref"] for d in run["decisions"]] == ["D1", "X1"]


def test_live_without_key_is_sse_error(client, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    events = stream(client, {"lines": [D1], "design_context": {}, "mode": "live"})
    assert events == [("error", {"message": "NVIDIA_API_KEY is not set"})]


def test_cache_mode_is_sse_error_until_phase_5b(client):
    events = stream(client, {"lines": [D1], "design_context": {}, "mode": "cache"})
    assert [e for e, _ in events] == ["error"]


def test_run_survives_restart(client):
    _, run_id = fixture_run(client)
    runs._store.clear()
    assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_unknown_run_is_404(client):
    for path in ("/api/runs/run-nope", "/api/runs/run-nope/export/bom.csv", "/api/runs/run-nope/export/risk.md",
                 "/api/runs/..%2F..%2Fcatalog/export/bom.csv"):
        assert client.get(path).status_code == 404, path


# ---------------------------------------------------------------- exports


def test_bom_export_header_and_rows(client):
    lines = [D1 | {"mpn": "MBR0540T1G"}]
    events, run_id = fixture_run(client, lines)
    response = client.get(f"/api/runs/{run_id}/export/bom.csv")
    assert response.status_code == 200
    rows = response.text.splitlines()
    assert rows[0] == ",".join(BOM_HEADER)
    assert rows[0] == "ref,qty,original_manufacturer,original_mpn,recommended_manufacturer,recommended_mpn,verdict,confidence,explanation"
    decision_count = sum(1 for e, _ in events if e == "part_decision")
    parsed = list(csv.DictReader(response.text.splitlines()))
    assert len(parsed) == decision_count
    d1 = next(r for r in parsed if r["ref"] == "D1")
    assert d1["qty"] == "3"


def test_risk_report_contains_each_ref(client):
    events, run_id = fixture_run(client)
    response = client.get(f"/api/runs/{run_id}/export/risk.md")
    assert response.status_code == 200
    text = response.text
    assert text.startswith(f"# PartSwap risk report\nRun: {run_id}\n")
    for e, d in events:
        if e == "part_decision":
            assert f"## {d['ref']}: {d['original_mpn']} → " in text
            assert f"Verdict: {d['verdict']}" in text
    assert "| Spec | Requirement | Original | Candidate | Result | Page |" in text
    assert "matches on headline specs" in text


# ---------------------------------------------------------------- parts, eval, extract


def test_unknown_part_is_404(client):
    pytest.importorskip("app.catalog")
    assert client.get("/api/parts/NOPE").status_code == 404
    assert client.get("/api/datasheets/NOPE").status_code == 404


def test_known_part_reports_datasheet_availability(client):
    pytest.importorskip("app.catalog")
    body = client.get("/api/parts/test-safe40").json()
    assert body["mpn"] == "TEST-SAFE40"
    assert body["datasheet_available"] is False
    assert client.get("/api/datasheets/TEST-SAFE40").status_code == 404


def test_eval_not_ready(client):
    assert client.get("/api/eval").json() == {"ready": False}


def test_extract_unavailable_until_phase_6(client):
    assert client.get("/api/extract/TEST-SAFE40").json() == {"available": False}
