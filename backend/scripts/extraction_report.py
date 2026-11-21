"""Measure provisional extraction fields against human-verified JSON specs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import all_parts  # noqa: E402
from app.paths import data_dir  # noqa: E402


def main() -> int:
    rows = []
    totals = {"match": 0, "mismatch": 0, "missing": 0}
    for part in all_parts():
        path = data_dir() / "specs" / "extracted" / f"{part.mpn.replace('/', '_')}.json"
        if not path.exists():
            continue
        extracted = json.loads(path.read_text()).get("specs", {})
        fields = []
        for key, verified in part.specs.items():
            actual = extracted.get(key, {})
            expected_value, actual_value = verified.value, actual.get("value")
            if actual_value is None:
                status = "missing"
            elif expected_value is not None and abs(actual_value - expected_value) <= max(abs(expected_value), 1e-12) * .02:
                status = "match"
            else:
                status = "mismatch"
            totals[status] += 1
            fields.append({"key": key, "verified_raw": verified.raw, "extracted_raw": actual.get("raw"), "status": status})
        rows.append({"mpn": part.mpn, "fields": fields})
    output = {"parts": rows, "totals": totals}
    destination = data_dir() / "eval" / "extraction_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
