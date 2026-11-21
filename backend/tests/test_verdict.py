import pytest

from app.schemas import Check, Comparison, DesignContext
from app.verdict import is_more_permissive, rank_candidates, suggest_verdict
from partfactory import install_catalog, part


def comparison(mpn, *checks):
    return Comparison(
        original_mpn="ORIG", candidate_mpn=mpn, category="schottky", suggested_verdict="drop_in", headline_match=True,
        checks=[Check(spec=f"s{i}", result=r, on_fail=f, on_unknown=u) for i, (r, f, u) in enumerate(checks)],
    )


@pytest.mark.parametrize("checks,expected", [
    ([("pass", "no_safe_match", "no_safe_match")], "drop_in"),
    ([("skip", "no_safe_match", "no_safe_match")], "drop_in"),
    ([("caveat", None, "caveat")], "drop_in_with_caveats"),
    ([("unknown", None, "caveat")], "drop_in_with_caveats"),
    ([("fail", "needs_redesign", "no_safe_match"), ("caveat", None, "caveat")], "needs_redesign"),
    ([("unknown", "no_safe_match", "no_safe_match"), ("fail", "needs_redesign", "no_safe_match")], "no_safe_match"),
    ([("fail", "no_safe_match", "no_safe_match"), ("fail", "needs_redesign", "no_safe_match")], "no_safe_match"),
])
def test_suggest_verdict_precedence(checks, expected):
    assert suggest_verdict(comparison("X", *checks)) == expected


def test_is_more_permissive():
    assert is_more_permissive("drop_in", "needs_redesign") is True
    assert is_more_permissive("needs_redesign", "drop_in") is False
    assert is_more_permissive("drop_in", "drop_in") is False


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [
        part("schottky", "A-OTHER", manufacturer="Other Inc", unit_price_usd=0.05, lead_time_weeks=20),
        part("schottky", "Z-DIODES", manufacturer="Diodes Incorporated", unit_price_usd=0.10, lead_time_weeks=2),
        part("schottky", "M-CAVEAT", manufacturer="Diodes Incorporated"),
    ])


def test_drop_in_ranks_ahead_of_caveat(catalog):
    ranked = rank_candidates([comparison("M-CAVEAT", ("caveat", None, "caveat")), comparison("A-OTHER")], DesignContext())
    assert [c.candidate_mpn for c in ranked] == ["A-OTHER", "M-CAVEAT"]


def test_preferred_manufacturer_first_among_equals(catalog):
    ranked = rank_candidates([comparison("A-OTHER"), comparison("Z-DIODES")], DesignContext())
    assert [c.candidate_mpn for c in ranked] == ["Z-DIODES", "A-OTHER"]


def test_fewer_caveats_first_for_lowest_risk(catalog):
    two = comparison("Z-DIODES", ("caveat", None, "caveat"), ("unknown", None, "caveat"))
    one = comparison("A-OTHER", ("caveat", None, "caveat"))
    assert [c.candidate_mpn for c in rank_candidates([two, one], DesignContext())] == ["A-OTHER", "Z-DIODES"]


def test_cost_and_lead_time_goals(catalog):
    cs = [comparison("Z-DIODES"), comparison("A-OTHER"), comparison("M-CAVEAT")]
    assert [c.candidate_mpn for c in rank_candidates(cs, DesignContext(goal="lowest_cost"))] == ["A-OTHER", "Z-DIODES", "M-CAVEAT"]
    assert [c.candidate_mpn for c in rank_candidates(cs, DesignContext(goal="shortest_lead_time"))] == ["Z-DIODES", "A-OTHER", "M-CAVEAT"]


def test_verdict_beats_goal(catalog):
    cheap_but_bad = comparison("A-OTHER", ("fail", "no_safe_match", "no_safe_match"))
    ranked = rank_candidates([cheap_but_bad, comparison("Z-DIODES")], DesignContext(goal="lowest_cost"))
    assert ranked[0].candidate_mpn == "Z-DIODES"
