from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import part, reqs

ORIGINAL = part("esd")


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_uni_vs_bidirectional_is_no_safe_match():
    c = evaluate_pair(ORIGINAL, part("esd", "B", polarity="bidirectional"), reqs())
    assert check(c, "polarity").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_capacitance_three_times_is_caveat():
    c = evaluate_pair(ORIGINAL, part("esd", "B", specs={"c_pf": 105}), reqs())
    assert check(c, "c_pf").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_capacitance_above_line_limit_is_no_safe_match():
    c = evaluate_pair(ORIGINAL, part("esd", "B", specs={"c_pf": 40}), reqs(req_c_max_pf=15))
    assert check(c, "c_pf").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_one_channel_replacing_two_is_needs_redesign():
    c = evaluate_pair(part("esd", channel_count=2), part("esd", "B", channel_count=1), reqs())
    assert check(c, "channel_count").result.value == "fail"
    assert suggest_verdict(c) == "needs_redesign"


def test_contact_rating_below_requirement_fails():
    c = evaluate_pair(ORIGINAL, part("esd", "B", specs={"esd_contact_kv": 4}), reqs(req_esd_contact_kv=8))
    assert check(c, "esd_contact_kv").result.value == "fail"
