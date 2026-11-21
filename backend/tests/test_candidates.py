import pytest

from app.candidates import search_candidates
from partfactory import install_catalog, part

DIODES = "Diodes Incorporated"


@pytest.fixture(autouse=True)
def catalog(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "TST-SCH40", manufacturer="onsemi"),
        part("schottky", "A-OTHER40", manufacturer="Other Inc"),
        part("schottky", "B0540W-7-F", manufacturer=DIODES),
        part("schottky", "B0520LW-7-F", manufacturer=DIODES, specs={"vrrm_v": 20}),
        part("schottky", "C-DRAFT", manufacturer=DIODES, verified=False),
        part("schottky", "SYN-SCH-1", manufacturer=DIODES, synthetic=True),
        part("ldo", "AP7333-33SRG-7", manufacturer=DIODES),
    ])


def mpns(parts):
    return [p.mpn for p in parts]


def test_preferred_manufacturer_first_then_mpn():
    assert mpns(search_candidates("schottky", "diodes incorporated", "TST-SCH40")) == ["B0520LW-7-F", "B0540W-7-F", "A-OTHER40"]


def test_original_excluded_case_insensitively():
    assert "TST-SCH40" not in mpns(search_candidates("schottky", DIODES, "tst-sch40"))


def test_other_categories_excluded():
    assert "AP7333-33SRG-7" not in mpns(search_candidates("schottky", DIODES, "TST-SCH40"))


def test_failing_part_still_returned():
    assert "B0520LW-7-F" in mpns(search_candidates("schottky", DIODES, "TST-SCH40"))


def test_unverified_excluded():
    assert "C-DRAFT" not in mpns(search_candidates("schottky", DIODES, "TST-SCH40"))


def test_synthetic_only_on_request():
    assert "SYN-SCH-1" not in mpns(search_candidates("schottky", DIODES, "TST-SCH40"))
    assert "SYN-SCH-1" in mpns(search_candidates("schottky", DIODES, "TST-SCH40", include_synthetic=True))


def test_limit():
    assert len(search_candidates("schottky", DIODES, "TST-SCH40", limit=2)) == 2


def test_accepts_enum_category():
    from app.schemas import Category
    assert len(search_candidates(Category.schottky, DIODES, "TST-SCH40")) == 3
