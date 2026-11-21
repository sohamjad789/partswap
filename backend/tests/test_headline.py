from app.compare import evaluate_pair
from app.headline import headline_match
from app.verdict import suggest_verdict
from partfactory import part, pins, reqs


def test_twenty_volt_schottky_on_32_volt_line_is_a_trap():
    original, candidate = part("schottky"), part("schottky", "B", specs={"vrrm_v": 20})
    assert headline_match(original, candidate) is True
    c = evaluate_pair(original, candidate, reqs(req_vrrm_v=32))
    assert c.headline_match is True
    assert suggest_verdict(c) == "no_safe_match"


def test_pin_swapped_ldo_is_a_trap():
    original = part("ldo")
    candidate = part("ldo", "B", pinout=pins("power_in", "power_out", "ground"))
    assert headline_match(original, candidate) is True
    assert suggest_verdict(evaluate_pair(original, candidate, reqs(req_vout_v=3.3))) == "needs_redesign"


def test_different_package_is_not_a_headline_match():
    assert headline_match(part("schottky"), part("schottky", "B", package={"code": "SMA", "pins": 2})) is False


def test_null_in_a_read_field_is_false():
    assert headline_match(part("schottky"), part("schottky", "B", specs={"if_avg_a": None})) is False


def test_schottky_current_at_eighty_percent_is_enough():
    assert headline_match(part("schottky"), part("schottky", "B", specs={"if_avg_a": 0.4})) is True
    assert headline_match(part("schottky"), part("schottky", "B", specs={"if_avg_a": 0.35})) is False


def test_mosfet_ignores_threshold_and_pinout():
    candidate = part("mosfet", "B", specs={"vgs_th_max_v": 4}, pinout=pins("drain", "source", "gate"))
    assert headline_match(part("mosfet"), candidate) is True


def test_esd_ignores_direction():
    assert headline_match(part("esd"), part("esd", "B", polarity="bidirectional", specs={"c_pf": 500})) is True


def test_buck_and_ldo_rules():
    assert headline_match(part("buck"), part("buck", "B", specs={"vin_max_v": 30})) is False
    assert headline_match(part("ldo"), part("ldo", "B", specs={"vout_v": 3.0})) is False


def test_different_category_is_false():
    assert headline_match(part("schottky"), part("esd", "B", package={"code": "SOD-123", "pins": 2})) is False
