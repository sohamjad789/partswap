from app.compare import evaluate_pair
from app.verdict import suggest_verdict
from partfactory import part, reqs

ORIGINAL = part("schottky")


def check(comparison, spec):
    return next(c for c in comparison.checks if c.spec == spec)


def test_vrrm_below_requirement_fails():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"vrrm_v": 20}), reqs(req_vrrm_v=32))
    vrrm = check(c, "vrrm_v")
    assert vrrm.result.value == "fail"
    assert vrrm.requirement == ">= 32 V (line requirement)"
    assert vrrm.reason == "candidate 20 V is below the required 32 V"
    assert vrrm.candidate.value == 20 and vrrm.candidate.condition
    assert suggest_verdict(c) == "no_safe_match"
    assert c.suggested_verdict.value == "no_safe_match"


def test_null_requirement_compares_with_original():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"vrrm_v": 20}), reqs())
    vrrm = check(c, "vrrm_v")
    assert vrrm.result.value == "fail"
    assert "original" in vrrm.requirement


def test_vrrm_meeting_requirement_passes():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"vrrm_v": 20}), reqs(req_vrrm_v=20))
    assert check(c, "vrrm_v").result.value == "pass"


def test_identical_part_is_drop_in():
    c = evaluate_pair(ORIGINAL, part("schottky", "B"), reqs(req_vrrm_v=32, req_iout_a=0.5, req_temp_min_c=-40, req_temp_max_c=85))
    assert [ch.result.value for ch in c.checks if ch.result.value != "pass"] == []
    assert suggest_verdict(c) == "drop_in"
    assert [ch.spec for ch in c.checks][-2:] == ["package", "pinout"]


def test_vf_worse_by_point_two_is_caveat():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"vf_v": 0.71}), reqs())
    assert check(c, "vf_v").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_leakage_six_times_is_caveat():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"ir_a": 0.00012}), reqs())
    assert check(c, "ir_a").result.value == "caveat"
    assert suggest_verdict(c) == "drop_in_with_caveats"


def test_dual_diode_is_no_safe_match():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", diode_count=2), reqs())
    assert check(c, "diode_count").result.value == "fail"
    assert suggest_verdict(c) == "no_safe_match"


def test_temperature_uses_lte_for_min_and_gte_for_max():
    c = evaluate_pair(ORIGINAL, part("schottky", "B", specs={"temp_min_c": -20, "temp_max_c": 150}),
                      reqs(req_temp_min_c=-40, req_temp_max_c=85))
    assert check(c, "temp_min_c").result.value == "fail"
    assert check(c, "temp_max_c").result.value == "pass"
