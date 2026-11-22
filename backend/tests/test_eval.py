"""Phase 7: the labelled pair set and the evaluation metrics (PLAN.md section 4.17). No network."""

import json
from collections import Counter

import pytest

from app.candidates import search_candidates
from app.catalog import all_parts, load_part
from app.decide import decide_deterministic
from app.eval.run_eval import (
    ARM_ORDER,
    Pair,
    PairOutcome,
    compute_metrics,
    eval_context,
    load_pairs,
    merge_results,
    model_outcome,
    pair_line,
    rules_comparison,
    run_arm,
)
from app.headline import headline_match
from app.paths import data_dir
from app.schemas import Source, Verdict
from app.verdict import suggest_verdict

PAIRS = load_pairs()
BY_ID = {p.id: p for p in PAIRS}
CLASS_COUNTS = {"A": 5, "B": 3, "C": 3, "D": 3, "E": 4, "F": 2}
DANGEROUS_CLASSES = {"A", "B", "C", "D"}


def ids(pairs):
    return [p.id for p in pairs]


# --------------------------------------------------------------------------- the pair set

def test_twenty_pairs_with_the_planned_class_counts():
    assert len(PAIRS) == 20
    assert Counter(p.pair_class for p in PAIRS) == CLASS_COUNTS
    assert len(BY_ID) == 20, "pair ids must be unique"
    assert all(p.id.startswith(p.pair_class) for p in PAIRS)


@pytest.mark.parametrize("pair", PAIRS, ids=ids(PAIRS))
def test_every_mpn_resolves_to_a_verified_part_of_the_same_category(pair):
    original, candidate = load_part(pair.original_mpn), load_part(pair.candidate_mpn)
    assert original is not None, f"{pair.original_mpn} not in catalog"
    assert candidate is not None, f"{pair.candidate_mpn} not in catalog"
    assert original.verified and candidate.verified
    assert original.category == candidate.category
    assert original.mpn != candidate.mpn
    assert pair_line(pair).ref == pair.id


@pytest.mark.parametrize("pair", PAIRS, ids=ids(PAIRS))
def test_dangerous_flag_matches_the_class(pair):
    assert pair.dangerous_if_drop_in == (pair.pair_class in DANGEROUS_CLASSES)


@pytest.mark.parametrize("pair", PAIRS, ids=ids(PAIRS))
def test_headline_matches_what_the_class_table_says_the_baseline_does(pair):
    # Classes A, B, C must look safe to a basic cross-reference; D differs in package so it does not.
    expected = pair.pair_class != "D"
    assert headline_match(load_part(pair.original_mpn), load_part(pair.candidate_mpn)) is expected


@pytest.mark.parametrize("pair", PAIRS, ids=ids(PAIRS))
def test_rules_verdict_matches_the_label_except_class_c(pair):
    verdict = suggest_verdict(rules_comparison(pair))
    if pair.pair_class == "C":
        # Every number passes, so class C measures the model, not the rules.
        assert verdict == Verdict.drop_in
    else:
        assert verdict == pair.expected_verdict


@pytest.mark.parametrize("pair", [p for p in PAIRS if p.pair_class == "C"], ids=lambda p: p.id)
def test_class_c_candidates_have_hand_authored_excerpts(pair):
    path = data_dir() / "excerpts" / f"{pair.candidate_mpn.replace('/', '_')}.json"
    excerpt = json.loads(path.read_text(encoding="utf-8"))
    assert excerpt["authored"] is True and excerpt["chunks"]


def test_synthetic_parts_never_reach_a_demo_search():
    synthetic = [p for p in all_parts() if p.synthetic]
    assert synthetic, "the evaluation needs its SYN- parts"
    assert all(p.mpn.startswith("SYN-") for p in synthetic)
    for part in synthetic:
        demo = search_candidates(part.category, "Diodes Incorporated", "NOT-IN-CATALOG")
        assert all(not c.synthetic for c in demo)


def test_catalog_stays_within_the_part_budget():
    assert len(all_parts()) <= 30  # Phase 1 pitfall: do not grow past 30 parts


def test_baseline_and_rules_counts_match_the_plan_by_construction():
    baseline = compute_metrics("naive_baseline", PAIRS, run_arm("baseline", PAIRS, log=lambda _: None), model_arm=False)
    rules = compute_metrics("partswap_rules", PAIRS, run_arm("rules", PAIRS, log=lambda _: None), model_arm=False)
    assert baseline["false_drop_in_count"] == 11
    assert rules["false_drop_in_count"] == 3


# --------------------------------------------------------------------------- metrics

def _pair(pid, expected, dangerous):
    return Pair.model_validate({"id": pid, "class": "A", "original_mpn": "X", "candidate_mpn": "Y", "description": "",
                                "requirements": {}, "expected_verdict": expected, "dangerous_if_drop_in": dangerous})


def test_metrics_on_a_hand_built_example():
    pairs = [
        _pair("p1", "no_safe_match", True),
        _pair("p2", "needs_redesign", True),
        _pair("p3", "drop_in_with_caveats", True),
        _pair("p4", "drop_in", False),
    ]
    outcomes = {
        "p1": PairOutcome(verdict="no_safe_match", model_verdict="drop_in", tightened=True, latency_ms=10),
        "p2": PairOutcome(verdict="drop_in", model_verdict="drop_in", latency_ms=30),
        "p3": PairOutcome(verdict="drop_in", fallback=True, latency_ms=20),
        "p4": PairOutcome(verdict="drop_in", model_verdict="drop_in", latency_ms=40),
    }
    row = compute_metrics("partswap_super", pairs, outcomes, model_arm=True)
    assert row == {
        "name": "partswap_super",
        "accuracy": 0.5,                  # p1 and p4 are right
        "false_drop_in_count": 2,         # p2 and p3: dangerous pairs whose final verdict is drop_in
        "model_false_drop_in_count": 2,   # p1 and p2: dangerous pairs the model itself called drop_in
        "tightened_count": 1,
        "fallback_count": 1,
        "median_latency_ms": 25.0,
    }
    plain = compute_metrics("partswap_rules", pairs, outcomes, model_arm=False)
    assert plain["model_false_drop_in_count"] is None and plain["fallback_count"] is None


def test_requirement_columns_are_validated():
    with pytest.raises(ValueError):
        Pair.model_validate({**BY_ID["A1-schottky-vrrm-20"].model_dump(by_alias=True), "requirements": {"vrrm": 32}})


# --------------------------------------------------------------------------- model arm plumbing

def test_model_outcome_caches_and_scores_a_fallback_with_the_rules_verdict(tmp_path):
    pair = BY_ID["A1-schottky-vrrm-20"]
    calls = []

    def fallback_runner(line, context, model_id, emit, only_candidates=None):
        calls.append(only_candidates)
        decision = decide_deterministic(line, context)
        return decision.model_copy(update={"source": Source.deterministic_fallback})

    kwargs = dict(model_id="fake-model", prompt_version="v1", cache_dir=tmp_path, runner=fallback_runner)
    first = model_outcome(pair, **kwargs)
    second = model_outcome(pair, **kwargs)

    assert calls == [[pair.candidate_mpn]], "second call must come from the cache"
    assert first.fallback and second.fallback
    assert first.verdict == second.verdict == Verdict.no_safe_match  # the pair's rules verdict
    model_outcome(pair, **{**kwargs, "prompt_version": "v2"})
    assert len(calls) == 2, "a new prompt version is a cache miss"


def test_model_outcome_keeps_the_model_verdict_when_it_decided(tmp_path):
    pair = BY_ID["E1-schottky-b0540w"]

    def model_runner(line, context, model_id, emit, only_candidates=None):
        decision = decide_deterministic(line, context)
        assert decision.compared_mpn == pair.candidate_mpn
        return decision.model_copy(update={"source": Source.model, "model_verdict": Verdict.drop_in, "confidence": 0.9})

    outcome = model_outcome(pair, model_id="fake-model", prompt_version="v1", cache_dir=tmp_path, runner=model_runner)
    assert not outcome.fallback
    assert outcome.verdict == Verdict.drop_in and outcome.model_verdict == Verdict.drop_in


def test_merge_keeps_arms_from_earlier_runs():
    pairs = PAIRS[:2]
    first = merge_results(None, pairs, [{"name": "partswap_super", "accuracy": 1.0}],
                          {"partswap_super": {p.id: PairOutcome(verdict=p.expected_verdict) for p in pairs}}, "v1")
    second = merge_results(first, pairs, [{"name": "naive_baseline", "accuracy": 0.0}],
                           {"naive_baseline": {p.id: PairOutcome(verdict="drop_in") for p in pairs}}, "v1")
    assert [row["name"] for row in second["approaches"]] == ["naive_baseline", "partswap_super"]
    assert [n for n in ARM_ORDER if n in second["per_pair"][0]] == ["naive_baseline", "partswap_super"]
    assert second["per_pair"][0]["partswap_super"] == pairs[0].expected_verdict.value
    assert second["pair_count"] == 2 and second["dangerous_count"] == 2


def test_eval_context_is_the_demo_board():
    context = eval_context()
    assert (context.input_voltage_v, context.input_voltage_max_v) == (24, 32)
    assert (context.operating_temp_min_c, context.operating_temp_max_c) == (-40, 85)
    assert context.preferred_manufacturer == "Diodes Incorporated"
