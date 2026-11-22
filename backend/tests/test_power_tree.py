import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.power_tree import PowerTreeRequest, propose
from partfactory import install_catalog, part


def request(vin, *rails):
    return PowerTreeRequest(input_voltage_v=vin, rails=[{"voltage_v": v, "current_a": i} for v, i in rails])


def ldo(mpn="TST-LDO33", **specs):
    return part("ldo", mpn, specs=specs)


def buck(mpn="TST-BUCK", vout=3.3, efficiency=None, **specs):
    return part("buck", mpn, specs={"vout_v": vout, "efficiency": efficiency, **specs})


def test_ldo_arithmetic(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [ldo()])
    result = propose(request(5.0, (3.3, 0.2)))
    [option] = result["options"]
    [stage] = option["stages"]
    assert stage["mpn"] == "TST-LDO33"
    assert stage["loss_w"] == pytest.approx((5.0 - 3.3) * 0.2)
    assert stage["efficiency"] == pytest.approx(3.3 / 5.0)
    assert option["total_loss_w"] == pytest.approx(0.34)
    assert option["efficiency"] == pytest.approx(0.66)
    assert option["complete"] is True


def test_ldo_rejected_without_dropout_headroom(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [ldo(dropout_v=0.5)])
    result = propose(request(3.6, (3.3, 0.1)))
    assert result["options"] == []
    assert result["unserved"][0]["rail"] == "3.3 V"


def test_unknown_dropout_is_not_a_pass(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [ldo(dropout_v=None)])
    assert propose(request(5.0, (3.3, 0.1)))["options"] == []


def test_ldo_cannot_take_24v_and_current_limit_holds(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [ldo()])
    assert propose(request(24.0, (3.3, 0.1)))["options"] == []
    assert propose(request(5.0, (3.3, 0.3)))["options"] == []


def test_buck_without_efficiency_ranked_last_and_not_assumed(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [ldo(vin_max_v=6.0), buck("TST-BUCK-A", efficiency=None), buck("TST-BUCK-B", efficiency=0.8)])
    options = propose(request(5.0, (3.3, 0.2)))["options"]
    assert [o["stages"][0]["mpn"] for o in options] == ["TST-BUCK-B", "TST-LDO33", "TST-BUCK-A"]
    known = options[0]["stages"][0]
    assert known["loss_w"] == pytest.approx(3.3 * 0.2 * (1 / 0.8 - 1))
    unknown = options[2]
    assert unknown["stages"][0]["loss_w"] is None
    assert unknown["stages"][0]["efficiency"] is None
    assert unknown["total_loss_w"] is None
    assert unknown["efficiency"] is None
    assert "efficiency not in catalog" in unknown["stages"][0]["note"]


def test_cascade_adds_downstream_current_to_upstream_rail(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [buck("TST-BUCK5", vout=5.0, efficiency=0.9), ldo()])
    options = propose(request(12.0, (5.0, 0.1), (3.3, 0.2)))["options"]
    [option] = options
    by_rail = {s["rail"]: s for s in option["stages"]}
    assert by_rail["3.3 V"]["source"] == "5 V"
    assert by_rail["3.3 V"]["loss_w"] == pytest.approx(1.7 * 0.2)
    assert by_rail["5 V"]["load_a"] == pytest.approx(0.3)
    assert by_rail["5 V"]["loss_w"] == pytest.approx(5.0 * 0.3 * (1 / 0.9 - 1))
    assert option["part_count"] == 2


def test_cascade_rejected_when_upstream_current_exceeds_rating(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [buck("TST-BUCK5", vout=5.0, efficiency=0.9, iout_max_a=0.25), ldo()])
    result = propose(request(12.0, (5.0, 0.1), (3.3, 0.2)))
    assert all(s["mpn"] is None or s["rail"] != "5 V" for o in result["options"] for s in o["stages"])


def test_ranked_by_total_loss_and_capped_at_three(tmp_path, monkeypatch):
    parts = [buck(f"TST-BUCK-{e}", efficiency=e / 100) for e in (70, 95, 80, 90)]
    install_catalog(tmp_path, monkeypatch, parts)
    options = propose(request(12.0, (3.3, 0.5)))["options"]
    assert [o["stages"][0]["mpn"] for o in options] == ["TST-BUCK-95", "TST-BUCK-90", "TST-BUCK-80"]


def test_rail_with_no_catalog_part_is_reported(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [buck(efficiency=None)])
    result = propose(request(24.0, (5.0, 0.5), (3.3, 0.2)))
    assert result["unserved"][0]["rail"] == "5 V"
    [option] = result["options"]
    assert option["complete"] is False
    assert {s["rail"]: s["mpn"] for s in option["stages"]} == {"5 V": None, "3.3 V": "TST-BUCK"}


def test_synthetic_parts_excluded(tmp_path, monkeypatch):
    install_catalog(tmp_path, monkeypatch, [part("ldo", "SYN-LDO33", synthetic=True)])
    assert propose(request(5.0, (3.3, 0.1)))["options"] == []


def test_at_most_three_rails():
    with pytest.raises(ValidationError):
        request(24.0, (5, 0.1), (3.3, 0.1), (1.8, 0.1), (1.2, 0.1))


def test_api_demo_rails_return_renderable_options():
    response = TestClient(app).post("/api/power-tree", json={
        "input_voltage_v": 24, "rails": [{"voltage_v": 5, "current_a": 0.5}, {"voltage_v": 3.3, "current_a": 0.2}],
    })
    assert response.status_code == 200
    body = response.json()
    assert body["options"]
    for option in body["options"]:
        assert option["stages"] and all("rail" in s and "mpn" in s for s in option["stages"])
