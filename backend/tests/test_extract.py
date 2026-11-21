import json
from pathlib import Path
from types import SimpleNamespace

from app.extract import parse_api, pipeline
from app.extract.pdf_pages import page_png, page_texts
from app.extract.structure import _first_object, grounding_check


def test_grounding_keeps_matched_raw_and_drops_ungrounded_or_wrong_value():
    text = "Maximum reverse voltage: 20 V"
    fields = {
        "vrrm_v": {"value": 20, "raw": "20 V", "condition": "maximum"},
        "if_avg_a": {"value": 1, "raw": "1 A", "condition": "maximum"},
        "vf_v": {"value": 40, "raw": "20 V", "condition": "maximum"},
    }
    checked = grounding_check(fields, text)
    assert checked["vrrm_v"]["value"] == 20
    assert checked["if_avg_a"]["value"] is None
    assert checked["vf_v"]["value"] is None


def test_tolerant_json_object_parsing():
    assert _first_object("Here is the result:\n```json\n{\"vrrm_v\": {\"value\": 40}}\n```") == {
        "vrrm_v": {"value": 40}
    }
    assert _first_object("no structured result") is None


def test_coordinate_tokens_are_stripped(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"content": "<x_0.1><y_0.2>VRRM 40 V<class_Caption>"}
    monkeypatch.setenv("NVIDIA_API_KEY", "test")
    monkeypatch.setattr(parse_api.httpx, "post", lambda *args, **kwargs: Response())
    assert parse_api.parse_page(b"png") == "VRRM 40 V"


def test_parse_failure_returns_none(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test")
    monkeypatch.setattr(parse_api.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(parse_api.httpx.TimeoutException("timeout")))
    assert parse_api.parse_page(b"png") is None


def test_zero_byte_pdf_is_unreadable(tmp_path):
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"")
    assert page_texts(pdf) == []
    assert page_png(pdf, 1) == b""


def test_pipeline_handles_missing_local_pdf_without_network(monkeypatch):
    monkeypatch.setattr(pipeline, "_pdf_path", lambda mpn: None)
    assert pipeline.extract_part("B0540W-7-F") == {"error": "unreadable_pdf"}
