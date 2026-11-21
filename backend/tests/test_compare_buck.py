import pytest

from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import part, reqs

ORIGINAL = part("buck")
LINE = dict(input_voltage_v=24, req_vin_max_v=32, req_vout_v=3.3, req_iout_a=0.5)


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_identical_is_drop_in():
    assert suggest_verdict(evaluate_pair(ORIGINAL, part("buck", "B"), reqs(**LINE))) == "drop_in"


def test_sync_vs_async_is_needs_redesign():
    c = evaluate_pair(ORIGINAL, part("buck", "B", topology="asynchronous"), reqs(**LINE))
    assert check(c, "topology").result.value == "fail"
    assert suggest_verdict(c) == "needs_redesign"


@pytest.mark.parametrize("fsw", [3.3e6, 3.6e5])
def test_switching_frequency_three_times_either_way_is_caveat(fsw):
    c = evaluate_pair(ORIGINAL, part("buck", "B", specs={"fsw_hz": fsw}), reqs(**LINE))
    assert check(c, "fsw_hz").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_adjustable_original_skips_vout():
    original = part("buck", output_type="adjustable", specs={"vout_v": None})
    candidate = part("buck", "B", output_type="adjustable", specs={"vout_v": None})
    c = evaluate_pair(original, candidate, reqs(**LINE))
    assert check(c, "vout_v").result.value == "skip"
    assert suggest_verdict(c) == "drop_in"


def test_vin_min_above_board_input_fails():
    c = evaluate_pair(ORIGINAL, part("buck", "B", specs={"vin_min_v": 30}), reqs(**LINE))
    assert check(c, "vin_min_v").result.value == "fail"
