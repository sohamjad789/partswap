import pytest

from app.units import format_quantity, parse_quantity, parse_range


@pytest.mark.parametrize("text", ["3.3V", "3300 mV", "3V3", "3.3 V"])
def test_voltage_notations_agree(text):
    q = parse_quantity(text)
    assert q.unit == "V" and q.value == pytest.approx(3.3)


@pytest.mark.parametrize("text", ["1.5 A", "1500mA", "1A5"])
def test_current_notations_agree(text):
    q = parse_quantity(text)
    assert q.unit == "A" and q.value == pytest.approx(1.5)


@pytest.mark.parametrize("text", ["2.2µA", "2.2uA", "2.2 μA"])
def test_micro_sign_and_greek_mu(text):
    q = parse_quantity(text)
    assert q.unit == "A" and q.value == pytest.approx(2.2e-6)


@pytest.mark.parametrize("text,value,unit", [
    ("4k7", 4700, "ohm"),
    ("65mΩ", 0.065, "ohm"),
    ("1.2 MHz", 1.2e6, "Hz"),
    ("15pF", 15e-12, "F"),
    ("8kV", 8000, "V"),
    ("±20 V", 20, "V"),
    ("-40 °C", -40, "C"),
    ("+125°C", 125, "C"),
    ("500mA", 0.5, "A"),
])
def test_other_units(text, value, unit):
    q = parse_quantity(text)
    assert q.unit == unit and q.value == pytest.approx(value)


def test_bare_number_has_no_unit():
    q = parse_quantity(" 32 ")
    assert q.unit == "" and q.value == 32


def test_milli_is_not_mega():
    assert parse_quantity("1 mΩ").value == pytest.approx(1e-3)
    assert parse_quantity("1 MΩ").value == pytest.approx(1e6)


@pytest.mark.parametrize("text", ["-40 to 125°C", "-40°C ~ +125°C", "−40 to +125 °C"])
def test_ranges(text):
    assert parse_range(text) == (-40, 125)


@pytest.mark.parametrize("text", ["abc", "", "3.3 X", "V3", "12..5"])
def test_garbage_raises(text):
    with pytest.raises(ValueError):
        parse_quantity(text)


def test_range_garbage_raises():
    with pytest.raises(ValueError):
        parse_range("hot")


@pytest.mark.parametrize("value,key,text", [
    (32, "vrrm_v", "32 V"),
    (0.15, "iout_a", "150 mA"),
    (2e-5, "ir_a", "20 µA"),
    (0.065, "rds_on_ohm", "65 mΩ"),
    (1.1e6, "fsw_hz", "1.1 MHz"),
    (-40, "temp_min_c", "-40 °C"),
    (15, "c_pf", "15 pF"),
    (8, "esd_contact_kv", "8 kV"),
    (1.7, "dropout_v", "1.7 V"),
])
def test_format_quantity(value, key, text):
    assert format_quantity(value, key) == text
