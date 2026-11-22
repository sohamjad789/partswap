import json
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app import export, power_tree, runs
from app.config import get_settings
from app.paths import data_dir
from app.power_tree import PowerTreeRequest
from app.schemas import DesignContext, Mode, RunRequest

app = FastAPI(title="PartSwap")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def demo_design_context() -> DesignContext:
    manifest_path = data_dir() / "demo_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return DesignContext.model_validate(manifest.get("design_context") or {})
    return DesignContext()


@app.get("/api/demo-bom")
def demo_bom() -> dict[str, Any]:
    csv_text = (data_dir() / "bom" / "demo_bom.csv").read_text(encoding="utf-8-sig")
    return {"csv": csv_text, "design_context": demo_design_context().model_dump(mode="json")}


@app.post("/api/bom/parse")
async def parse_bom_route(request: Request) -> JSONResponse:
    try:
        from app.bom import parse_bom
    except ImportError:
        raise HTTPException(503, "BOM parser (backend/app/bom.py) has not landed yet.")
    try:
        text = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"errors": [{"row": 1, "message": "File is not UTF-8 text."}]}, status_code=400)
    lines, errors = parse_bom(text)
    if errors:
        return JSONResponse({"errors": [e.model_dump(mode="json") for e in errors]}, status_code=400)
    return JSONResponse({"lines": [line.model_dump(mode="json") for line in lines]})


@app.post("/api/runs")
def create_run(request: RunRequest, fast: int = 0) -> StreamingResponse:
    mode = request.mode or Mode(get_settings().mode)
    return sse_response(runs.stream_run(request.lines, request.design_context, mode, fast=bool(fast)))


def _stored_run_or_404(run_id: str) -> runs.StoredRun:
    stored = runs.get_stored_run(run_id)
    if stored is None:
        raise HTTPException(404, f"Unknown run {run_id}")
    return stored


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _stored_run_or_404(run_id).run.model_dump(mode="json")


@app.get("/api/runs/{run_id}/export/bom.csv")
def export_bom(run_id: str) -> Response:
    stored = _stored_run_or_404(run_id)
    return Response(
        export.bom_csv(stored.run, stored.lines),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="partswap-{run_id}-bom.csv"'},
    )


@app.get("/api/runs/{run_id}/export/risk.md")
def export_risk(run_id: str) -> Response:
    stored = _stored_run_or_404(run_id)
    return Response(
        export.risk_report(stored.run),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="partswap-{run_id}-risk.md"'},
    )


def _load_part_or_404(mpn: str):
    try:
        from app.catalog import load_part
    except ImportError:
        raise HTTPException(503, "Catalog (backend/app/catalog.py) has not landed yet.")
    part = load_part(mpn)
    if part is None:
        raise HTTPException(404, f"Unknown part {mpn}")
    return part


def _datasheet_path(part):
    if not part.datasheet_filename:
        return None
    datasheets = (data_dir() / "datasheets").resolve()
    path = (datasheets / part.datasheet_filename).resolve()
    if path.parent != datasheets or not path.is_file():
        return None
    return path


@app.get("/api/parts/{mpn:path}")
def get_part(mpn: str) -> dict[str, Any]:
    part = _load_part_or_404(mpn)
    return part.model_dump(mode="json") | {"datasheet_available": _datasheet_path(part) is not None}


@app.get("/api/datasheets/{mpn:path}")
def get_datasheet(mpn: str) -> FileResponse:
    path = _datasheet_path(_load_part_or_404(mpn))
    if path is None:
        raise HTTPException(404, f"No local datasheet for {mpn}")
    return FileResponse(path, media_type="application/pdf")


@app.get("/api/eval")
def get_eval() -> dict[str, Any]:
    path = data_dir() / "eval" / "results.json"
    if not path.exists():
        return {"ready": False}
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/power-tree")
def post_power_tree(request: PowerTreeRequest) -> dict[str, Any]:
    return power_tree.propose(request)


@app.get("/api/extract/{mpn:path}")
def get_extract(mpn: str) -> dict[str, Any]:
    part = _load_part_or_404(mpn)
    path = data_dir() / "specs" / "extracted" / f"{part.mpn.replace('/', '_')}.json"
    if not path.exists():
        return {"available": False}
    extracted = json.loads(path.read_text(encoding="utf-8"))
    fields = []
    for key, verified in part.specs.items():
        candidate = extracted.get("specs", {}).get(key, {})
        value = candidate.get("value")
        if value is None:
            status = "missing"
        elif verified.value is not None and abs(value - verified.value) <= max(abs(verified.value), 1e-12) * .02:
            status = "match"
        else:
            status = "mismatch"
        fields.append({"key": key, "verified_raw": verified.raw, "extracted_raw": candidate.get("raw"), "status": status})
    return {"available": True, "parser": extracted.get("parser"), "fields": fields}


@app.post("/api/extract/{mpn:path}")
def post_extract(mpn: str) -> dict[str, Any]:
    _load_part_or_404(mpn)
    from app.extract.pipeline import extract_part
    result = extract_part(mpn)
    if result.get("error"):
        return result
    return get_extract(mpn)
