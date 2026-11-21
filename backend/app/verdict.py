"""Verdict floor and candidate ranking (PLAN.md section 4.6)."""

from typing import Iterable, Optional

from app.catalog import load_part
from app.schemas import VERDICT_ORDER, Check, CheckResult, Comparison, DesignContext, Goal, Verdict


def verdict_from_checks(checks: Iterable[Check]) -> Verdict:
    checks = list(checks)
    nsm = Verdict.no_safe_match
    if any((c.result == CheckResult.fail and c.on_fail == nsm) or (c.result == CheckResult.unknown and c.on_unknown == nsm)
           for c in checks):
        return nsm
    if any(c.result == CheckResult.fail and c.on_fail == Verdict.needs_redesign for c in checks):
        return Verdict.needs_redesign
    if any(c.result == CheckResult.caveat or (c.result == CheckResult.unknown and c.on_unknown == "caveat") for c in checks):
        return Verdict.drop_in_with_caveats
    return Verdict.drop_in


def suggest_verdict(comparison: Comparison) -> Verdict:
    return verdict_from_checks(comparison.checks)


def is_more_permissive(a: str, b: str) -> bool:
    return VERDICT_ORDER.index(Verdict(a)) < VERDICT_ORDER.index(Verdict(b))


def _risk_count(comparison: Comparison) -> int:
    return sum(c.result in (CheckResult.caveat, CheckResult.unknown) for c in comparison.checks)


def _nulls_last(value: Optional[float]) -> tuple[bool, float]:
    return (value is None, value or 0.0)


def rank_candidates(comparisons: list[Comparison], context: DesignContext) -> list[Comparison]:
    preferred = context.preferred_manufacturer.strip().lower()

    def key(c: Comparison):
        part = load_part(c.candidate_mpn)
        manufacturer = part.manufacturer.strip().lower() if part else ""
        risk = (_risk_count(c), manufacturer != preferred, c.candidate_mpn)
        goal = ()
        if context.goal == Goal.lowest_cost:
            goal = _nulls_last(part.unit_price_usd if part else None)
        elif context.goal == Goal.shortest_lead_time:
            goal = _nulls_last(part.lead_time_weeks if part else None)
        return (VERDICT_ORDER.index(suggest_verdict(c)), goal, risk)

    return sorted(comparisons, key=key)
