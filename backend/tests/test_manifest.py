"""Phase 1 data gate: the demo BOM produces the three demo beats from real data."""

import json

import pytest

from app.bom import parse_bom
from app.catalog import load_part
from app.compare import evaluate_pair
from app.decide import decide_deterministic
from app.headline import headline_match
from app.paths import repo_root
from app.requirements_build import build_requirements
from app.schemas import DesignContext
from app.verdict import suggest_verdict

DATA = repo_root() / "data"
MANIFEST = DATA / "demo_manifest.json"

pytestmark = pytest.mark.skipif(not MANIFEST.exists(), reason="data/demo_manifest.json not written yet")


@pytest.fixture(scope="module")
def setup():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    lines, errors = parse_bom((DATA / "bom" / "demo_bom.csv").read_text(encoding="utf-8"))
    assert errors == []
    return manifest, DesignContext.model_validate(manifest["design_context"]), {l.ref: l for l in lines}


def manifest_lines():
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["lines"]


@pytest.mark.parametrize("entry", manifest_lines(), ids=lambda e: e["ref"])
def test_candidate_pair_verdicts(setup, entry):
    _, context, lines = setup
    line = lines[entry["ref"]]
    original = load_part(entry["original_mpn"])
    assert original is not None
    requirements = build_requirements(line, context)
    for candidate in entry["candidates"]:
        part = load_part(candidate["mpn"])
        assert part is not None, candidate["mpn"]
        comparison = evaluate_pair(original, part, requirements)
        assert suggest_verdict(comparison) == candidate["expected_pair_verdict"], (candidate["mpn"], comparison.checks)
        assert headline_match(original, part) == candidate["headline_match"], candidate["mpn"]


@pytest.mark.parametrize("entry", manifest_lines(), ids=lambda e: e["ref"])
def test_line_decision(setup, entry):
    _, context, lines = setup
    decision = decide_deterministic(lines[entry["ref"]], context)
    assert decision.recommended_mpn == entry["expected_recommended_mpn"]
    assert decision.verdict.value == entry["expected_verdict"]


def test_demo_bom_has_all_three_beats(setup):
    _, context, lines = setup
    decisions = [decide_deterministic(line, context) for line in lines.values()]
    verdicts = {d.verdict.value for d in decisions}
    assert {"drop_in", "drop_in_with_caveats"} <= verdicts
    assert any(r.headline_match for d in decisions for r in d.rejected)
