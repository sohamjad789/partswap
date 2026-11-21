import json

import pytest

from app import schemas
from app.paths import data_dir, repo_root

EXAMPLES = repo_root() / "shared" / "examples"

EXAMPLE_MODELS = {
    "design_context.json": schemas.DesignContext,
    "part_spec.json": schemas.PartSpec,
    "comparison.json": schemas.Comparison,
    "package_pinout.json": schemas.PackagePinoutResult,
    "decision.json": schemas.Decision,
    "eval_results.json": schemas.EvalResults,
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_example_file_has_a_model():
    on_disk = {p.name for p in EXAMPLES.iterdir() if p.is_file()}
    assert on_disk == set(EXAMPLE_MODELS) | {"sse_events.jsonl"}


@pytest.mark.parametrize("name", sorted(EXAMPLE_MODELS))
def test_example_validates(name):
    EXAMPLE_MODELS[name].model_validate(load(EXAMPLES / name))


def test_sse_examples_cover_every_event_and_step_kind():
    lines = [json.loads(l) for l in (EXAMPLES / "sse_events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for line in lines:
        schemas.FixtureEvent.model_validate(line)
    assert {l["event"] for l in lines} == set(schemas.SSE_EVENT_MODELS)
    kinds = {l["data"]["kind"] for l in lines if l["event"] == "agent_step"}
    assert kinds == {"reasoning", "tool_call", "tool_result", "guardrail", "error"}


def test_starter_fixture_validates():
    fixture = schemas.FixtureRun.model_validate(load(data_dir() / "fixtures" / "demo_run.json"))
    streamed = [e.data for e in fixture.events if e.event == "part_decision"]
    assert [schemas.Decision.model_validate(d) for d in streamed] == fixture.decisions
    assert fixture.events[0].event == "run_started"
    assert fixture.events[-1].event == "run_completed"


def test_starter_fixture_covers_the_demo_beats():
    fixture = schemas.FixtureRun.model_validate(load(data_dir() / "fixtures" / "demo_run.json"))
    verdicts = {d.verdict for d in fixture.decisions}
    assert {schemas.Verdict.drop_in, schemas.Verdict.drop_in_with_caveats} <= verdicts
    assert any(r.headline_match for d in fixture.decisions for r in d.rejected)


def test_policy_files_parse():
    categories = load(data_dir() / "categories.json")
    assert set(categories) == {c.value for c in schemas.Category}
    tokens = set(schemas.PinFunction.__args__)
    assert set(load(data_dir() / "pin_functions.json").values()) <= tokens
    load(data_dir() / "package_aliases.json")
    load(data_dir() / "topics.json")


def test_decision_rejects_recommendation_on_no_safe_match():
    data = load(EXAMPLES / "decision.json") | {"verdict": "no_safe_match"}
    with pytest.raises(ValueError):
        schemas.Decision.model_validate(data)


def test_agent_step_rejects_fields_of_another_kind():
    with pytest.raises(ValueError):
        schemas.AgentStep.model_validate({"ref": "D1", "step": 1, "kind": "reasoning", "tool": "compare_specs"})
