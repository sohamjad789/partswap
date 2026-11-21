import json
import time
from typing import Any, Iterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.paths import data_dir
from app.schemas import DesignContext, FixtureRun, Mode, RunRequest

FIXTURE_DELAY_S = 0.3

app = FastAPI(title="PartSwap")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def sse_response(events: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "mode_default": settings.mode,
        "super_model": settings.super_model,
        "fast_model": settings.fast_model,
        "has_api_key": settings.has_api_key,
    }


@app.get("/api/demo-bom")
def demo_bom() -> dict[str, Any]:
    csv_text = (data_dir() / "bom" / "demo_bom.csv").read_text(encoding="utf-8-sig")
    manifest_path = data_dir() / "demo_manifest.json"
    context = DesignContext()
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        context = DesignContext.model_validate(manifest.get("design_context") or {})
    return {"csv": csv_text, "design_context": context.model_dump(mode="json")}


def stream_fixture(fast: bool) -> Iterator[str]:
    fixture = FixtureRun.model_validate_json((data_dir() / "fixtures" / "demo_run.json").read_text(encoding="utf-8"))
    for i, item in enumerate(fixture.events):
        if i and not fast:
            time.sleep(FIXTURE_DELAY_S)
        yield sse(item.event, item.data)


def stream_error(message: str) -> Iterator[str]:
    yield sse("error", {"message": message})


@app.post("/api/runs")
def create_run(request: RunRequest, fast: int = 0) -> StreamingResponse:
    settings = get_settings()
    mode = request.mode or Mode(settings.mode)
    if mode == Mode.live and not settings.has_api_key:
        return sse_response(stream_error("NVIDIA_API_KEY is not set"))
    if mode != Mode.fixture:
        return sse_response(stream_error(f"Mode '{mode.value}' is not implemented yet; only 'fixture' is available."))
    return sse_response(stream_fixture(fast=bool(fast)))
