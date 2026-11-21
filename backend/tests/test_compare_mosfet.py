from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import part, reqs

ORIGINAL = part("mosfet")


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_threshold_above_gate_drive_is_no_safe_match():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", specs={"vgs_th_max_v": 4.0}), reqs(req_vgs_v=3.3))
    assert check(c, "vgs_th_max_v").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_no_gate_drive_skips_threshold_check():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", specs={"vgs_th_max_v": 4.0}), reqs())
    assert check(c, "vgs_th_max_v").result.value == "skip"
    assert suggest_verdict(c) == "drop_in"


def test_rds_on_double_is_caveat():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", specs={"rds_on_ohm": 4.0}), reqs())
    assert check(c, "rds_on_ohm").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_rds_on_four_times_fails():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", specs={"rds_on_ohm": 8.0}), reqs())
    assert check(c, "rds_on_ohm").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_n_vs_p_is_no_safe_match():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", polarity="p"), reqs())
    assert check(c, "polarity").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_vds_below_line_requirement_fails():
    c = evaluate_pair(ORIGINAL, part("mosfet", "B", specs={"vds_max_v": 30}), reqs(req_vds_v=60))
    assert check(c, "vds_max_v").result.value == "fail"
