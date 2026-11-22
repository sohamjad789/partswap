"""Agent tools and the `record_decision` guardrails (PLAN.md section 4.9). Spec numbers never come from the model."""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.candidates import search_candidates
from app.catalog import load_part
from app.compare import evaluate_pair
from app.decide import VERDICT_LABELS, build_decision, floor_reason
from app.excerpts import excerpt_for
from app.package import check_package_pinout
from app.requirements_build import build_requirements
from app.schemas import (
    VERDICT_ORDER, BomLine, Category, CheckResult, Comparison, Decision, DesignContext, PartSpec, Requirements,
    Source, Verdict,
)
from app.verdict import is_more_permissive, rank_candidates

TOPICS = ["pinout", "absolute_maximum", "electrical", "thermal", "application"]
VERDICTS = [v.value for v in VERDICT_ORDER]
MAX_SUMMARY = 240


class FallbackRequired(Exception):
    """The line must be decided by `decide_deterministic` instead."""


def _function(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


_STR = {"type": "string"}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _function("get_bom_line", "The BOM line and its resolved requirements.", {"ref": _STR}, ["ref"]),
    _function("get_part_specs", "The verified spec record for one catalog part.", {"mpn": _STR}, ["mpn"]),
    _function("search_candidates", "Catalog parts in the same category. Returns no spec values.",
              {"category": {"type": "string", "enum": [c.value for c in Category]},
               "preferred_manufacturer": _STR, "original_mpn": _STR},
              ["category", "preferred_manufacturer", "original_mpn"]),
    _function("get_datasheet_excerpt", "Up to two datasheet text chunks for a part on one topic.",
              {"mpn": _STR, "topic": {"type": "string", "enum": TOPICS}}, ["mpn", "topic"]),
    _function("compare_specs", "Authoritative spec, package, and pinout comparison of a candidate against the "
              "original for this line, with each value's test condition.",
              {"original_mpn": _STR, "candidate_mpn": _STR, "ref": _STR}, ["original_mpn", "candidate_mpn", "ref"]),
    _function("check_package_pinout", "Package code and pin-function comparison of two parts.",
              {"original_mpn": _STR, "candidate_mpn": _STR}, ["original_mpn", "candidate_mpn"]),
    _function("record_decision", "Record the final verdict for this line. Call exactly once.",
              {"ref": _STR,
               "candidate_mpn": {"type": ["string", "null"]},
               "verdict": {"type": "string", "enum": VERDICTS},
               "confidence": {"type": "number", "minimum": 0, "maximum": 1},
               "caveats": {"type": "array", "items": _STR},
               "explanation": _STR},
              ["ref", "candidate_mpn", "verdict", "confidence", "caveats", "explanation"]),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}


@dataclass
class AgentState:
    line: BomLine
    context: DesignContext
    original: PartSpec
    requirements: Requirements
    model_id: Optional[str] = None
    only_candidates: Optional[list[str]] = None
    search_results: dict[str, PartSpec] = field(default_factory=dict)
    compared: set[str] = field(default_factory=set)
    record_errors: int = 0
    nudged: bool = False
    decision: Optional[Decision] = None
    guardrail_notes: list[str] = field(default_factory=list)

    @classmethod
    def for_line(cls, line: BomLine, context: DesignContext, original: PartSpec, **kwargs: Any) -> "AgentState":
        return cls(line=line, context=context, original=original,
                   requirements=build_requirements(line, context), **kwargs)

    def comparisons(self) -> list[Comparison]:
        return [evaluate_pair(self.original, p, self.requirements) for p in self.search_results.values()]


def execute_tool(name: str, arguments_json: Optional[str], state: AgentState) -> dict[str, Any]:
    if name not in TOOL_NAMES:
        return {"error": "unknown_tool"}
    try:
        args = json.loads(arguments_json or "{}")
    except (TypeError, ValueError):
        return {"error": "invalid_arguments"}
    if not isinstance(args, dict):
        return {"error": "invalid_arguments"}
    try:
        return _HANDLERS[name](state, args)
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"error": "invalid_arguments"}


def _str(args: dict[str, Any], key: str) -> str:
    value = args[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key)
    return value.strip()


def _get_bom_line(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    if _str(args, "ref").lower() != state.line.ref.lower():
        return {"error": "unknown_ref"}
    return {"line": state.line.model_dump(mode="json"), "requirements": state.requirements.model_dump(mode="json")}


def _get_part_specs(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    spec = load_part(_str(args, "mpn"))
    return spec.model_dump(mode="json") if spec else {"error": "unknown_mpn"}


def _search_candidates(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    category = Category(_str(args, "category"))
    preferred = args.get("preferred_manufacturer") or ""
    original_mpn = _str(args, "original_mpn")
    if state.only_candidates is not None:
        allowed = {m.lower() for m in state.only_candidates}
        found = [p for p in search_candidates(category, preferred, original_mpn, include_synthetic=True, limit=10_000)
                 if p.mpn.lower() in allowed]
    else:
        found = search_candidates(category, preferred, original_mpn)
    for p in found:
        state.search_results[p.mpn.lower()] = p
    return {"candidates": [{"mpn": p.mpn, "manufacturer": p.manufacturer, "package_code": p.package.code,
                            "description": p.description} for p in found]}


def _get_datasheet_excerpt(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    return excerpt_for(_str(args, "mpn"), _str(args, "topic"))


def _two_parts(args: dict[str, Any]) -> tuple[Optional[PartSpec], Optional[PartSpec]]:
    return load_part(_str(args, "original_mpn")), load_part(_str(args, "candidate_mpn"))


def _compare_specs(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    original, candidate = _two_parts(args)
    if original is None or candidate is None:
        return {"error": "unknown_mpn"}
    state.compared.add(candidate.mpn.lower())
    return evaluate_pair(original, candidate, state.requirements).model_dump(mode="json")


def _check_package_pinout(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    original, candidate = _two_parts(args)
    if original is None or candidate is None:
        return {"error": "unknown_mpn"}
    return check_package_pinout(original, candidate).model_dump(mode="json")


def _record_error(state: AgentState, error: str) -> dict[str, Any]:
    state.record_errors += 1
    if state.record_errors >= 2:
        raise FallbackRequired(f"record_decision failed twice ({error})")
    return {"error": error}


def _confidence(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return min(max(float(value), 0.0), 1.0)


def caveat_list(value: Any) -> list[str]:
    """Normalize `caveats` to a list of strings.

    Models sometimes send the array JSON-encoded as one string; iterating that string would store one
    caveat per character. A JSON array string is decoded; any other string is a single caveat.
    """
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except ValueError:
                decoded = None
            if isinstance(decoded, list):
                value = decoded
        if isinstance(value, str):
            value = [text]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(c).strip() for c in value if str(c).strip()]


def _record_decision(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    verdict = args.get("verdict")
    if verdict not in VERDICTS:
        return _record_error(state, "invalid_verdict")
    candidate_mpn = args.get("candidate_mpn")
    if candidate_mpn is None:
        if state.search_results:
            return _record_error(state, "unknown_candidate")
    elif not isinstance(candidate_mpn, str) or candidate_mpn.strip().lower() not in state.search_results:
        return _record_error(state, "unknown_candidate")

    comparisons = state.comparisons()
    if not state.nudged:
        for c in rank_candidates(comparisons, state.context):
            if c.candidate_mpn.lower() not in state.compared and is_more_permissive(c.suggested_verdict, verdict):
                state.nudged = True
                return {"error": "uncompared_candidate",
                        "message": f"You have not compared {c.candidate_mpn}. Compare it before deciding."}

    caveats = caveat_list(args.get("caveats"))
    explanation = str(args.get("explanation") or "").strip()
    stored, tightened, compared_mpn = verdict, False, None
    if candidate_mpn is not None:
        compared = next(c for c in comparisons if c.candidate_mpn.lower() == candidate_mpn.strip().lower())
        compared_mpn = compared.candidate_mpn
        floor = compared.suggested_verdict
        if is_more_permissive(verdict, floor):
            stored, tightened = floor.value, True
            note = f"Verdict tightened by deterministic check: {floor_reason(compared)}"
            caveats.append(note)
            state.guardrail_notes.append(note)

    state.decision = build_decision(
        state.line, state.context, comparisons, compared_mpn, stored, source=Source.model, model=state.model_id,
        model_verdict=verdict, confidence=_confidence(args.get("confidence")), caveats=caveats,
        explanation=explanation or f"{VERDICT_LABELS[Verdict(stored)]}: {compared_mpn or 'no candidate'}.",
        tightened=tightened,
    )
    return state.decision.model_dump(mode="json")


_HANDLERS = {
    "get_bom_line": _get_bom_line,
    "get_part_specs": _get_part_specs,
    "search_candidates": _search_candidates,
    "get_datasheet_excerpt": _get_datasheet_excerpt,
    "compare_specs": _compare_specs,
    "check_package_pinout": _check_package_pinout,
    "record_decision": _record_decision,
}


def summarize(name: str, result: dict[str, Any]) -> str:
    """One-line `tool_result` summary (PLAN.md section 4.11)."""
    if "error" in result:
        text = f"error: {result['error']}" + (f" ({result['message']})" if result.get("message") else "")
    elif name == "compare_specs":
        checks = result["checks"]
        fails = sum(c["result"] == CheckResult.fail.value for c in checks)
        caveats = sum(c["result"] == CheckResult.caveat.value for c in checks)
        text = f"{result['candidate_mpn']}: {result['suggested_verdict']}; {fails} fail, {caveats} caveat"
    elif name == "search_candidates":
        names = ", ".join(c["mpn"] for c in result["candidates"])
        text = f"{len(result['candidates'])} candidates: {names}"
    elif name == "record_decision":
        text = f"{result['ref']}: {result['verdict']} ({result['compared_mpn'] or 'no candidate'})"
    elif name == "get_part_specs":
        text = f"{result['mpn']}: {result['category']}, {result['package']['code']}"
    elif name == "get_bom_line":
        text = f"{result['line']['ref']}: {result['line']['mpn']}"
    elif name == "get_datasheet_excerpt":
        pages = ", ".join(str(c["page"]) for c in result["chunks"])
        text = f"{result['mpn']} {result['topic']}: {len(result['chunks'])} chunks (p. {pages})"
    elif name == "check_package_pinout":
        text = f"package {result['package']['result']}, pinout {result['pinout']['result']}"
    else:
        text = json.dumps(result)
    return text[:MAX_SUMMARY]
