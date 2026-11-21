import json

import pytest

from app.excerpts import excerpt_for
from partfactory import install_catalog


@pytest.fixture(autouse=True)
def excerpts(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [])
    (tmp_path / "excerpts").mkdir()
    chunks = [
        {"page": 1, "text": "Features. Low dropout."},
        {"page": 1, "text": "Pin description: pin 1 GND, pin 2 OUT, pin 3 IN. Pinout SOT23R."},
        {"page": 4, "text": "Application information: use a 1 µF ceramic capacitor; stability needs ESR below 1 Ω."},
        {"page": 5, "text": "Layout: place the capacitor close to the pin." + " x" * 1000},
    ]
    (tmp_path / "excerpts" / "AP7333-33SRG-7.json").write_text(json.dumps({"mpn": "AP7333-33SRG-7", "chunks": chunks}))
    (tmp_path / "excerpts" / "MCP1700-3302E_TT.json").write_text(json.dumps({"mpn": "MCP1700-3302E/TT", "chunks": chunks[:1]}))


def test_top_chunks_by_keyword_count():
    result = excerpt_for("AP7333-33SRG-7", "application")
    assert result["mpn"] == "AP7333-33SRG-7" and result["topic"] == "application"
    assert [c["page"] for c in result["chunks"]] == [4, 5]


def test_total_length_capped():
    result = excerpt_for("AP7333-33SRG-7", "application")
    assert len(result["chunks"]) <= 2
    assert sum(len(c["text"]) for c in result["chunks"]) <= 1500


def test_pinout_topic():
    assert excerpt_for("AP7333-33SRG-7", "pinout")["chunks"][0]["page"] == 1


def test_no_file_or_no_match_is_no_excerpt():
    assert excerpt_for("NOPE", "pinout") == {"error": "no_excerpt"}
    assert excerpt_for("MCP1700-3302E/TT", "thermal") == {"error": "no_excerpt"}


def test_case_insensitive_mpn_and_slash_in_filename():
    assert "error" not in excerpt_for("ap7333-33srg-7", "pinout")
    assert excerpt_for("MCP1700-3302E/TT", "pinout") == {"error": "no_excerpt"}


def test_unknown_topic():
    assert excerpt_for("AP7333-33SRG-7", "colour") == {"error": "unknown_topic"}
