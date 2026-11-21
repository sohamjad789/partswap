from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import MISSING, part, reqs


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_null_critical_spec_is_unknown_and_no_safe_match():
    c = evaluate_pair(part("schottky"), part("schottky", "B", specs={"vrrm_v": None}), reqs(req_vrrm_v=32))
    assert check(c, "vrrm_v").result.value == "unknown"
    assert check(c, "vrrm_v").result.value != "pass"
    assert suggest_verdict(c) == "no_safe_match"


def test_missing_secondary_spec_is_unknown_and_caveat():
    c = evaluate_pair(part("ldo"), part("ldo", "B", specs={"iq_a": MISSING}), reqs(req_vout_v=3.3))
    assert check(c, "iq_a").result.value == "unknown"
    assert check(c, "iq_a").candidate is None
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_original_value_missing_when_it_is_the_target():
    c = evaluate_pair(part("schottky", specs={"vrrm_v": None}), part("schottky", "B"), reqs())
    assert check(c, "vrrm_v").result.value == "unknown"


def test_original_value_not_needed_when_requirement_given():
    c = evaluate_pair(part("schottky", specs={"vrrm_v": None}), part("schottky", "B"), reqs(req_vrrm_v=32))
    assert check(c, "vrrm_v").result.value == "pass"


def test_null_root_value_is_unknown():
    c = evaluate_pair(part("mosfet"), part("mosfet", "B", polarity=None), reqs())
    assert check(c, "polarity").result.value == "unknown"
    assert suggest_verdict(c) == "no_safe_match"
