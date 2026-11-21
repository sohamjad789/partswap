"""BOM CSV and Markdown risk report for a finished run (PLAN.md section 4.13)."""

import csv
import io
from typing import Optional

from app.schemas import BomLine, Check, CheckResult, CheckValue, Run

BOM_HEADER = [
    "ref", "qty", "original_manufacturer", "original_mpn", "recommended_manufacturer",
    "recommended_mpn", "verdict", "confidence", "explanation",
]


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def bom_csv(run: Run, lines: list[BomLine]) -> str:
    qty_by_ref = {line.ref: line.qty for line in lines}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(BOM_HEADER)
    for d in run.decisions:
        writer.writerow([
            d.ref,
            _cell(qty_by_ref.get(d.ref)),
            d.original_manufacturer,
            d.original_mpn,
            _cell(d.recommended_manufacturer),
            _cell(d.recommended_mpn),
            d.verdict.value,
            _cell(d.confidence),
            d.explanation,
        ])
    return out.getvalue()


def _md(text: Optional[str]) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _shown(value: Optional[CheckValue]) -> str:
    if value is None:
        return ""
    if value.raw is not None:
        return value.raw
    return _cell(value.value)


def _page(check: Check) -> str:
    for side in (check.candidate, check.original):
        if side is not None and side.page is not None:
            return str(side.page)
    return ""


def risk_report(run: Run) -> str:
    ctx = run.design_context
    out = [
        "# PartSwap risk report",
        f"Run: {run.run_id}",
        f"Goal: {ctx.goal.value}",
        f"Preferred manufacturer: {ctx.preferred_manufacturer}",
    ]
    for d in run.decisions:
        out += [
            "",
            f"## {d.ref}: {d.original_mpn} → {d.recommended_mpn or 'no safe match'}",
            f"Verdict: {d.verdict.value}",
            d.explanation,
        ]
        checks = [c for c in d.spec_checks if c.result != CheckResult.skip]
        if checks:
            out += ["", "| Spec | Requirement | Original | Candidate | Result | Page |", "| --- | --- | --- | --- | --- | --- |"]
            out += [
                f"| {_md(c.spec)} | {_md(c.requirement)} | {_md(_shown(c.original))} | "
                f"{_md(_shown(c.candidate))} | {c.result.value} | {_page(c)} |"
                for c in checks
            ]
        out.append("")
        out += ["Caveats:"] + [f"- {c}" for c in d.caveats] if d.caveats else ["Caveats: none"]
        if d.rejected:
            out.append("Rejected candidates:")
            for r in d.rejected:
                label = " — matches on headline specs" if r.headline_match else ""
                out.append(f"- {r.mpn} — {r.reason}{label}")
        else:
            out.append("Rejected candidates: none")
    return "\n".join(out) + "\n"
