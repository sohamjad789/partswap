"""Evaluation harness (PLAN.md section 4.17 and Phase 7).

Scores four approaches on the 20 labelled swap pairs in `data/eval/pairs.json` and merges the measured
numbers into `data/eval/results.json`, which `GET /api/eval` serves to the UI.

    cd backend && python -m app.eval.run_eval --arms baseline,rules
    cd backend && python -m app.eval.run_eval --arms super
    cd backend && python -m app.eval.run_eval --arms bolt [--refresh]

Arms:
    naive_baseline   drop_in when the headline cross-reference matches, else no_safe_match
    partswap_rules   suggest_verdict(evaluate_pair(...)), no model
    partswap_bolt    run_part with the fast model, restricted to the pair's candidate
    partswap_super   run_part with the reasoning model, restricted to the pair's candidate

Model arms cache each pair's decision in `data/cache/eval/{arm}/{id}.json`; `--refresh` ignores the cache.
A model decision that fell back to the deterministic path is scored with the pair's rules verdict and counted
in `fallback_count`, so a fallback is never reported as the model's own answer.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog import load_part
from app.compare import evaluate_pair
from app.headline import headline_match
from app.paths import data_dir
from app.requirements_build import build_requirements
from app.schemas import BomLine, Comparison, Decision, DesignContext, Source, Verdict
from app.verdict import suggest_verdict

ARM_NAMES: dict[str, str] = {
    "baseline": "naive_baseline",
    "rules": "partswap_rules",
    "bolt": "partswap_bolt",
    "super": "partswap_super",
}
ARM_ORDER = list(ARM_NAMES.values())
MODEL_ARMS = {"bolt", "super"}
WORKERS = 3  # free-tier rate limit: keep concurrency at 3 (PLAN.md section 12)

Runner = Callable[..., Decision]


class Pair(BaseModel):
    """One labelled swap pair (PLAN.md section 4.17)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    pair_class: Literal["A", "B", "C", "D", "E", "F"] = Field(alias="class")
    original_mpn: str
    candidate_mpn: str
    description: str
    requirements: dict[str, float]
    expected_verdict: Verdict
    dangerous_if_drop_in: bool

    @field_validator("requirements")
    @classmethod
    def _requirement_columns(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = [k for k in value if not k.startswith("req_") or k not in BomLine.model_fields]
        if unknown:
            raise ValueError(f"unknown requirement column(s): {', '.join(unknown)}")
        return value


class PairOutcome(BaseModel):
    """What one arm said about one pair."""

    verdict: Verdict
    model_verdict: Optional[Verdict] = None
    tightened: bool = False
    fallback: bool = False
    latency_ms: float = 0.0


# --------------------------------------------------------------------------- inputs

def pairs_path() -> Path:
    return data_dir() / "eval" / "pairs.json"


def results_path() -> Path:
    return data_dir() / "eval" / "results.json"


def load_pairs(path: Optional[Path] = None) -> list[Pair]:
    raw = json.loads((path or pairs_path()).read_text(encoding="utf-8"))
    return [Pair.model_validate(item) for item in raw]


def eval_context() -> DesignContext:
    """The demo board's design context. `DesignContext` defaults are the demo values (PLAN.md section 4.4)."""
    return DesignContext()


def pair_line(pair: Pair) -> BomLine:
    """A synthetic BOM line for the pair: ref is the pair id, requirement cells come from `requirements`."""
    original = load_part(pair.original_mpn)
    if original is None:
        raise ValueError(f"{pair.id}: original {pair.original_mpn} is not in the catalog")
    return BomLine(ref=pair.id, manufacturer=original.manufacturer, mpn=original.mpn, qty=1,
                   description=pair.description, **pair.requirements)


def rules_comparison(pair: Pair, context: Optional[DesignContext] = None) -> Comparison:
    original, candidate = load_part(pair.original_mpn), load_part(pair.candidate_mpn)
    if original is None or candidate is None:
        raise ValueError(f"{pair.id}: a part is missing from the catalog")
    requirements = build_requirements(pair_line(pair), context or eval_context())
    return evaluate_pair(original, candidate, requirements)


# --------------------------------------------------------------------------- arms

def _timed(work: Callable[[], Verdict]) -> PairOutcome:
    start = time.perf_counter()
    verdict = work()
    return PairOutcome(verdict=verdict, latency_ms=(time.perf_counter() - start) * 1000)


def baseline_outcome(pair: Pair) -> PairOutcome:
    def work() -> Verdict:
        original, candidate = load_part(pair.original_mpn), load_part(pair.candidate_mpn)
        return Verdict.drop_in if headline_match(original, candidate) else Verdict.no_safe_match
    return _timed(work)


def rules_outcome(pair: Pair, context: Optional[DesignContext] = None) -> PairOutcome:
    return _timed(lambda: suggest_verdict(rules_comparison(pair, context)))


def _cache_file(cache_dir: Path, pair: Pair) -> Path:
    return cache_dir / f"{pair.id}.json"


def score_decision(pair: Pair, decision: Decision, latency_ms: float, context: Optional[DesignContext] = None) -> PairOutcome:
    """Turn a model decision into a pair outcome. Fallbacks are scored with the rules verdict."""
    on_candidate = (decision.compared_mpn or "").lower() == pair.candidate_mpn.lower()
    if decision.source != Source.model or not on_candidate:
        return PairOutcome(verdict=suggest_verdict(rules_comparison(pair, context)), fallback=True, latency_ms=latency_ms)
    return PairOutcome(verdict=decision.verdict, model_verdict=decision.model_verdict,
                       tightened=decision.tightened, latency_ms=latency_ms)


def model_outcome(pair: Pair, *, model_id: str, prompt_version: str, cache_dir: Path, refresh: bool = False,
                  runner: Optional[Runner] = None, context: Optional[DesignContext] = None) -> PairOutcome:
    """Run (or load from cache) the agent on one pair, restricted to the pair's candidate."""
    context = context or eval_context()
    path = _cache_file(cache_dir, pair)
    if not refresh and path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("model") == model_id and cached.get("prompt_version") == prompt_version:
            return score_decision(pair, Decision.model_validate(cached["decision"]), cached.get("latency_ms", 0.0), context)

    if runner is None:
        from app.agent.loop import run_part  # imported here so baseline/rules never load the model client
        runner = run_part
    errors: list[str] = []

    def emit(event: str, data: dict[str, Any]) -> None:
        if event == "part_error":
            errors.append(str(data.get("message", "")))

    start = time.perf_counter()
    decision = runner(pair_line(pair), context, model_id, emit, only_candidates=[pair.candidate_mpn])
    latency_ms = (time.perf_counter() - start) * 1000

    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pair_id": pair.id, "model": model_id, "prompt_version": prompt_version,
                                "latency_ms": latency_ms, "fallback_reason": errors[0] if errors else None,
                                "decision": decision.model_dump(mode="json")},
                               indent=2, ensure_ascii=False), encoding="utf-8")
    return score_decision(pair, decision, latency_ms, context)


# --------------------------------------------------------------------------- metrics

def compute_metrics(name: str, pairs: list[Pair], outcomes: dict[str, PairOutcome], *, model_arm: bool) -> dict[str, Any]:
    """The per-approach row of `results.json` (PLAN.md section 4.17)."""
    scored = [(p, outcomes[p.id]) for p in pairs]
    dangerous = [(p, o) for p, o in scored if p.dangerous_if_drop_in]
    latencies = [o.latency_ms for _, o in scored]
    return {
        "name": name,
        "accuracy": round(sum(o.verdict == p.expected_verdict for p, o in scored) / len(scored), 4) if scored else 0.0,
        "false_drop_in_count": sum(o.verdict == Verdict.drop_in for _, o in dangerous),
        "model_false_drop_in_count": sum(o.model_verdict == Verdict.drop_in for _, o in dangerous) if model_arm else None,
        "tightened_count": sum(o.tightened for _, o in scored) if model_arm else None,
        "fallback_count": sum(o.fallback for _, o in scored) if model_arm else None,
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
    }


def merge_results(existing: Optional[dict[str, Any]], pairs: list[Pair], new_rows: Iterable[dict[str, Any]],
                  new_columns: dict[str, dict[str, PairOutcome]], prompt_version: str) -> dict[str, Any]:
    """Merge freshly computed arms into an earlier results file, keeping arms that were not re-run."""
    existing = existing if existing and existing.get("approaches") else {}
    rows = {row["name"]: row for row in existing.get("approaches", [])}
    rows.update({row["name"]: row for row in new_rows})

    previous = {row["id"]: row for row in existing.get("per_pair", [])}
    per_pair = []
    for pair in pairs:
        row = {"id": pair.id, "class": pair.pair_class, "expected": pair.expected_verdict.value}
        row.update({k: v for k, v in previous.get(pair.id, {}).items() if k in ARM_ORDER})
        for name, outcomes in new_columns.items():
            row[name] = outcomes[pair.id].verdict.value
        per_pair.append(row)

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pair_count": len(pairs),
        "dangerous_count": sum(p.dangerous_if_drop_in for p in pairs),
        "prompt_version": prompt_version,
        "approaches": [rows[name] for name in ARM_ORDER if name in rows],
        "per_pair": per_pair,
    }


# --------------------------------------------------------------------------- runner

def run_arm(arm: str, pairs: list[Pair], *, refresh: bool = False, prompt_version: str = "",
            runner: Optional[Runner] = None, log: Callable[[str], None] = print) -> dict[str, PairOutcome]:
    if arm == "baseline":
        return {p.id: baseline_outcome(p) for p in pairs}
    if arm == "rules":
        return {p.id: rules_outcome(p) for p in pairs}

    from app.config import get_settings
    settings = get_settings()
    model_id = settings.super_model if arm == "super" else settings.fast_model
    cache_dir = data_dir() / "cache" / "eval" / arm

    def one(pair: Pair) -> tuple[str, PairOutcome]:
        outcome = model_outcome(pair, model_id=model_id, prompt_version=prompt_version, cache_dir=cache_dir,
                                refresh=refresh, runner=runner)
        note = " (fallback: rules verdict)" if outcome.fallback else (" (tightened)" if outcome.tightened else "")
        log(f"  [{arm}] {pair.id:28} {outcome.verdict.value:22} {outcome.latency_ms / 1000:6.1f} s{note}")
        return pair.id, outcome

    log(f"{ARM_NAMES[arm]}: {model_id}, {len(pairs)} pairs, {WORKERS} workers")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return dict(pool.map(one, pairs))


def _print_summary(results: dict[str, Any], new_names: set[str]) -> None:
    print(f"\n{'approach':18} {'accuracy':>8} {'unsafe':>7} {'model':>6} {'tight':>6} {'fallbk':>7} {'median ms':>10}")
    for row in results["approaches"]:
        def cell(key: str) -> str:
            return "-" if row.get(key) is None else str(row[key])
        mark = "*" if row["name"] in new_names else " "
        print(f"{mark}{row['name']:17} {row['accuracy']:8.0%} {cell('false_drop_in_count'):>7} "
              f"{cell('model_false_drop_in_count'):>6} {cell('tightened_count'):>6} {cell('fallback_count'):>7} "
              f"{row['median_latency_ms']:10.1f}")
    for row in results["approaches"]:
        if (row.get("fallback_count") or 0) > 4:
            print(f"note: {row['name']} fell back on {row['fallback_count']} pairs; report it with fallback_count, "
                  "not as the model's accuracy.")
    misses = [(r["id"], name, r[name], r["expected"]) for r in results["per_pair"] for name in sorted(new_names)
              if name in r and r[name] != r["expected"]]
    if misses:
        print("\nmisses (pair, approach, got, expected):")
        for pair_id, name, got, expected in misses:
            print(f"  {pair_id:28} {name:16} {got:22} expected {expected}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PartSwap evaluation (PLAN.md section 4.17).")
    parser.add_argument("--arms", default="baseline,rules", help="comma-separated: baseline, rules, bolt, super")
    parser.add_argument("--refresh", action="store_true", help="ignore cached model decisions")
    args = parser.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARM_NAMES]
    if unknown or not arms:
        parser.error(f"unknown arm(s): {', '.join(unknown) or '(none)'}; choose from {', '.join(ARM_NAMES)}")

    if MODEL_ARMS & set(arms):
        from app.config import get_settings
        if not get_settings().has_api_key:
            print("NVIDIA_API_KEY is not set; model arms need it. Baseline and rules run without a key.", file=sys.stderr)
            return 2

    from app.agent.prompts import PROMPT_VERSION

    pairs = load_pairs()
    new_rows, new_columns = [], {}
    for arm in arms:
        outcomes = run_arm(arm, pairs, refresh=args.refresh, prompt_version=PROMPT_VERSION)
        name = ARM_NAMES[arm]
        new_rows.append(compute_metrics(name, pairs, outcomes, model_arm=arm in MODEL_ARMS))
        new_columns[name] = outcomes

    path = results_path()
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    results = merge_results(existing, pairs, new_rows, new_columns, PROMPT_VERSION)
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    _print_summary(results, set(new_columns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
