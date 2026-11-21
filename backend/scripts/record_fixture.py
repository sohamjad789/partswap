"""Run the demo BOM through `runs.run_events` and write `data/fixtures/demo_run.json`.

Usage (from the repo root): python backend/scripts/record_fixture.py --mode deterministic|live
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bom import parse_bom  # noqa: E402
from app.main import demo_design_context  # noqa: E402
from app.paths import data_dir  # noqa: E402
from app.runs import run_events  # noqa: E402
from app.schemas import Decision, FixtureRun, Mode  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=[Mode.deterministic.value, Mode.live.value], required=True)
    args = parser.parse_args()

    lines, errors = parse_bom((data_dir() / "bom" / "demo_bom.csv").read_text(encoding="utf-8"))
    if errors:
        for e in errors:
            print(f"demo_bom.csv row {e.row}: {e.message}", file=sys.stderr)
        return 1

    context = demo_design_context()
    events = list(run_events(lines, context, Mode(args.mode)))
    failures = [d["message"] for e, d in events if e == "error"]
    if failures:
        print(f"Run failed: {failures[0]}", file=sys.stderr)
        return 1

    fixture = FixtureRun(
        run_id=events[0][1]["run_id"],
        mode=Mode(args.mode),
        design_context=context,
        events=[{"event": e, "data": d} for e, d in events],
        decisions=[Decision.model_validate(d) for e, d in events if e == "part_decision"],
    )
    out = data_dir() / "fixtures" / "demo_run.json"
    out.write_text(fixture.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(fixture.decisions)} decisions, {len(events)} events)")
    for d in fixture.decisions:
        print(f"  {d.ref}: {d.verdict.value} -> {d.recommended_mpn or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
