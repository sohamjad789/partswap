"""Pydantic models for every contract in PLAN.md section 4.

Field names are the contract shared with the frontend (`frontend/src/types.ts`)
and with `shared/examples/`. Change them only together with PLAN.md.
"""

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- enums


class Category(str, Enum):
    ldo = "ldo"
    buck = "buck"
    schottky = "schottky"
    mosfet = "mosfet"
    esd = "esd"


class Verdict(str, Enum):
    drop_in = "drop_in"
    drop_in_with_caveats = "drop_in_with_caveats"
    needs_redesign = "needs_redesign"
    no_safe_match = "no_safe_match"


VERDICT_ORDER: list[Verdict] = [
    Verdict.drop_in,
    Verdict.drop_in_with_caveats,
    Verdict.needs_redesign,
    Verdict.no_safe_match,
]


class Goal(str, Enum):
    lowest_risk = "lowest_risk"
    lowest_cost = "lowest_cost"
    shortest_lead_time = "shortest_lead_time"


class Mode(str, Enum):
    fixture = "fixture"
    deterministic = "deterministic"
    cache = "cache"
    live = "live"


class Source(str, Enum):
    model = "model"
    deterministic = "deterministic"
    deterministic_fallback = "deterministic_fallback"


class CheckResult(str, Enum):
    pass_ = "pass"
    fail = "fail"
    caveat = "caveat"
    unknown = "unknown"
    skip = "skip"


PinFunction = Literal[
    "ground", "power_in", "power_out", "enable_active_high", "enable_active_low",
    "nc", "gate", "drain", "source", "anode", "cathode", "io", "feedback",
    "bypass", "switch", "bootstrap", "power_good", "unknown",
]

OnUnknown = Union[Verdict, Literal["caveat"]]


# ---------------------------------------------------------------- part spec (4.5)


class SpecField(Contract):
    value: Optional[float] = None
    raw: Optional[str] = None
    condition: str
    page: Optional[int] = Field(default=None, ge=1)
    table: Optional[str] = None


class Package(Contract):
    code: str
    pins: int = Field(ge=1)
    page: Optional[int] = Field(default=None, ge=1)


class Pin(Contract):
    pin: int = Field(ge=1)
    name: str
    functions: list[PinFunction]


class PartSpec(Contract):
    mpn: str
    manufacturer: str
    category: Category
    description: str
    datasheet_filename: Optional[str] = None
    package: Package
    pinout: Optional[list[Pin]] = None
    pinout_page: Optional[int] = Field(default=None, ge=1)
    polarity: Optional[Literal["n", "p", "unidirectional", "bidirectional"]] = None
    diode_count: Optional[int] = None
    channel_count: Optional[int] = None
    topology: Optional[Literal["synchronous", "asynchronous"]] = None
    output_type: Optional[Literal["fixed", "adjustable"]] = None
    unit_price_usd: Optional[float] = None
    lead_time_weeks: Optional[float] = None
    verified: bool
    synthetic: bool = False
    specs: dict[str, SpecField]

    @model_validator(mode="after")
    def _synthetic_prefix(self) -> "PartSpec":
        if self.synthetic != self.mpn.startswith("SYN-"):
            raise ValueError("synthetic parts, and only synthetic parts, have an MPN starting with 'SYN-'")
        return self


# ---------------------------------------------------------------- BOM, context, requirements (4.3, 4.4)


class BomLine(Contract):
    ref: str = Field(min_length=1)
    manufacturer: str
    mpn: str = Field(min_length=1)
    qty: int = Field(gt=0)
    description: str = ""
    req_vin_max_v: Optional[float] = None
    req_vout_v: Optional[float] = None
    req_iout_a: Optional[float] = None
    req_temp_min_c: Optional[float] = None
    req_temp_max_c: Optional[float] = None
    req_vrrm_v: Optional[float] = None
    req_vds_v: Optional[float] = None
    req_vgs_v: Optional[float] = None
    req_vrwm_v: Optional[float] = None
    req_headroom_vin_v: Optional[float] = None
    req_esd_contact_kv: Optional[float] = None
    req_c_max_pf: Optional[float] = None


class BomError(Contract):
    row: int = Field(ge=1)
    message: str


class DesignContext(Contract):
    input_voltage_v: float = 24.0
    input_voltage_max_v: float = 32.0
    operating_temp_min_c: float = -40
    operating_temp_max_c: float = 85
    preferred_manufacturer: str = "Diodes Incorporated"
    goal: Goal = Goal.lowest_risk


class Requirements(Contract):
    input_voltage_v: Optional[float] = None
    req_vin_max_v: Optional[float] = None
    req_vout_v: Optional[float] = None
    req_iout_a: Optional[float] = None
    req_temp_min_c: Optional[float] = None
    req_temp_max_c: Optional[float] = None
    req_vrrm_v: Optional[float] = None
    req_vds_v: Optional[float] = None
    req_vgs_v: Optional[float] = None
    req_vrwm_v: Optional[float] = None
    req_headroom_vin_v: Optional[float] = None
    req_esd_contact_kv: Optional[float] = None
    req_c_max_pf: Optional[float] = None


# ---------------------------------------------------------------- comparison (4.6)


class CheckValue(Contract):
    """One side of a check. Root checks (output_type, polarity, package) carry strings or ints."""

    value: Union[float, str, None] = None
    raw: Optional[str] = None
    condition: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)


class Check(Contract):
    spec: str
    result: CheckResult
    on_fail: Optional[Verdict] = None
    on_unknown: Optional[OnUnknown] = None
    requirement: Optional[str] = None
    original: Optional[CheckValue] = None
    candidate: Optional[CheckValue] = None
    reason: str = ""


class Comparison(Contract):
    original_mpn: str
    candidate_mpn: str
    category: Category
    checks: list[Check]
    suggested_verdict: Verdict
    headline_match: bool


class PackageComparison(Contract):
    original: Optional[str] = None
    candidate: Optional[str] = None
    result: CheckResult


class PinoutComparison(Contract):
    original: Optional[dict[str, list[PinFunction]]] = None
    candidate: Optional[dict[str, list[PinFunction]]] = None
    result: CheckResult


class PackagePinoutResult(Contract):
    """Return value of `package.check_package_pinout` and the `check_package_pinout` tool."""

    package: PackageComparison
    pinout: PinoutComparison
    detail: str


class PackagePinoutSummary(Contract):
    """`Decision.package_pinout`."""

    package_result: CheckResult
    pinout_result: CheckResult
    detail: str


# ---------------------------------------------------------------- decision and run (4.8, 4.12)


class RejectedCandidate(Contract):
    mpn: str
    manufacturer: str
    verdict: Verdict
    reason: str
    headline_match: bool


class Decision(Contract):
    ref: str
    original_mpn: str
    original_manufacturer: str
    recommended_mpn: Optional[str] = None
    recommended_manufacturer: Optional[str] = None
    compared_mpn: Optional[str] = None
    verdict: Verdict
    model_verdict: Optional[Verdict] = None
    tightened: bool = False
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source: Source
    model: Optional[str] = None
    spec_checks: list[Check] = Field(default_factory=list)
    package_pinout: Optional[PackagePinoutSummary] = None
    caveats: list[str] = Field(default_factory=list)
    explanation: str
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    candidates_considered: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _invariants(self) -> "Decision":
        if self.verdict == Verdict.no_safe_match:
            if self.recommended_mpn is not None:
                raise ValueError("recommended_mpn must be null when verdict is no_safe_match")
        elif self.recommended_mpn != self.compared_mpn:
            raise ValueError("recommended_mpn must equal compared_mpn unless verdict is no_safe_match")
        if self.tightened and self.confidence is not None and self.confidence > 0.6:
            raise ValueError("confidence is capped at 0.6 when tightened")
        return self


class Run(Contract):
    run_id: str
    created_at: str
    mode: Mode
    design_context: DesignContext
    decisions: list[Decision]


class RunRequest(Contract):
    """Body of `POST /api/runs`. `mode` null means `PARTSWAP_MODE`."""

    lines: list[BomLine] = Field(default_factory=list)
    design_context: DesignContext = Field(default_factory=DesignContext)
    mode: Optional[Mode] = None


# ---------------------------------------------------------------- SSE events (4.11)


class RunStarted(Contract):
    run_id: str
    part_count: int = Field(ge=0)
    mode: Mode


class PartStarted(Contract):
    ref: str
    mpn: str
    index: int = Field(ge=0)


AgentStepKind = Literal["reasoning", "tool_call", "tool_result", "guardrail", "error"]

_STEP_FIELDS: dict[str, tuple[str, ...]] = {
    "reasoning": ("text",),
    "tool_call": ("tool", "arguments"),
    "tool_result": ("tool", "summary"),
    "guardrail": ("text",),
    "error": ("text",),
}


class AgentStep(Contract):
    """Serialize with `model_dump(exclude_none=True)` so each kind carries only its own fields."""

    ref: str
    step: int = Field(ge=1)
    kind: AgentStepKind
    text: Optional[str] = None
    tool: Optional[str] = None
    arguments: Optional[dict[str, Any]] = None
    summary: Optional[str] = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def _fields_for_kind(self) -> "AgentStep":
        required = _STEP_FIELDS[self.kind]
        for name in ("text", "tool", "arguments", "summary"):
            present = getattr(self, name) is not None
            if name in required and not present:
                raise ValueError(f"agent_step kind {self.kind!r} requires {name!r}")
            if name not in required and present:
                raise ValueError(f"agent_step kind {self.kind!r} does not carry {name!r}")
        return self


class PartError(Contract):
    ref: str
    message: str
    fallback: Literal[True] = True


class RunCompleted(Contract):
    run_id: str
    elapsed_ms: int = Field(ge=0)


class ErrorEvent(Contract):
    message: str


SSE_EVENT_MODELS: dict[str, type[Contract]] = {
    "run_started": RunStarted,
    "part_started": PartStarted,
    "agent_step": AgentStep,
    "part_decision": Decision,
    "part_error": PartError,
    "run_completed": RunCompleted,
    "error": ErrorEvent,
}


def validate_event(event: str, data: dict[str, Any]) -> Contract:
    if event not in SSE_EVENT_MODELS:
        raise ValueError(f"unknown SSE event {event!r}")
    return SSE_EVENT_MODELS[event].model_validate(data)


class FixtureEvent(Contract):
    event: str
    data: dict[str, Any]

    @model_validator(mode="after")
    def _data_matches_event(self) -> "FixtureEvent":
        validate_event(self.event, self.data)
        return self


class FixtureRun(Contract):
    """`data/fixtures/demo_run.json`."""

    run_id: str
    mode: Mode
    design_context: DesignContext
    events: list[FixtureEvent]
    decisions: list[Decision]


# ---------------------------------------------------------------- evaluation (4.17)


ApproachName = Literal["naive_baseline", "partswap_rules", "partswap_bolt", "partswap_super"]


class EvalPair(Contract):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    class_: Literal["A", "B", "C", "D", "E", "F"] = Field(alias="class")
    original_mpn: str
    candidate_mpn: str
    description: str
    requirements: Requirements
    expected_verdict: Verdict
    dangerous_if_drop_in: bool


class EvalApproach(Contract):
    name: ApproachName
    accuracy: float = Field(ge=0, le=1)
    false_drop_in_count: int = Field(ge=0)
    model_false_drop_in_count: Optional[int] = None
    tightened_count: Optional[int] = None
    fallback_count: Optional[int] = None
    median_latency_ms: float = Field(ge=0)


class EvalPairResult(Contract):
    id: str
    expected: Verdict
    naive_baseline: Optional[Verdict] = None
    partswap_rules: Optional[Verdict] = None
    partswap_bolt: Optional[Verdict] = None
    partswap_super: Optional[Verdict] = None


class EvalResults(Contract):
    generated_at: str
    pair_count: int = Field(ge=0)
    dangerous_count: int = Field(ge=0)
    prompt_version: str
    approaches: list[EvalApproach]
    per_pair: list[EvalPairResult]
