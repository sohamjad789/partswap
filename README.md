# PartSwap

PartSwap checks whether a catalog part can safely replace a part on your bill of materials. Upload a BOM and a design context (input voltage, temperature range, preferred manufacturer); for each line an agent finds candidates in a local catalog, compares critical specs, package, and pinout against the original part and the circuit, and returns one verdict: `drop_in`, `drop_in_with_caveats`, `needs_redesign`, or `no_safe_match`. Deterministic Python owns unit conversion, threshold checks, and a verdict floor no model can loosen; NVIDIA Nemotron chooses candidates, reads test conditions and datasheet excerpts, tightens verdicts, and writes the explanation. See `PLAN.md` for the full design.

## Prerequisites

- Python 3.11 or 3.12 (not 3.14: PyMuPDF and pdfplumber wheels lag behind)
- Node 20+
- Optional: an NVIDIA API key for `live` mode. `fixture`, `deterministic`, and `cache` modes need no key and no network.

## Setup

```
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env        # then set NVIDIA_API_KEY if you have one
```

## Run

```
uvicorn app.main:app --app-dir backend --port 8000 --reload     # development
uvicorn app.main:app --app-dir backend --port 8000              # demo (no --reload)
cd frontend && npm install && npm run dev                       # http://127.0.0.1:5173
```

Quick check of the backend without the frontend:

```
curl http://127.0.0.1:8000/api/health
curl -N -X POST 'http://127.0.0.1:8000/api/runs?fast=1' -H 'content-type: application/json' \
  -d '{"lines":[],"design_context":{},"mode":"fixture"}'
```

## Test

```
source .venv/bin/activate
pytest -q                   # whole suite; no network, no API key
```

## Model probe

```
python backend/scripts/probe_models.py
```

Checks which Nemotron model IDs answer and support tool calling, and whether the Parse endpoint accepts your key. Results go to `docs/model_probe.md`. Without a key it records "not run" and exits cleanly.

## License

MIT. See `LICENSE`.
