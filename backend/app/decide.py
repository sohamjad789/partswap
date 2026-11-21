"""Decision assembly and the deterministic pipeline (PLAN.md section 4.8)."""

import itertools
from typing import Any, Callable, Iterable, Optional

from app.candidates import search_candidates
from app.catalog import load_part
from app.compare import evaluate_pair
from app.package import check_package_pinout
from app.requirements_build import build_requirements
from app.schemas import (
    AgentStep, BomLine, Check, CheckResult, Comparison, Decision, DesignContext, PackagePinoutSummary,
    RejectedCandidate, Source, Verdict,
)
from app.verdict import rank_candidates

Emit = Callable[[str, dict[str, Any]], None]

VERDICT_LABELS = {
    Verdict.drop_in: "Drop-in",
    Verdict.drop_in_with_caveats: "Drop-in with caveats",
    Verdict.needs_redesign: "Needs redesign",
    Verdict.no_safe_match: "No safe match",
}
TIGHTENED_CONFIDENCE_CAP = 0.6


def _deciding_check(comparison: Comparison) -> Optional[Check]:
    """The first check responsible for a `needs_redesign` or `no_safe_match` floor."""
    floor = comparison.suggested_verdict
    for c in comparison.checks:
        if floor == Verdict.no_safe_match and (
            (c.result == CheckResult.fail and c.on_fail == Verdict.no_safe_match)
            or (c.result == CheckResult.unknown and c.on_unknown == Verdict.no_safe_match)
        ):
            return c
        if floor == Verdict.needs_redesign and c.result == CheckResult.fail and c.on_fail == Verdict.needs_redesign:
            return c
    return None


def _caveat_checks(comparison: Comparison) -> list[Check]:
    return [c for c in comparison.checks
            if c.result == CheckResult.caveat or (c.result == CheckResult.unknown and c.on_unknown == "caveat")]


def _describe(check: Check) -> str:
    return f"{check.spec}: {check.reason}"


def floor_reason(comparison: Comparison) -> str:
    """`"{spec}: {reason}"` of the check that sets the comparison's floor verdict."""
    deciding = _deciding_check(comparison)
    if deciding is not None:
        return _describe(deciding)
    caveats = _caveat_checks(comparison)
    return _describe(caveats[0]) if caveats else comparison.suggested_verdict.value


def build_decision(
    line: BomLine,
    context: DesignContext,
    comparisons: list[Comparison],
    compared_mpn: Optional[str],
    verdict: str,
    *,
    source: str,
    model: Optional[str] = None,
    model_verdict: Optional[str] = None,
    confidence: Optional[float] = None,
    caveats: Iterable[str] = (),
    explanation: str = "",
    tightened: bool = False,
) -> Decision:
    original = load_part(line.mpn)
    verdict = Verdict(verdict)
    compared = None
    if compared_mpn is not None:
        compared = next((c for c in comparisons if c.candidate_mpn.lower() == compared_mpn.lower()), None)
        if compared is None:
            raise ValueError(f"{compared_mpn} is not among the compared candidates")
    if compared is None:
        verdict = Verdict.no_safe_match
    candidate = load_part(compared.candidate_mpn) if compared else None

    package_pinout = None
    if original is not None and candidate is not None:
        pp = check_package_pinout(original, candidate)
        package_pinout = PackagePinoutSummary(package_result=pp.package.result, pinout_result=pp.pinout.result,
                                              detail=pp.detail)

    rejected = []
    for c in comparisons:
        if c is compared or c.suggested_verdict not in (Verdict.needs_redesign, Verdict.no_safe_match):
            continue
        part = load_part(c.candidate_mpn)
        deciding = _deciding_check(c)
        rejected.append(RejectedCandidate(
            mpn=c.candidate_mpn,
            manufacturer=part.manufacturer if part else "",
            verdict=c.suggested_verdict,
            reason=_describe(deciding) if deciding else c.suggested_verdict.value,
            headline_match=c.headline_match,
        ))

    if tightened and confidence is not None:
        confidence = min(confidence, TIGHTENED_CONFIDENCE_CAP)
    recommend = compared is not None and verdict != Verdict.no_safe_match
    return Decision(
        ref=line.ref,
        original_mpn=original.mpn if original else line.mpn,
        original_manufacturer=original.manufacturer if original else line.manufacturer,
        recommended_mpn=compared.candidate_mpn if recommend else None,
        recommended_manufacturer=candidate.manufacturer if recommend and candidate else None,
        compared_mpn=compared.candidate_mpn if compared else None,
        verdict=verdict,
        model_verdict=Verdict(model_verdict) if model_verdict is not None else None,
        tightened=tightened,
        confidence=confidence,
        source=Source(source),
        model=model,
        spec_checks=compared.checks if compared else [],
        package_pinout=package_pinout,
        caveats=list(caveats),
        explanation=explanation,
        rejected=rejected,
        candidates_considered=[c.candidate_mpn for c in comparisons],
    )


def _sentence(text: str) -> str:
    return text if text.endswith(".") else text + "."


def decide_deterministic(line: BomLine, context: DesignContext, emit: Optional[Emit] = None) -> Decision:
    counter = itertools.count(1)

    def step(**fields: Any) -> None:
        if emit is not None:
            emit("agent_step", AgentStep(ref=line.ref, step=next(counter), **fields).model_dump(mode="json", exclude_none=True))

    original = load_part(line.mpn)
    if original is None:
        return build_decision(line, context, [], None, Verdict.no_safe_match, source=Source.deterministic,
                              explanation=f"{line.mpn} is not in the local catalog.")

    requirements = build_requirements(line, context)
    search_args = {"category": original.category.value, "preferred_manufacturer": context.preferred_manufacturer,
                   "original_mpn": original.mpn}
    step(kind="tool_call", tool="search_candidates", arguments=search_args)
    candidates = search_candidates(original.category, context.preferred_manufacturer, original.mpn)
    names = ", ".join(c.mpn for c in candidates)
    step(kind="tool_result", tool="search_candidates", summary=f"{len(candidates)} candidates: {names}"[:240])
    if not candidates:
        return build_decision(line, context, [], None, Verdict.no_safe_match, source=Source.deterministic,
                              explanation="No candidate in the local catalog for this category.")

    comparisons = []
    for candidate in candidates:
        step(kind="tool_call", tool="compare_specs",
             arguments={"original_mpn": original.mpn, "candidate_mpn": candidate.mpn, "ref": line.ref})
        comparison = evaluate_pair(original, candidate, requirements)
        comparisons.append(comparison)
        fails = sum(c.result == CheckResult.fail for c in comparison.checks)
        caveat_count = sum(c.result == CheckResult.caveat for c in comparison.checks)
        step(kind="tool_result", tool="compare_specs",
             summary=f"{candidate.mpn}: {comparison.suggested_verdict.value}; {fails} fail, {caveat_count} caveat"[:240])

    best = rank_candidates(comparisons, context)[0]
    verdict = best.suggested_verdict
    caveats = [_describe(c) for c in _caveat_checks(best)]
    detail = floor_reason(best) if verdict != Verdict.drop_in else ""
    explanation = f"{VERDICT_LABELS[verdict]}: {best.candidate_mpn}." + (f" {_sentence(detail)}" if detail else "")
    return build_decision(line, context, comparisons, best.candidate_mpn, verdict, source=Source.deterministic,
                          caveats=caveats, explanation=explanation)
