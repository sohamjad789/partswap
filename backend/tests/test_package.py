import pytest

from app.compare import evaluate_pair
from app.package import check_package_pinout, normalize_package, normalize_pin_name
from app.verdict import suggest_verdict
from partfactory import part, pins, reqs


@pytest.mark.parametrize("code,expected", [
    ("SOT23R", "SOT-23-3"), ("sot-23", "SOT-23-3"), ("SOT-23-5 (DBV)", "SOT-23-5"), ("SOD 123", "SOD-123"),
    ("TSOT-23-5", "TSOT-23-5"), ("SOD-123F", "SOD-123F"),
])
def test_normalize_package(code, expected):
    assert normalize_package(code) == expected


@pytest.mark.parametrize("name,token", [
    ("NC", "nc"), ("/SHDN", "enable_active_low"), ("vin", "power_in"), ("E N", "enable_active_high"), ("XYZ", "unknown"),
])
def test_normalize_pin_name(name, token):
    assert normalize_pin_name(name) == token


def test_same_package_and_pins_pass():
    r = check_package_pinout(part("schottky"), part("schottky", "B"))
    assert r.package.result.value == "pass" and r.pinout.result.value == "pass"
    assert r.detail == "Same SOD-123 package and pin functions."


def test_diode_pins_swapped_fail():
    r = check_package_pinout(part("schottky"), part("schottky", "B", pinout=pins("anode", "cathode")))
    assert r.pinout.result.value == "fail"


def test_three_pin_swap_matches_plan_example():
    original = part("ldo", pinout=pins("ground", "power_out", "power_in"))
    candidate = part("ldo", "B", pinout=pins("power_in", "power_out", "ground"), package={"code": "SOT23R", "pins": 3})
    r = check_package_pinout(original, candidate)
    assert r.package.result.value == "pass"
    assert r.pinout.result.value == "fail"
    assert r.pinout.original == {"1": ["ground"], "2": ["power_out"], "3": ["power_in"]}
    assert r.detail == ("Same SOT-23-3 package. Pin 1 is ground on the original and power_in on the candidate; "
                        "pin 3 is power_in on the original and ground on the candidate.")


def test_sot23_5_vs_tsot_fails():
    a = part("ldo", package={"code": "SOT-23-5", "pins": 3})
    b = part("ldo", "B", package={"code": "TSOT-23-5", "pins": 3})
    r = check_package_pinout(a, b)
    assert r.package.result.value == "fail"
    assert "SOT-23-5" in r.detail and "TSOT-23-5" in r.detail


def test_unknown_token_is_unknown_and_floor_no_safe_match():
    candidate = part("schottky", "B", pinout=pins("cathode", "unknown"))
    assert check_package_pinout(part("schottky"), candidate).pinout.result.value == "unknown"
    assert suggest_verdict(evaluate_pair(part("schottky"), candidate, reqs())) == "no_safe_match"


def test_missing_pinout_is_unknown():
    assert check_package_pinout(part("schottky"), part("schottky", "B", pinout=None)).pinout.result.value == "unknown"


def test_different_pin_counts_fail():
    candidate = part("ldo", "B", pinout=pins("ground", "power_out", "power_in", "nc"))
    r = check_package_pinout(part("ldo"), candidate)
    assert r.pinout.result.value == "fail"


def test_function_sets_compare_without_order():
    a = part("schottky", pinout=[{"pin": 1, "name": "K", "functions": ["cathode", "nc"]}, {"pin": 2, "name": "A", "functions": ["anode"]}])
    b = part("schottky", "B", pinout=[{"pin": 1, "name": "K", "functions": ["nc", "cathode"]}, {"pin": 2, "name": "A", "functions": ["anode"]}])
    assert check_package_pinout(a, b).pinout.result.value == "pass"


def test_pinout_fail_is_needs_redesign():
    candidate = part("ldo", "B", pinout=pins("power_in", "power_out", "ground"))
    c = evaluate_pair(part("ldo"), candidate, reqs(req_vout_v=3.3))
    pinout = next(ch for ch in c.checks if ch.spec == "pinout")
    assert pinout.result.value == "fail" and pinout.on_fail.value == "needs_redesign"
    assert pinout.reason.startswith("Same SOT-23-3 package. Pin 1 is ground")
    assert suggest_verdict(c) == "needs_redesign"
