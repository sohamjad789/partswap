from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import part, reqs

ORIGINAL = part("ldo")
LINE = dict(req_vin_max_v=5.5, req_vout_v=3.3, req_iout_a=0.15, req_headroom_vin_v=5, req_temp_min_c=-40, req_temp_max_c=85)


def compare(**specs):
    root = {k: specs.pop(k) for k in list(specs) if k in ("output_type",)}
    return evaluate_pair(ORIGINAL, part("ldo", "B", specs=specs, **root), reqs(**LINE))


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_identical_is_drop_in():
    assert suggest_verdict(compare()) == "drop_in"


def test_iq_three_times_is_caveat():
    c = compare(iq_a=4.8e-6)
    assert check(c, "iq_a").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_dropout_beyond_headroom_is_no_safe_match():
    c = compare(dropout_v=2.0)
    assert check(c, "dropout_v").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_dropout_slightly_worse_with_headroom_is_caveat():
    c = compare(dropout_v=0.298)
    assert check(c, "dropout_v").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_fixed_vs_adjustable_is_needs_redesign():
    c = compare(output_type="adjustable")
    assert check(c, "output_type").result.value == "fail"
    assert suggest_verdict(c) == "needs_redesign"


def test_wrong_output_voltage_is_no_safe_match():
    c = compare(vout_v=3.0)
    assert check(c, "vout_v").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_output_voltage_within_two_percent_passes():
    assert check(compare(vout_v=3.33), "vout_v").result.value == "pass"


def test_input_minimum_above_headroom_fails():
    assert check(compare(vin_min_v=5.2), "vin_min_v").result.value == "fail"


def test_line_vin_max_not_board_input():
    c = compare(vin_abs_max_v=6.0, vin_max_v=5.5)
    assert check(c, "vin_abs_max_v").result.value == "pass"
    assert check(c, "vin_max_v").result.value == "pass"
