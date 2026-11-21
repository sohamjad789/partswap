"""Run modes, SSE framing, and the run store (PLAN.md sections 4.1, 4.11, 4.12)."""

import json
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from pydantic import BaseModel

from app.config import get_settings
from app.paths import data_dir
from app.schemas import BomLine, Decision, DesignContext, FixtureRun, Mode, Run, Source, Verdict

FIXTURE_DELAY_S = 0.3
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

Event = tuple[str, dict[str, Any]]


class StoredRun(BaseModel):
    """What `data/cache/runs/{run_id}.json` holds: the public `Run` plus the input lines the exports need."""

    run: Run
    lines: list[BomLine] = []


_store: dict[str, StoredRun] = {}
_store_lock = threading.Lock()


# ---------------------------------------------------------------- SSE framing


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def stream_run(lines: list[BomLine], context: DesignContext, mode: Mode, *, fast: bool = False) -> Iterator[str]:
    for event, data in run_events(lines, context, mode, fast=fast):
        yield sse(event, data)


# ---------------------------------------------------------------- run store


def _runs_dir() -> Path:
    return data_dir() / "cache" / "runs"


def save_run(stored: StoredRun) -> None:
    with _store_lock:
        _store[stored.run.run_id] = stored
    path = _runs_dir() / f"{stored.run.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def get_stored_run(run_id: str) -> Optional[StoredRun]:
    if not RUN_ID_PATTERN.match(run_id):
        return None
    with _store_lock:
        stored = _store.get(run_id)
    if stored is not None:
        return stored
    path = _runs_dir() / f"{run_id}.json"
    if not path.exists():
        return None
    stored = StoredRun.model_validate_json(path.read_text(encoding="utf-8"))
    with _store_lock:
        _store[run_id] = stored
    return stored


def get_run(run_id: str) -> Optional[Run]:
    stored = get_stored_run(run_id)
    return stored.run if stored else None


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- mode dispatch


def run_events(lines: list[BomLine], context: DesignContext, mode: Mode, *, fast: bool = False) -> Iterator[Event]:
    if mode == Mode.live and not get_settings().has_api_key:
        yield "error", {"message": "NVIDIA_API_KEY is not set"}
        return
    if mode == Mode.fixture:
        yield from _fixture_events(lines, fast)
    elif mode == Mode.deterministic:
        yield from _deterministic_events(lines, context)
    elif mode == Mode.live:
        yield from _live_events(lines, context)
    else:
        yield "error", {"message": f"Mode '{mode.value}' is not implemented yet; use 'fixture', 'deterministic', or 'live'."}


def _fixture_events(lines: list[BomLine], fast: bool) -> Iterator[Event]:
    fixture = FixtureRun.model_validate_json((data_dir() / "fixtures" / "demo_run.json").read_text(encoding="utf-8"))
    run_id = _new_run_id()
    started = time.monotonic()
    for i, item in enumerate(fixture.events):
        if i and not fast:
            time.sleep(FIXTURE_DELAY_S)
        data = dict(item.data)
        if item.event == "run_started":
            data["run_id"] = run_id
        elif item.event == "run_completed":
            data = {"run_id": run_id, "elapsed_ms": int((time.monotonic() - started) * 1000)}
            run = Run(
                run_id=run_id,
                created_at=_now_iso(),
                mode=Mode.fixture,
                design_context=fixture.design_context,
                decisions=fixture.decisions,
            )
            save_run(StoredRun(run=run, lines=lines))
        yield item.event, data


def _deterministic_events(lines: list[BomLine], context: DesignContext) -> Iterator[Event]:
    try:
        from app.decide import decide_deterministic
    except ImportError:
        yield "error", {"message": "Deterministic mode needs backend/app/decide.py, which has not landed yet."}
        return

    yield from _decided_events(lines, context, Mode.deterministic,
                               lambda line, emit: decide_deterministic(line, context, emit=emit))


def _live_events(lines: list[BomLine], context: DesignContext) -> Iterator[Event]:
    from app.agent.client import make_client
    from app.agent.loop import run_part

    settings = get_settings()
    client = make_client(settings)
    yield from _decided_events(lines, context, Mode.live,
                               lambda line, emit: run_part(line, context, settings.super_model, emit, client=client))


Decide = Callable[[BomLine, Callable[..., None]], Decision]


def _decided_events(lines: list[BomLine], context: DesignContext, mode: Mode, decide: Decide) -> Iterator[Event]:
    run_id = _new_run_id()
    started = time.monotonic()
    run = Run(run_id=run_id, created_at=_now_iso(), mode=mode, design_context=context, decisions=[])
    yield "run_started", {"run_id": run_id, "part_count": len(lines), "mode": mode.value}
    try:
        for index, line in enumerate(lines):
            yield "part_started", {"ref": line.ref, "mpn": line.mpn, "index": index}
            outcome: list[Any] = []
            yield from _streamed(lambda emit: decide(line, emit), outcome)
            decision, exc = outcome
            if exc is not None:  # one line failing never stops the run
                yield "part_error", {"ref": line.ref, "message": f"{type(exc).__name__}: {exc}", "fallback": True}
                decision = _error_decision(line, exc)
            run.decisions.append(decision)
            yield "part_decision", decision.model_dump(mode="json")
        yield "run_completed", {"run_id": run_id, "elapsed_ms": int((time.monotonic() - started) * 1000)}
    finally:
        save_run(StoredRun(run=run, lines=lines))


def _streamed(work: Callable[[Callable[..., None]], Decision], outcome: list[Any]) -> Iterator[Event]:
    """Run `work(emit)` in a thread and yield its events as they arrive; `outcome` gets `[decision, exception]`."""
    events: queue.Queue = queue.Queue()
    done = object()

    def target() -> None:
        try:
            outcome[:] = [work(_collector(events.put)), None]
        except Exception as exc:
            outcome[:] = [None, exc]
        finally:
            events.put(done)

    threading.Thread(target=target, daemon=True).start()
    while (item := events.get()) is not done:
        yield item


def _collector(sink: Callable[[Event], None]) -> Callable[..., None]:
    """`emit` for Phase 2/5 code. Accepts `emit(event, data)` or `emit(agent_step)` with a dict or model."""

    def emit(*args: Any) -> None:
        event, data = args if len(args) == 2 else ("agent_step", args[0])
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json", exclude_none=True)
        sink((event, data))

    return emit


def _error_decision(line: BomLine, exc: Exception) -> Decision:
    return Decision(
        ref=line.ref,
        original_mpn=line.mpn,
        original_manufacturer=line.manufacturer,
        verdict=Verdict.no_safe_match,
        source=Source.deterministic,
        explanation=f"The deterministic check failed for this line ({type(exc).__name__}). Treat it as unverified.",
    )
