"""BOM CSV parsing (PLAN.md section 4.3)."""

import csv
import io

from app.catalog import load_part
from app.schemas import BomError, BomLine
from app.units import parse_quantity

REQUIRED = ("ref", "manufacturer", "mpn", "qty")
REQUIREMENT_COLUMNS = (
    "req_vin_max_v", "req_vout_v", "req_iout_a", "req_temp_min_c", "req_temp_max_c", "req_vrrm_v",
    "req_vds_v", "req_vgs_v", "req_vrwm_v", "req_headroom_vin_v", "req_esd_contact_kv", "req_c_max_pf",
)
# column suffix -> (unit parse_quantity returns, multiplier from that unit to the column's unit)
COLUMN_UNITS = {"v": ("V", 1.0), "a": ("A", 1.0), "c": ("C", 1.0), "kv": ("V", 1e-3), "pf": ("F", 1e12)}


def _requirement(column: str, cell: str) -> float:
    q = parse_quantity(cell)
    unit, scale = COLUMN_UNITS[column.rsplit("_", 1)[-1]]
    if q.unit == "":
        return q.value
    if q.unit != unit:
        raise ValueError(f"unit {q.unit} does not fit {column}")
    return float(f"{q.value * scale:.12g}")


def parse_bom(text: str) -> tuple[list[BomLine], list[BomError]]:
    text = text.lstrip("\ufeff")
    if not text.strip():
        return [], [BomError(row=1, message="The file is empty.")]

    reader = csv.reader(io.StringIO(text))
    header: list[str] | None = None
    errors: list[BomError] = []
    lines: list[BomLine] = []
    seen_refs: set[str] = set()

    for row in reader:
        row_no = reader.line_num
        if not any(cell.strip() for cell in row):
            continue
        if header is None:
            header = [h.strip().lower() for h in row]
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                return [], [BomError(row=row_no, message=f"Missing required column: {', '.join(missing)}.")]
            continue
        if len(row) != len(header):
            errors.append(BomError(row=row_no, message=f"Expected {len(header)} fields, found {len(row)}."))
            continue
        cells = {name: cell.strip() for name, cell in zip(header, row)}
        row_errors = []
        if not cells["ref"]:
            row_errors.append("ref is blank")
        if not cells["mpn"]:
            row_errors.append("mpn is blank")
        qty = cells["qty"]
        if not (qty.isdigit() and int(qty) > 0):
            row_errors.append(f"qty {qty!r} is not a positive integer")
        if cells["ref"] and cells["ref"] in seen_refs:
            row_errors.append(f"ref {cells['ref']} repeats")
        requirements = {}
        for column in REQUIREMENT_COLUMNS:
            if cells.get(column):
                try:
                    requirements[column] = _requirement(column, cells[column])
                except ValueError:
                    row_errors.append(f"{column} value {cells[column]!r} does not parse")
        if row_errors:
            errors.append(BomError(row=row_no, message="; ".join(row_errors) + "."))
            continue
        seen_refs.add(cells["ref"])
        part = load_part(cells["mpn"])
        lines.append(BomLine(
            ref=cells["ref"],
            manufacturer=cells["manufacturer"],
            mpn=part.mpn if part else cells["mpn"],
            qty=int(qty),
            description=cells.get("description", ""),
            **requirements,
        ))

    if header is None:
        return [], [BomError(row=1, message="The file is empty.")]
    if errors:
        return [], errors
    return lines, []
