import pytest

from app.bom import parse_bom

HEADER = ("ref,manufacturer,mpn,qty,description,req_vin_max_v,req_vout_v,req_iout_a,req_temp_min_c,req_temp_max_c,"
          "req_vrrm_v,req_vds_v,req_vgs_v,req_vrwm_v,req_headroom_vin_v,req_esd_contact_kv,req_c_max_pf")
EXAMPLE = (HEADER + "\n"
           "D1,onsemi,MBR0540T1G,1,Reverse-polarity Schottky on the 24 V input,,,0.5,,,32,,,,,,\n"
           "U2,Microchip,MCP1700-3302E/TT,1,3.3 V LDO for the MCU fed from the 5 V rail,5.5,3.3,0.15,,,,,,,5,,\n")


@pytest.fixture(autouse=True)
def empty_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTSWAP_DATA_DIR", str(tmp_path))


def ok(text):
    lines, errors = parse_bom(text)
    assert errors == []
    return lines


def bad(text):
    lines, errors = parse_bom(text)
    assert lines == [] and errors
    return errors


def test_plan_example():
    d1, u2 = ok(EXAMPLE)
    assert d1.ref == "D1" and d1.req_vrrm_v == 32 and d1.req_iout_a == 0.5 and d1.req_vout_v is None
    assert u2.mpn == "MCP1700-3302E/TT" and u2.req_headroom_vin_v == 5 and u2.req_vin_max_v == 5.5


def test_header_case_and_spaces():
    (line,) = ok(" Ref , Manufacturer,MPN, QTY\nD1,onsemi,X1,2\n")
    assert line.mpn == "X1" and line.qty == 2 and line.description == ""


def test_missing_description_column():
    (line,) = ok("ref,manufacturer,mpn,qty,req_vrrm_v\nD1,onsemi,X1,1,32\n")
    assert line.req_vrrm_v == 32


@pytest.mark.parametrize("cell,column,value", [
    ("3V3", "req_vout_v", 3.3),
    ("3300mV", "req_vout_v", 3.3),
    ("500mA", "req_iout_a", 0.5),
    ("8kV", "req_esd_contact_kv", 8),
    ("15pF", "req_c_max_pf", 15),
    ("−40", "req_temp_min_c", -40),
    ("8", "req_esd_contact_kv", 8),
])
def test_requirement_cells_convert_to_column_unit(cell, column, value):
    (line,) = ok(f"ref,manufacturer,mpn,qty,{column}\nD1,m,X1,1,{cell}\n")
    assert getattr(line, column) == pytest.approx(value)


def test_bom_mark_ignored():
    assert ok("\ufeff" + EXAMPLE)[0].ref == "D1"


def test_extra_column_ignored():
    (line,) = ok("ref,manufacturer,mpn,qty,notes\nD1,m,X1,1,whatever\n")
    assert line.ref == "D1"


def test_blank_lines_skipped():
    assert len(ok(EXAMPLE + "\n\n")) == 2


def test_quoted_description_with_comma():
    (line,) = ok('ref,manufacturer,mpn,qty,description\nD1,m,X1,1,"Schottky, input"\n')
    assert line.description == "Schottky, input"


def test_empty_file():
    assert bad("")[0].row == 1
    bad("   \n")


def test_missing_mpn_column():
    (error,) = bad("ref,manufacturer,part,qty\nD1,m,X1,1\n")
    assert error.row == 1 and "mpn" in error.message


def test_semicolon_file():
    bad("ref;manufacturer;mpn;qty\nD1;m;X1;1\n")


@pytest.mark.parametrize("row", ["D1,m,,1", "D1,m,X1,0", "D1,m,X1,two", "D1,m,X1,1.5", ",m,X1,1"])
def test_bad_cells(row):
    (error,) = bad(f"ref,manufacturer,mpn,qty\n{row}\n")
    assert error.row == 2


def test_duplicate_ref():
    (error,) = bad("ref,manufacturer,mpn,qty\nD1,m,X1,1\nD1,m,X2,1\n")
    assert error.row == 3 and "D1" in error.message


def test_wrong_field_count():
    (error,) = bad(EXAMPLE + "D2,onsemi,X,1,desc,,,,,,,,,,,\n")
    assert error.row == 4


def test_unparseable_requirement():
    (error,) = bad("ref,manufacturer,mpn,qty,req_vrrm_v\nD1,m,X1,1,lots\n")
    assert error.row == 2 and "req_vrrm_v" in error.message


def test_wrong_unit_in_requirement():
    bad("ref,manufacturer,mpn,qty,req_vrrm_v\nD1,m,X1,1,5A\n")


def test_errors_are_collected_across_rows():
    errors = bad("ref,manufacturer,mpn,qty\nD1,m,X1,0\nD2,m,,1\n")
    assert [e.row for e in errors] == [2, 3]


def test_mpn_takes_catalog_spelling(tmp_path, monkeypatch):
    from partfactory import install_catalog, part
    install_catalog(tmp_path, monkeypatch, [part("ldo", "MCP1700-3302E/TT")])
    (line,) = ok("ref,manufacturer,mpn,qty\nU2,Microchip,mcp1700-3302e/tt,1\n")
    assert line.mpn == "MCP1700-3302E/TT"


def test_unknown_mpn_is_not_an_error():
    (line,) = ok("ref,manufacturer,mpn,qty\nU9,Acme,ZZZ999,1\n")
    assert line.mpn == "ZZZ999"
