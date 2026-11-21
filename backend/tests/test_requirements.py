from app.requirements_build import build_requirements
from app.schemas import BomLine, DesignContext

CONTEXT = DesignContext(input_voltage_v=24, operating_temp_min_c=-40, operating_temp_max_c=85)


def line(**req):
    return BomLine(ref="U2", manufacturer="m", mpn="X", qty=1, **req)


def test_empty_temperature_inherits_context():
    r = build_requirements(line(), CONTEXT)
    assert (r.req_temp_min_c, r.req_temp_max_c) == (-40, 85)


def test_line_temperature_wins():
    r = build_requirements(line(req_temp_max_c=105), CONTEXT)
    assert (r.req_temp_min_c, r.req_temp_max_c) == (-40, 105)


def test_empty_vin_max_and_headroom_stay_null():
    r = build_requirements(line(req_vout_v=3.3), CONTEXT)
    assert r.req_vin_max_v is None and r.req_headroom_vin_v is None and r.req_vout_v == 3.3


def test_input_voltage_always_copied():
    assert build_requirements(line(), CONTEXT).input_voltage_v == 24
