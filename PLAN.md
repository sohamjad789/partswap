# PLAN.md

> **For agentic workers:** Execute **one phase per chat**. Read this file and the repo first. Do not start the next phase. Commit only when the human running your chat asks. Required style: small modules, pytest for the deterministic core, no LangChain, no database.
>
> **Goal:** A local demo of PartSwap, an agent that checks whether a catalog part can replace a BOM part, with Nemotron doing the judgment and deterministic code owning the numbers.
>
> **Architecture:** React UI talks to a FastAPI backend. Specs live in human-verified JSON. A tool-calling loop uses NVIDIA's OpenAI-compatible API. Unit math, pass/fail checks, and the verdict floor are Python. The model picks among candidates, reads test conditions and datasheet excerpts, writes the explanation, and may only make a verdict stricter.
>
> **Tech stack:** Python 3.11 or 3.12, FastAPI, Pydantic v2, openai SDK, httpx, PyMuPDF, pdfplumber, pytest. React 18 + Vite + TypeScript. No component library, no chart library.
>
> **Clock:** Deadline 9:00 PM, Saturday 21 Nov 2026. Work starts 1:00 PM. By **4:00 PM** the browser must run the demo BOM through the real deterministic pipeline (real specs, real checks, real verdicts). The live Nemotron agent must decide one line by **4:30 PM**. The backup video is recorded at 7:30 PM, not in the last half hour.

## 1. Objective

PartSwap is a local web app. An engineer uploads a BOM and a design context. For each line an agent finds candidate replacements in a local catalog, compares critical specs, package, and pinout against the original part and against the design, and returns one verdict: `drop_in`, `drop_in_with_caveats`, `needs_redesign`, or `no_safe_match`. The UI shows a results table, a side-by-side spec comparison, the candidates the agent rejected and why, a streamed reasoning trace, and exports a new BOM plus a risk report.

The demo board is a 24 V industrial I/O node (32 V max input) moving to Diodes Incorporated parts. One run must show:

1. A clean drop-in.
2. A drop-in with caveats.
3. At least one trap: a candidate that matches on headline specs (what a basic cross-reference tool checks) and is rejected for a reason found in the datasheet. The trap is shown as a rejected candidate on the line, next to the part the agent did recommend.
4. An evaluation table: the naive baseline approves dangerous swaps that PartSwap rejects, and Nemotron Super catches context-dependent problems that fixed rules miss.

Division of labor, which is also the Nemotron pitch:

- **Python** converts units, runs threshold checks, and sets a verdict floor that no model output can loosen.
- **Nemotron Super** chooses which candidate to pursue, compares the conditions each value was measured under against this circuit, reads datasheet excerpts, tightens the verdict when the numbers pass but the conditions do not hold, and writes the explanation.
- **Nemotron Bolt** does cheap steps: categorizing unknown parts, structuring extracted datasheet text, and serving as the small-model arm of the evaluation.
- **Nemotron Parse** turns datasheet page images into text and tables for the extraction pipeline.

Working software beats coverage. The demo runs on verified JSON and cached agent runs. Live PDF extraction is shown as a capability and cannot break the demo.

## 2. Repo Instructions / Local Rules

None found. Checked and absent: `.cursor/rules/*.mdc`, `.cursorrules`, `AGENTS.md` / `agents.md`, `CLAUDE.md` / `claude.md`, and any workflow doc other than `README.md`.

`README.md` is a two-line description of a different idea (`tinyml-edge-vs-cloud`). It does not constrain PartSwap, and Phase 0 replaces it. `LICENSE` (MIT, copyright 2026 sohamjad789) and the existing Python `.gitignore` stay. Phase 0 appends to `.gitignore`; it does not rewrite it.

Rules that bind every executor:

- Commit and push only when the human running your chat asks. Never force-push, change git config, or skip hooks.
- The project remote is `origin`, `https://github.com/sohamjad789/tinyml-edge-vs-cloud.git`, branch `main`. The repository name is left over from an earlier idea; PartSwap lives here.
- Datasheet PDFs and `.env` are never committed.
- UI changes are verified in a browser before a phase is called done.

## 3. Current State

Git branch `main`, tracking `origin/main`. Two commits when this plan was written: `947f6c8` "Initial commit" and the commit that added `PLAN.md`.

| Path | What it is |
| --- | --- |
| `README.md` | Title `tinyml-edge-vs-cloud` and one sentence about TinyML benchmarking. No PartSwap content. |
| `LICENSE` | MIT, copyright sohamjad789. |
| `.gitignore` | GitHub Python template. Already ignores `.env`, `.venv`, `__pycache__/`, `.pytest_cache/`. Nothing for Node or datasheets. |
| `PLAN.md` | This file. |

No application code, tests, `package.json`, requirements file, or data exist. Everything below is built from scratch beside those files.

Toolchain on the machine this plan was written on:

- `python3` is **3.14.1**. Do not use it for the venv (PyMuPDF and pdfplumber wheels are the risk).
- `/opt/homebrew/bin/python3.11` exists. Use it. On another machine, any Python 3.11 or 3.12 works.
- Node `v24.18.0`, npm `11.16.0`.

## 4. Architecture

### 4.1 Components

```
Browser (Vite :5173)
  |  REST + SSE over fetch (POST), not EventSource
  v
FastAPI (:8000, backend/app/main.py)
  |-- bom.py            parse CSV -> BomLine[]
  |-- catalog.py        load catalog + verified PartSpec JSON
  |-- units.py          "3V3", "3300 mV", "-40 to 125°C" -> SI numbers
  |-- compare.py        evaluate_pair: per-spec pass / fail / caveat / unknown
  |-- package.py        package code + pin-function comparison
  |-- headline.py       what a naive cross-reference checks
  |-- verdict.py        verdict floor + candidate ranking
  |-- decide.py         build the Decision record; deterministic pipeline
  |-- agent/            Nemotron tool loop (uses everything above)
  |-- runs.py           modes, SSE stream, cache, run store
  |-- extract/          PDF -> page text -> structured specs (offline)
  \-- eval/             labeled pairs -> results.json (offline)

data/              verified JSON (committed), PDFs and caches (gitignored)
shared/examples/   contract payloads, validated by pytest
```

Rules that keep the lanes independent:

- Deterministic modules never import the OpenAI client. The agent imports them, not the other way round.
- The frontend speaks only HTTP and uses the field names in this section.
- Every numeric spec value shown in the UI comes from `evaluate_pair`, never from model text.
- The model can tighten a verdict and cannot loosen one. Order, most to least permissive: `drop_in` > `drop_in_with_caveats` > `needs_redesign` > `no_safe_match`.

Run modes (all emit the same SSE event shapes):

| Mode | What runs | Needs API key |
| --- | --- | --- |
| `fixture` | Replays `data/fixtures/demo_run.json`. | No |
| `deterministic` | Real pipeline without a model: search, `evaluate_pair` on every candidate, rank, decide. Works on any uploaded BOM. | No |
| `cache` | Replays the cached live-agent run for each line. A line with no cache entry runs `deterministic`. It never falls through to `live`. | No |
| `live` | Nemotron tool loop. Writes the cache. On failure a line falls back to the deterministic decision. | Yes |

### 4.2 Folder structure

Create exactly this layout. No `src/` at the repo root, no database, no second backend.

```
PLAN.md  README.md  LICENSE  .gitignore  .env.example  pytest.ini
shared/examples/                  # JSON payloads from this section
data/categories.json              # comparison policy
data/package_aliases.json
data/pin_functions.json
data/topics.json
data/demo_manifest.json           # expected outcomes for the demo BOM (never shown to the agent)
data/catalog.json
data/bom/demo_bom.csv
data/specs/{MPN}.json             # one verified PartSpec per file
data/specs/extracted/             # gitignored, pipeline output
data/excerpts/{MPN}.json          # short page-text chunks for retrieval
data/fixtures/demo_run.json       # recorded run, replayable with no network
data/eval/pairs.json
data/eval/results.json            # generated
data/eval/extraction_report.json  # generated
data/datasheets/SOURCES.md        # URLs only
data/datasheets/*.pdf             # gitignored
data/cache/                       # gitignored
docs/model_probe.md  docs/nemotron.md  docs/demo_script.md
backend/requirements.txt
backend/app/{__init__,main,config,paths,schemas}.py
backend/app/{units,bom,catalog,requirements_build,compare,package,headline,verdict,decide,candidates,excerpts,categorize,runs,export}.py
backend/app/agent/{__init__,client,prompts,tools,loop}.py
backend/app/extract/{__init__,pdf_pages,parse_api,structure,pipeline}.py
backend/app/eval/{__init__,run_eval}.py
backend/scripts/{probe_models,record_fixture,build_excerpts,extraction_report}.py
backend/tests/
frontend/{package.json,vite.config.ts,index.html}
frontend/src/{main.tsx,App.tsx,api.ts,types.ts,styles.css}
frontend/src/components/{BomForm,ResultsTable,PartDetail,AgentTrace,EvalPanel}.tsx
```

`backend/app/paths.py` exposes `repo_root()` (parent of `backend/`) and `data_dir()`. `PARTSWAP_DATA_DIR` is resolved against `repo_root()` when it is relative. No module opens a path relative to the process cwd.

### 4.3 BOM input

CSV, comma-separated, UTF-8. A leading UTF-8 byte-order mark is stripped. Header names are matched case-insensitively after trimming spaces.

Required columns: `ref`, `manufacturer`, `mpn`, `qty`. Optional: `description`.

Optional requirement columns (circuit requirements for that line):

```
req_vin_max_v,req_vout_v,req_iout_a,req_temp_min_c,req_temp_max_c,req_vrrm_v,req_vds_v,req_vgs_v,req_vrwm_v,req_headroom_vin_v,req_esd_contact_kv,req_c_max_pf
```

Requirement cells are parsed with `units.parse_quantity`, so `3.3`, `3V3`, `3300mV`, and `500mA` are all accepted. A bare number is taken in the column's unit (the key suffix); a value with a unit is converted to the column's unit (`8kV` → 8 in `req_esd_contact_kv`, `15pF` → 15 in `req_c_max_pf`). A cell that fails to parse is a row error.

`qty` is a positive integer. `ref` is unique. `mpn` is matched to the catalog case-insensitively and stored in the catalog's spelling.

Example `data/bom/demo_bom.csv` (the first two demo lines; Phase 1 owns the final file):

```csv
ref,manufacturer,mpn,qty,description,req_vin_max_v,req_vout_v,req_iout_a,req_temp_min_c,req_temp_max_c,req_vrrm_v,req_vds_v,req_vgs_v,req_vrwm_v,req_headroom_vin_v,req_esd_contact_kv,req_c_max_pf
D1,onsemi,MBR0540T1G,1,Reverse-polarity Schottky on the 24 V input,,,0.5,,,32,,,,,,
U2,Microchip,MCP1700-3302E/TT,1,3.3 V LDO for the MCU fed from the 5 V rail,5.5,3.3,0.15,,,,,,,5,,
```

Every row has exactly 17 fields. A row with a different field count is a row error.

Reject the file (HTTP 400, no run) when: it is empty; a required column is missing; a row has the wrong field count; `ref` or `mpn` is blank; `qty` is not a positive integer; `ref` repeats; a requirement cell does not parse. The error body is `{errors: [{row, message}]}` where `row` is the 1-based line number in the file.

An MPN that is not in the catalog does **not** reject the file. That line becomes `no_safe_match` during the run. Extra columns are ignored.

### 4.4 Design context and requirements

```json
{
  "input_voltage_v": 24.0,
  "input_voltage_max_v": 32.0,
  "operating_temp_min_c": -40,
  "operating_temp_max_c": 85,
  "preferred_manufacturer": "Diodes Incorporated",
  "goal": "lowest_risk"
}
```

`goal` is `lowest_risk` (default), `lowest_cost`, or `shortest_lead_time`. Default `preferred_manufacturer` is `Diodes Incorporated`.

There is no board-level current. Current is per line (`req_iout_a`) because a signal MOSFET and a buck converter do not share a current.

`build_requirements(line, context) -> Requirements` in `requirements_build.py` produces one object per line with these fields, each a float or null: `input_voltage_v`, `req_vin_max_v`, `req_vout_v`, `req_iout_a`, `req_temp_min_c`, `req_temp_max_c`, `req_vrrm_v`, `req_vds_v`, `req_vgs_v`, `req_vrwm_v`, `req_headroom_vin_v`, `req_esd_contact_kv`, `req_c_max_pf`.

| Field | Empty cell means |
| --- | --- |
| `req_temp_min_c`, `req_temp_max_c` | Inherit the design context's operating range. |
| `input_voltage_v` | Always copied from the design context. |
| every other field | Null. The check then compares the candidate against the **original part's** value: the candidate must be at least as capable. |

Two fields deliberately do not inherit the board input: `req_vin_max_v` (a 3.3 V LDO behind a 5 V rail must not be asked to survive 32 V) and `req_headroom_vin_v` (the voltage actually present at an LDO's input). Lines that need them set them in the CSV.

### 4.5 Part spec schema

File `data/specs/{MPN}.json`. In the filename only, `/` becomes `_` (`MCP1700-3302E/TT` → `MCP1700-3302E_TT.json`).

```json
{
  "mpn": "B0540W-7-F",
  "manufacturer": "Diodes Incorporated",
  "category": "schottky",
  "description": "40 V 0.5 A Schottky, SOD-123",
  "datasheet_filename": "B0540W.pdf",
  "package": {"code": "SOD-123", "pins": 2, "page": 1},
  "pinout": [
    {"pin": 1, "name": "K", "functions": ["cathode"]},
    {"pin": 2, "name": "A", "functions": ["anode"]}
  ],
  "pinout_page": 1,
  "polarity": null,
  "diode_count": 1,
  "channel_count": null,
  "topology": null,
  "output_type": null,
  "unit_price_usd": null,
  "lead_time_weeks": null,
  "verified": true,
  "synthetic": false,
  "specs": {
    "vrrm_v":     {"value": 40,      "raw": "40 V",    "condition": "peak repetitive reverse voltage", "page": 2, "table": "Maximum Ratings"},
    "if_avg_a":   {"value": 0.5,     "raw": "0.5 A",   "condition": "average rectified output current", "page": 2, "table": "Maximum Ratings"},
    "vf_v":       {"value": 0.51,    "raw": "0.510 V", "condition": "max, IF = 0.5 A, TJ = 25 °C", "page": 2, "table": "Electrical Characteristics"},
    "ir_a":       {"value": 0.00002, "raw": "20 µA",   "condition": "max, VR = 40 V, TJ = 25 °C", "page": 2, "table": "Electrical Characteristics"},
    "temp_min_c": {"value": -65,     "raw": "-65 °C",  "condition": "junction", "page": 2, "table": "Thermal Characteristics"},
    "temp_max_c": {"value": 150,     "raw": "+150 °C", "condition": "junction", "page": 2, "table": "Thermal Characteristics"}
  }
}
```

The values above are from a web search of the B0540W datasheet, not from a human check of the PDF. Phase 1 re-verifies them, including the pin numbering, before `verified` stays true.

- `SpecField.value` is a number already converted to the unit named by the key suffix (`_v` volts, `_a` amps, `_ohm` ohms, `_hz` hertz, `_c` Celsius, `_pf` picofarads, `_kv` kilovolts). `raw` is the datasheet text. `condition` is the test condition as printed and is required; the agent reasons over it. `page` is 1-based.
- A missing key and `"value": null` mean the same thing: the comparison result is `unknown`, never `pass`.
- `temp_min_c` / `temp_max_c` hold the operating range the datasheet gives, ambient if stated, otherwise junction. `condition` says which.
- `pinout[].functions` is the authoritative, human-entered function list using the tokens in section 4.6. `name` is the datasheet's label and is for display.
- `category`: `ldo`, `buck`, `schottky`, `mosfet`, `esd`.
- `polarity`: `n` / `p` for MOSFETs; `unidirectional` / `bidirectional` for ESD; else null.
- `output_type`: `fixed` / `adjustable` for LDO and buck. `topology`: `synchronous` / `asynchronous` for buck. `diode_count`: int for Schottky. `channel_count`: int for ESD.
- `synthetic: true` marks an invented part used only in the evaluation. Its MPN starts with `SYN-`. Synthetic parts never appear in a demo BOM line's search results (section 4.7).
- Prices and lead times may be null. Do not scrape distributors.

### 4.6 Comparison policy

`data/categories.json` is the single source of thresholds. `compare.py` reads it and hardcodes none. Phase 0 writes it verbatim:

```json
{
  "ldo": {"checks": [
    {"key": "output_type",   "where": "root",  "rule": "enum_equal",      "on_fail": "needs_redesign", "on_unknown": "no_safe_match"},
    {"key": "vout_v",        "where": "specs", "rule": "relative_match",  "tolerance": 0.02, "required_from": "req_vout_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vin_abs_max_v", "where": "specs", "rule": "candidate_gte",   "required_from": "req_vin_max_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vin_max_v",     "where": "specs", "rule": "candidate_gte",   "required_from": "req_vin_max_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vin_min_v",     "where": "specs", "rule": "candidate_lte",   "required_from": "req_headroom_vin_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "iout_max_a",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_iout_a", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "dropout_v",     "where": "specs", "rule": "dropout_fits",    "caveat_abs": 0.05, "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "iq_a",          "where": "specs", "rule": "not_worse_ratio", "ratio": 2.0, "on_unknown": "caveat"},
    {"key": "temp_min_c",    "where": "specs", "rule": "candidate_lte",   "required_from": "req_temp_min_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "temp_max_c",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_temp_max_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"}
  ]},
  "buck": {"checks": [
    {"key": "output_type",   "where": "root",  "rule": "enum_equal",      "on_fail": "needs_redesign", "on_unknown": "no_safe_match"},
    {"key": "topology",      "where": "root",  "rule": "enum_equal",      "on_fail": "needs_redesign", "on_unknown": "no_safe_match"},
    {"key": "vin_min_v",     "where": "specs", "rule": "candidate_lte",   "required_from": "input_voltage_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vin_max_v",     "where": "specs", "rule": "candidate_gte",   "required_from": "req_vin_max_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vout_v",        "where": "specs", "rule": "relative_match",  "tolerance": 0.02, "required_from": "req_vout_v", "only_when_output_type": "fixed", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "iout_max_a",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_iout_a", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "fsw_hz",        "where": "specs", "rule": "within_ratio",    "ratio": 2.0, "on_unknown": "caveat"},
    {"key": "iq_a",          "where": "specs", "rule": "not_worse_ratio", "ratio": 2.0, "on_unknown": "caveat"},
    {"key": "temp_min_c",    "where": "specs", "rule": "candidate_lte",   "required_from": "req_temp_min_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "temp_max_c",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_temp_max_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"}
  ]},
  "schottky": {"checks": [
    {"key": "diode_count",   "where": "root",  "rule": "enum_equal",      "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vrrm_v",        "where": "specs", "rule": "candidate_gte",   "required_from": "req_vrrm_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "if_avg_a",      "where": "specs", "rule": "candidate_gte",   "required_from": "req_iout_a", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vf_v",          "where": "specs", "rule": "worse_by_abs",    "caveat_abs": 0.1, "on_unknown": "caveat"},
    {"key": "ir_a",          "where": "specs", "rule": "not_worse_ratio", "ratio": 5.0, "on_unknown": "caveat"},
    {"key": "temp_min_c",    "where": "specs", "rule": "candidate_lte",   "required_from": "req_temp_min_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "temp_max_c",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_temp_max_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"}
  ]},
  "mosfet": {"checks": [
    {"key": "polarity",      "where": "root",  "rule": "enum_equal",      "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vds_max_v",     "where": "specs", "rule": "candidate_gte",   "required_from": "req_vds_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "id_max_a",      "where": "specs", "rule": "candidate_gte",   "required_from": "req_iout_a", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vgs_max_v",     "where": "specs", "rule": "candidate_gte",   "required_from": null, "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vgs_th_max_v",  "where": "specs", "rule": "vgs_th_drive",    "required_from": "req_vgs_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "rds_on_ohm",    "where": "specs", "rule": "rds_on",          "caveat_ratio": 1.5, "fail_ratio": 3.0, "on_fail": "no_safe_match", "on_unknown": "caveat"},
    {"key": "temp_min_c",    "where": "specs", "rule": "candidate_lte",   "required_from": "req_temp_min_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "temp_max_c",    "where": "specs", "rule": "candidate_gte",   "required_from": "req_temp_max_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"}
  ]},
  "esd": {"checks": [
    {"key": "polarity",       "where": "root",  "rule": "enum_equal",      "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "channel_count",  "where": "root",  "rule": "candidate_gte",   "required_from": null, "on_fail": "needs_redesign", "on_unknown": "no_safe_match"},
    {"key": "vrwm_v",         "where": "specs", "rule": "candidate_gte",   "required_from": "req_vrwm_v", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "esd_contact_kv", "where": "specs", "rule": "candidate_gte",   "required_from": "req_esd_contact_kv", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "vc_v",           "where": "specs", "rule": "not_worse_ratio", "ratio": 1.2, "on_unknown": "caveat"},
    {"key": "c_pf",           "where": "specs", "rule": "esd_c",           "required_from": "req_c_max_pf", "on_fail": "no_safe_match", "on_unknown": "caveat"},
    {"key": "temp_min_c",     "where": "specs", "rule": "candidate_lte",   "required_from": "req_temp_min_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"},
    {"key": "temp_max_c",     "where": "specs", "rule": "candidate_gte",   "required_from": "req_temp_max_c", "on_fail": "no_safe_match", "on_unknown": "no_safe_match"}
  ]}
}
```

Each check produces `pass`, `fail`, `caveat`, `unknown`, or `skip`.

| Rule | Behavior |
| --- | --- |
| `candidate_gte` / `candidate_lte` | Compare the candidate value to the target. Target is the requirement named by `required_from`; if that is null, the original part's value. |
| `relative_match` | Pass when `abs(candidate - target) / target <= tolerance`. Same target rule. Skipped when `only_when_output_type` does not equal the original's `output_type`. |
| `enum_equal` | Python `==` on the two root values. |
| `not_worse_ratio` | For lower-is-better values. Pass when `candidate <= original * ratio`, else `caveat`. |
| `within_ratio` | Pass when `max(c, o) / min(c, o) <= ratio`, else `caveat`. |
| `worse_by_abs` | Pass when `candidate <= original + caveat_abs`, else `caveat`. |
| `dropout_fits` | `fail` when both `req_headroom_vin_v` and `req_vout_v` are set and `candidate > req_headroom_vin_v - req_vout_v`. Otherwise `caveat` when `candidate > original + caveat_abs`, else `pass`. |
| `rds_on` | Ratio `r = candidate / original`. `pass` when `r <= caveat_ratio`, `caveat` when `r <= fail_ratio`, else `fail`. |
| `vgs_th_drive` | `skip` when `req_vgs_v` is null. Otherwise `fail` when `candidate > req_vgs_v`. |
| `esd_c` | `fail` when `req_c_max_pf` is set and `candidate > req_c_max_pf`. Otherwise `caveat` when `candidate > original * 2`, else `pass`. |

`unknown` is the result whenever a value the rule needs is null or missing (the candidate's, or the original's when the original is the target). Do not treat `unknown` as `pass` and do not treat `skip` as `fail`.

**Package and pinout.** `check_package_pinout(original, candidate)` in `package.py` returns:

```json
{"package": {"original": "SOT-23-3", "candidate": "SOT-23-3", "result": "pass"},
 "pinout": {"original": {"1": ["ground"], "2": ["power_out"], "3": ["power_in"]},
            "candidate": {"1": ["power_in"], "2": ["power_out"], "3": ["ground"]},
            "result": "fail"},
 "detail": "Same SOT-23-3 package. Pin 1 is ground on the original and power_in on the candidate; pin 3 is power_in on the original and ground on the candidate."}
```

- Package: `pass` when `normalize_package(code)` is equal, else `fail`.
- Pinout: `pass` when both parts have the same pin numbers and, for each pin number, the same set of function tokens. Any difference is `fail`. A missing pinout or a `unknown` token on either part is `unknown`.
- `normalize_package`: uppercase, remove spaces, remove a trailing parenthetical such as `(DBV)`, then look up `data/package_aliases.json`. A code not in the table is kept as is.

`data/package_aliases.json` (write verbatim; punctuation variants only):

```json
{
  "SOD123": "SOD-123", "SOD-123": "SOD-123",
  "SOT23": "SOT-23-3", "SOT-23": "SOT-23-3", "SOT23-3": "SOT-23-3", "SOT-23-3": "SOT-23-3", "SOT23R": "SOT-23-3",
  "SOT23-5": "SOT-23-5", "SOT-23-5": "SOT-23-5", "SOT25": "SOT-23-5",
  "SOT23-6": "SOT-23-6", "SOT-23-6": "SOT-23-6", "SOT26": "SOT-23-6",
  "SOT223": "SOT-223", "SOT-223": "SOT-223",
  "SMA": "SMA", "SMB": "SMB"
}
```

`SOT23R` is Diodes' name for a SOT-23 body with a different pin assignment. The body is the same, so it maps to `SOT-23-3` and the pinout check carries the difference. Never add an alias between different bodies: TSOT-23, SC-70, SOT-323, SOD-123F/W, and PowerDI are not aliases of anything.

Function tokens for `pinout[].functions`: `ground`, `power_in`, `power_out`, `enable_active_high`, `enable_active_low`, `nc`, `gate`, `drain`, `source`, `anode`, `cathode`, `io`, `feedback`, `bypass`, `switch`, `bootstrap`, `power_good`, `unknown`.

`data/pin_functions.json` maps a datasheet pin label to a token. It is used by the extraction pipeline and by a data validation test, not by the comparison. Lookup is exact after uppercasing and removing spaces; there is no prefix logic (so `NC` can never be read as "active-low C"). Write verbatim:

```json
{
  "GND": "ground", "VSS": "ground", "GROUND": "ground",
  "IN": "power_in", "VIN": "power_in", "VCC": "power_in", "VDD": "power_in",
  "OUT": "power_out", "VOUT": "power_out",
  "EN": "enable_active_high", "ENABLE": "enable_active_high", "CE": "enable_active_high",
  "/EN": "enable_active_low", "NEN": "enable_active_low", "EN#": "enable_active_low",
  "SHDN": "enable_active_low", "/SHDN": "enable_active_low", "NSHDN": "enable_active_low",
  "NC": "nc", "N/C": "nc", "DNC": "nc",
  "G": "gate", "GATE": "gate", "D": "drain", "DRAIN": "drain", "S": "source", "SOURCE": "source",
  "A": "anode", "ANODE": "anode", "K": "cathode", "C": "cathode", "CATHODE": "cathode",
  "IO": "io", "I/O": "io",
  "ADJ": "feedback", "FB": "feedback", "VFB": "feedback",
  "BYP": "bypass", "BP": "bypass", "NR": "bypass",
  "SW": "switch", "LX": "switch", "BST": "bootstrap", "BOOT": "bootstrap", "CB": "bootstrap",
  "PG": "power_good", "PGOOD": "power_good"
}
```

**`evaluate_pair(original, candidate, requirements) -> Comparison`** in `compare.py` runs the category checks, then appends two checks built from `check_package_pinout`: `spec: "package"` and `spec: "pinout"`, both with `on_fail: "needs_redesign"` and `on_unknown: "no_safe_match"`. It sets `suggested_verdict`. This is the only comparison function; the agent tool `compare_specs` calls it.

```json
{
  "original_mpn": "MBR0540T1G",
  "candidate_mpn": "B0520LW-7-F",
  "category": "schottky",
  "checks": [
    {
      "spec": "vrrm_v",
      "result": "fail",
      "on_fail": "no_safe_match",
      "requirement": ">= 32 V (line requirement)",
      "original": {"value": 40, "raw": "40 V", "condition": "peak repetitive reverse voltage", "page": 1},
      "candidate": {"value": 20, "raw": "20 V", "condition": "peak repetitive reverse voltage", "page": 2},
      "reason": "candidate 20 V is below the required 32 V"
    }
  ],
  "suggested_verdict": "no_safe_match",
  "headline_match": true
}
```

**`suggest_verdict(comparison) -> str`** in `verdict.py`, first match wins:

1. Any `fail` whose `on_fail` is `no_safe_match`, or any `unknown` whose `on_unknown` is `no_safe_match` → `no_safe_match`. An unverified critical rating is not a safe match.
2. Any `fail` whose `on_fail` is `needs_redesign` → `needs_redesign`.
3. Any `caveat`, or any `unknown` whose `on_unknown` is `caveat` → `drop_in_with_caveats`.
4. Otherwise → `drop_in`.

**`headline_match(original, candidate) -> bool`** in `headline.py` is the naive cross-reference. It reads only these fields:

| Category | True when |
| --- | --- |
| ldo | `vout_v` within 5 %, candidate `iout_max_a` >= original, package equal |
| buck | candidate `iout_max_a` >= original, candidate `vin_max_v` >= original, package equal |
| schottky | candidate `if_avg_a` >= 0.8 × original, package equal. Does not read `vrrm_v`. |
| mosfet | candidate `vds_max_v` and `id_max_a` >= original, package equal. Does not read pinout or `vgs_th_max_v`. |
| esd | candidate `vrwm_v` >= original, package equal. Does not read direction or capacitance. |

It never reads pinout, requirements, or conditions. A null in a field it reads makes it false.

**`rank_candidates(comparisons, context) -> list[Comparison]`** in `verdict.py`: sort by verdict (best first), then by goal:

- `lowest_risk`: fewer `caveat` + `unknown` checks, then preferred manufacturer, then MPN.
- `lowest_cost`: lower `unit_price_usd` (nulls last), then the `lowest_risk` order.
- `shortest_lead_time`: lower `lead_time_weeks` (nulls last), then the `lowest_risk` order.

### 4.7 Catalog and search

`data/catalog.json` is an array of `{mpn, manufacturer, category, description, spec_file}`; `spec_file` is relative to `data/`. The spec file is the source of truth.

`search_candidates(category, preferred_manufacturer, original_mpn, include_synthetic=False, limit=8) -> list[PartSpec]` in `candidates.py`:

- Same category, `verified` true, not the original.
- `synthetic` parts are excluded unless `include_synthetic` is true (only the evaluation sets it).
- **No electrical filtering.** A part that fails Vrrm must still be returned, or the agent never sees the trap a naive tool would approve.
- Sort: preferred manufacturer first (case-insensitive), then MPN. Truncate to `limit`.

### 4.8 Decision record

`build_decision(...)` in `decide.py` is the one place a `Decision` is assembled. Both the deterministic pipeline and the agent's `record_decision` call it, so the numbers are identical in every mode.

```json
{
  "ref": "D1",
  "original_mpn": "MBR0540T1G",
  "original_manufacturer": "onsemi",
  "recommended_mpn": "B0540W-7-F",
  "recommended_manufacturer": "Diodes Incorporated",
  "compared_mpn": "B0540W-7-F",
  "verdict": "drop_in",
  "model_verdict": "drop_in",
  "tightened": false,
  "confidence": 0.9,
  "source": "model",
  "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
  "spec_checks": [],
  "package_pinout": {"package_result": "pass", "pinout_result": "pass", "detail": "Same SOD-123 package and pin functions."},
  "caveats": [],
  "explanation": "B0540W-7-F matches the 40 V / 0.5 A rating in the same SOD-123 package (datasheet p.2). B0520LW-7-F and B0530W-7-F share the package and current rating but block only 20 V and 30 V, below the 32 V this input can reach.",
  "rejected": [
    {"mpn": "B0520LW-7-F", "manufacturer": "Diodes Incorporated", "verdict": "no_safe_match", "reason": "vrrm_v: candidate 20 V is below the required 32 V", "headline_match": true},
    {"mpn": "B0530W-7-F", "manufacturer": "Diodes Incorporated", "verdict": "no_safe_match", "reason": "vrrm_v: candidate 30 V is below the required 32 V", "headline_match": true}
  ],
  "candidates_considered": ["B0520LW-7-F", "B0530W-7-F", "B0540W-7-F"]
}
```

- `compared_mpn` is the candidate the verdict is about. `spec_checks` and `package_pinout` are always `evaluate_pair(original, compared_mpn)`.
- `recommended_mpn` equals `compared_mpn` unless the verdict is `no_safe_match`, in which case it is null. `needs_redesign` keeps the recommendation so the engineer sees the closest part.
- `rejected` lists every other searched candidate whose floor verdict is `needs_redesign` or `no_safe_match`, with `reason` = `"{spec}: {reason}"` of its first failing check and `headline_match` from `headline.py`. A rejected candidate with `headline_match: true` is a trap a basic cross-reference would have approved. This list is computed in Python for every candidate, whether or not the model looked at it.
- `model_verdict` is what the model asked for before the guardrail; null when no model was involved. `tightened` is true when the guardrail changed it.
- `source`: `model`, `deterministic`, or `deterministic_fallback` (live mode failed for this line).
- `confidence` is the model's 0–1 value, capped at 0.6 when `tightened`. Null when no model was involved.
- No candidates in the category: `verdict: no_safe_match`, `compared_mpn: null`, empty `spec_checks`, explanation `No candidate in the local catalog for this category.` MPN not in the catalog: same, with explanation `{mpn} is not in the local catalog.`

Deterministic pipeline, `decide_deterministic(line, context, emit) -> Decision` in `decide.py`: resolve requirements, search, `evaluate_pair` every candidate, `rank_candidates`, take the first as `compared_mpn`, build the decision with `source: deterministic` and a templated explanation (`{verdict label}: {compared_mpn}. {first caveat or failing reason, if any}`). It calls `emit` with the same `agent_step` events the live loop produces (`search_candidates`, then one `compare_specs` per candidate).

### 4.9 Agent tools

Executed locally. The model never receives a PDF or a whole datasheet.

| Tool | Arguments | Returns |
| --- | --- | --- |
| `get_bom_line` | `ref` | The line plus resolved `Requirements`. |
| `get_part_specs` | `mpn` | The `PartSpec`, or `{error: "unknown_mpn"}`. |
| `search_candidates` | `category`, `preferred_manufacturer`, `original_mpn` | `{candidates: [{mpn, manufacturer, package_code, description}]}`. No spec values. |
| `get_datasheet_excerpt` | `mpn`, `topic` | `{mpn, topic, chunks: [{page, text}]}`, at most 2 chunks and 1500 characters. `topic` is `pinout`, `absolute_maximum`, `electrical`, `thermal`, or `application`. No data: `{error: "no_excerpt"}`. |
| `compare_specs` | `original_mpn`, `candidate_mpn`, `ref` | The `Comparison` from `evaluate_pair`, including package and pinout checks and each value's `condition`. Reloads specs from disk; ignores any numbers the model passes. |
| `check_package_pinout` | `original_mpn`, `candidate_mpn` | The object in section 4.6. |
| `record_decision` | `ref`, `candidate_mpn`, `verdict`, `confidence`, `caveats`, `explanation` | The stored `Decision`. Terminal for that line. `candidate_mpn` is null only when search returned nothing. |

Guardrails inside `record_decision` (`agent/tools.py`), in order:

1. `verdict` not one of the four values, or `candidate_mpn` not in this line's search results → tool error (`invalid_verdict` / `unknown_candidate`). The model may correct itself once; a second error triggers the deterministic fallback.
2. If the model never called `compare_specs` on a candidate whose floor verdict is better than the verdict it is recording → tool error once: `You have not compared {mpn}. Compare it before deciding.` A second attempt is accepted as given.
3. Compute `floor = suggest_verdict(evaluate_pair(original, candidate))`.
4. If the model's verdict is more permissive than `floor`, store `floor`, set `tightened: true`, add the caveat `Verdict tightened by deterministic check: {reason}`. A stricter model verdict is kept.
5. Call `build_decision`. Spec numbers come from step 3, never from the model.

### 4.10 Agent loop

`run_part(line, context, model_id, emit, only_candidates=None) -> Decision` in `agent/loop.py`.

- The first user message carries the context so the model does not spend turns fetching it:

  ```
  Verify a replacement for BOM line {ref}.
  Line: {line JSON}
  Resolved requirements: {requirements JSON}
  Original part: {mpn}, {manufacturer}, category {category}, package {package code}
  Goal: {goal}. Preferred manufacturer: {preferred_manufacturer}.
  Start with search_candidates. Finish by calling record_decision exactly once.
  ```

- Max 10 model turns per line. Line wall-clock budget 150 seconds. Exceeding either triggers the fallback.
- Execute every tool call in an assistant message, in order, up to 4; return one `role: tool` message per call with the matching `tool_call_id`, immediately after the assistant message. Calls beyond 4 get `{error: "too_many_calls"}`. If `record_decision` appears with other calls, run it last.
- Client: `OpenAI(base_url=..., api_key=..., timeout=60, max_retries=0)`. The loop does its own retries: 429 and 5xx retry three times with 1 s, 2 s, 4 s waits. A 400 is not retried.
- `finish_reason == "length"` with no tool call: retry that turn once with thinking disabled.
- Invalid JSON arguments or an unknown tool name: return `{error: "invalid_arguments"}` or `{error: "unknown_tool"}`. Two consecutive errors of the same kind trigger the fallback.
- A turn with neither tool calls nor content: one retry, then fallback.
- If the response has no `tool_calls` but `content` contains a JSON object with a known tool `name` and valid `arguments`, accept it as a tool call. At most once per line.
- If `message.reasoning_content` is present, emit it as an `agent_step` of kind `reasoning` (first 500 characters). Do not send it back to the model.
- Fallback: `decide_deterministic`, stored with `source: deterministic_fallback`. One line failing never stops the run.
- `only_candidates` restricts search results to the given MPNs and sets `include_synthetic=True`. Only the evaluation uses it.

Categorizing: a catalog MPN uses the catalog category, no model call. For an MPN not in the catalog the line is `no_safe_match` (section 4.8) and the fast model is called once with `CATEGORY_PROMPT` only to label the part's category in the explanation; if that call fails the label is omitted.

### 4.11 Streaming events

`POST /api/runs` returns `text/event-stream`. Implement it as a **sync generator** in a `StreamingResponse` (FastAPI runs it in a thread pool) and use the sync OpenAI client. Do not mix in asyncio. The frontend reads it with `fetch` and a stream reader; `EventSource` cannot POST.

```
event: agent_step
data: {"ref":"D1","step":2,"kind":"tool_call","tool":"compare_specs","arguments":{"original_mpn":"MBR0540T1G","candidate_mpn":"B0520LW-7-F","ref":"D1"}}

```

A blank line ends each event. `data` is one line of JSON.

| Event | Data |
| --- | --- |
| `run_started` | `{run_id, part_count, mode}` |
| `part_started` | `{ref, mpn, index}` |
| `agent_step` | `{ref, step, kind, ...}` |
| `part_decision` | the `Decision` |
| `part_error` | `{ref, message, fallback: true}` (always followed by a `part_decision`) |
| `run_completed` | `{run_id, elapsed_ms}` |
| `error` | `{message}`, then the stream ends |

`agent_step.kind`:

| Kind | Extra fields |
| --- | --- |
| `reasoning` | `text` |
| `tool_call` | `tool`, `arguments` |
| `tool_result` | `tool`, `summary` (one string, max 240 characters; for `compare_specs`: `"{candidate}: {suggested_verdict}; {n} fail, {n} caveat"`) |
| `guardrail` | `text` (for example the tightening message) |
| `error` | `text` |

Cache: key = SHA-256 of canonical JSON (sorted keys, no whitespace) of `{line, design_context, model_id, prompt_version}`. `PROMPT_VERSION` is a constant in `agent/prompts.py`, bumped on every prompt edit. File `data/cache/decisions/{hash}.json` = `{key, decision, events}`. Written after every live line, including fallbacks. Changing any spec JSON does not change the key, so delete `data/cache/` after spec edits.

`data/fixtures/demo_run.json` = `{run_id, mode, design_context, events: [{event, data}], decisions}`. It is **recorded**, not hand-written (`backend/scripts/record_fixture.py`), except for the three-line starter Phase 0 writes. `fixture` mode sleeps 300 ms between events unless the query string has `fast=1`.

### 4.12 HTTP API

Backend `http://127.0.0.1:8000`, frontend `http://127.0.0.1:5173`. Vite proxies `/api` to the backend. CORS allows `http://127.0.0.1:5173` and `http://localhost:5173`.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/health` | `{status: "ok", mode_default, super_model, fast_model, has_api_key}` |
| GET | `/api/demo-bom` | `{csv, design_context}`. `design_context` comes from `data/demo_manifest.json`, or the section 4.4 example when the manifest does not exist yet. |
| POST | `/api/bom/parse` | Body `text/csv`. `200 {lines}` or `400 {errors}`. |
| POST | `/api/runs` | JSON `{lines, design_context, mode}`. SSE. `mode` defaults to `PARTSWAP_MODE`. `live` without a key → SSE `error` with `NVIDIA_API_KEY is not set`. |
| GET | `/api/runs/{run_id}` | `{run_id, created_at, mode, design_context, decisions}`. Read from memory, else from `data/cache/runs/{run_id}.json` (so exports survive a server restart). |
| GET | `/api/runs/{run_id}/export/bom.csv` | Section 4.13 |
| GET | `/api/runs/{run_id}/export/risk.md` | Section 4.13 |
| GET | `/api/parts/{mpn}` | The `PartSpec` fields plus `datasheet_available: bool`, or 404. |
| GET | `/api/datasheets/{mpn}` | The local PDF (`application/pdf`), or 404. The UI links to it as `...#page={n}`. |
| GET | `/api/eval` | `data/eval/results.json`, or `{ready: false}`. |
| GET | `/api/extract/{mpn}` | Extraction check (section 4.16), or `{available: false}`. |
| POST | `/api/extract/{mpn}` | Runs the extraction pipeline for one catalog MPN, then returns the same body as GET. |

### 4.13 Exports

BOM CSV header:

```
ref,qty,original_manufacturer,original_mpn,recommended_manufacturer,recommended_mpn,verdict,confidence,explanation
```

One row per input line; null values are empty cells.

Risk report (Markdown):

```
# PartSwap risk report
Run: {run_id}
Goal: {goal}
Preferred manufacturer: {preferred_manufacturer}

## {ref}: {original_mpn} → {recommended_mpn or "no safe match"}
Verdict: {verdict}
{explanation}

| Spec | Requirement | Original | Candidate | Result | Page |
| --- | --- | --- | --- | --- | --- |
| vrrm_v | >= 32 V (line requirement) | 40 V | 40 V | pass | 2 |

Caveats: {one bullet per caveat, or "none"}
Rejected candidates: {one bullet per entry: mpn — reason — "matches on headline specs" when headline_match}
```

Use the `raw` strings. `skip` checks are omitted.

### 4.14 Prompts

`agent/prompts.py`. Write these strings verbatim. `PROMPT_VERSION = "v2"`. (v2 came from the single Phase 7 improvement loop: steps 3, 5, 6 and 7 below were revised because v1 over-tightened true drop-ins on generic 25 °C test conditions and gave class C pairs a stricter verdict than caveats. `data/eval/results_v1.json` keeps the v1 numbers.)

`SYSTEM_PROMPT`:

```
You are PartSwap's verification agent. You decide whether a catalog part can replace one BOM line on a real circuit board, and you explain the risk to a hardware engineer.

Facts come from tools. Never invent a part number, a spec value, a unit, or a page number.

How to work:
1. Call search_candidates, then compare_specs on the plausible candidates (at most 4).
2. compare_specs is authoritative for the numbers. A fail marked no_safe_match cannot be any kind of drop-in. A package or pinout fail means needs_redesign at best.
3. Then do what the numeric checks cannot. For each value that passed, read its "condition" and compare it with this circuit: the line description and the resolved requirements. A value measured under a condition this circuit does not meet is unverified, but only when that value matters for what this part does in this circuit. Examples: Rds(on) given only at a higher gate voltage than the circuit drives; leakage given only at 25 °C when the description says reverse leakage matters, such as a diode blocking a battery on a board that runs hot; a current rating that needs more input headroom than the circuit has. A standard test condition (25 °C, typical values) is not a concern by itself when this circuit's job does not depend on that value.
4. When a concern depends on text rather than a number (pin functions, output capacitor or stability requirements, derating), call get_datasheet_excerpt for that part and topic.
5. If every numeric check passes but a passing value is unverified for this circuit, or an excerpt shows a requirement this circuit may not meet, record drop_in_with_caveats and name the condition and the circuit fact in the caveats. Reserve needs_redesign for package or pinout differences and no_safe_match for ratings that fail or are unknown. You may never be more lenient than compare_specs.
6. Prefer the preferred manufacturer when two candidates are equally safe. That preference ranks candidates; it is never a caveat. lowest_risk means fewer caveats and more margin, not a lower price.
7. Finish with record_decision exactly once. caveats is a JSON array of short strings. The explanation must name the datasheet values and pages the tools returned, and should say which look-alike candidates were rejected and why.

Do not claim pin compatibility unless the pinout check passed. Treat unknown as unverified, never as pass.
```

`CATEGORY_PROMPT`:

```
Classify the electronic component into exactly one token: ldo, buck, schottky, mosfet, esd, or unknown. Reply with that single token and nothing else.
Description: {description}
MPN: {mpn}
```

`STRUCTURE_PROMPT`:

```
Extract the requested fields from this datasheet page for part {mpn}. Return one JSON object mapping each field name to {"value": number or null, "raw": string or null, "condition": string or null}.
- value is converted to the unit in the field name suffix (_v volts, _a amps, _ohm ohms, _hz hertz, _c Celsius, _pf picofarads, _kv kilovolts).
- raw is copied exactly from the page text.
- If the page lists several parts, use the column or row for {mpn}.
- If a field is not on this page, set all three to null. Do not guess.
Category: {category}
Fields: {field_names}
Page {page} text:
{text}
```

Grounding check (Python, not a model call): drop any field whose `raw`, whitespace-normalized and lowercased, is not a substring of the page text. When `raw` parses with a unit, also drop the field if `value` differs by more than 1 % from `units.parse_quantity(raw)` converted to the field's unit. When `raw` is a bare number (the unit sits in another table column), keep the field.

### 4.15 Models and environment

`.env.example` (copy to `.env`; `.env` is already gitignored):

```
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_SUPER_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
NEMOTRON_FAST_MODEL=nvidia/nemotron-3.5-bolt-e4b
NEMOTRON_PARSE_URL=https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-parse/parse
PARTSWAP_MODE=fixture
PARTSWAP_DATA_DIR=data
```

| Variable | Read by |
| --- | --- |
| `NVIDIA_API_KEY` | `agent/client.py`, `extract/parse_api.py`, `scripts/probe_models.py` |
| `NVIDIA_BASE_URL` | `agent/client.py` |
| `NEMOTRON_SUPER_MODEL` | live verification loop; eval arm `partswap_super` |
| `NEMOTRON_FAST_MODEL` | category label, extraction structuring; eval arm `partswap_bolt` |
| `NEMOTRON_PARSE_URL` | `extract/parse_api.py` (a REST endpoint, not a chat model) |
| `PARTSWAP_MODE` | default mode of `POST /api/runs`; reported by `/api/health` |
| `PARTSWAP_DATA_DIR` | `paths.data_dir()` |

`config.py` loads `.env` from the repo root with `python-dotenv`. Importing the app must not require a key.

Model facts gathered from NVIDIA's catalog pages while writing this plan. All of them are re-checked by the Phase 0 probe before code depends on them:

- **Reasoning model.** The brief's ID `nvidia/nemotron-3-super-120b-a12b` still has an API page, but its catalog page marks the free endpoint **Deprecated**. The current model is `nvidia/nemotron-3.5-super-vl-120b-a12b` (reasoning, tool calling, 1M context; listed as early access). Preference order: 3.5 Super VL, then 3 Super, then `nvidia/nemotron-3.5-lightning-30b-a3b`. Use the first that passes the probe's tool-call test.
- **Fast model.** `nvidia/nemotron-3.5-bolt-e4b`. Its API reference says standalone gateway requests may need `stg/nvidia/nemotron-3.5-bolt-e4b`; the probe tries both. Its model card says to emit one tool call per turn and that a tool result must directly follow the assistant message that requested it.
- **Parse.** `nvidia/nemotron-3.5-parse` is a REST endpoint: multipart `document` = **one page image** (PNG or JPEG) plus optional `options={"decoding":{"max_output_tokens":N}}`; the response has `content` (Markdown with `<x_..>`, `<y_..>`, `<class_..>` tokens). It does not accept a PDF. The older chat-style `nvidia/nemotron-parse` endpoint is deprecated; do not call it.
- **Rate limit.** The free tier is documented as up to 40 requests per minute and 10,000 per day, shared and variable. Keep concurrency at 3 or below.

Completion arguments, defined once as `MODEL_KWARGS` in `agent/client.py`:

| Model | Arguments |
| --- | --- |
| Super | `temperature=0.2, top_p=0.95, max_tokens=4096, parallel_tool_calls=False, extra_body={"chat_template_kwargs": {"enable_thinking": True}}` |
| Bolt | `temperature=0.2, top_p=0.95, max_tokens=4096, parallel_tool_calls=False, extra_body={"skip_special_tokens": False, "chat_template_kwargs": {"enable_thinking": True}}` |

Thinking tokens count against `max_tokens`, which is why it is 4096 and why the loop handles `finish_reason == "length"`. If the probe shows a model returns tool calls only with thinking off, set that model's `enable_thinking` to false and record it in `docs/model_probe.md`.

### 4.16 Frontend

One page. Light background, dark text, base font 18 px, readable at 1920×1080 on a projector. No login.

- **Top bar:** "PartSwap", a mode badge, and `has_api_key` status.
- **Left column:** file input, "Load demo BOM" button, design-context form (section 4.4 fields), mode select (`fixture`, `deterministic`, `cache`, `live`; default from `/api/health.mode_default`), "Run" button. BOM parse errors render here as a list.
- **Center:** results table. Columns: Ref, Original, Recommended, Verdict (badge), Confidence (`—` when null), Traps. Traps shows `{n} rejected` when `rejected` has entries with `headline_match: true`. Clicking a row selects it. Under the table: "Export BOM", "Export risk report", then the evaluation panel.
- **Right column, tab "Detail":** for the selected line: side-by-side spec table from `decision.spec_checks` (columns Spec, Requirement, Original, Candidate, Result; `fail` rows `#fde8e8`, `caveat` and `unknown` rows `#fff4d6`); each value shows its `condition` in small text and `p.{page}` as a link to `/api/datasheets/{mpn}#page={page}` when `datasheet_available`; the package/pinout line; caveats; the explanation; a "tightened by deterministic check" notice when `tightened`; a **Rejected candidates** list with each reason and the label "A basic cross-reference would approve this" when `headline_match`; a "Run live on this line" button (posts that one line with `mode: live`); the extraction check when available.
- **Right column, tab "Agent":** chronological steps for the selected line, appended as events arrive. `reasoning` in italics, tool calls in monospace.

Badge colors (white text): `drop_in` `#1b7f4e`, `drop_in_with_caveats` `#8a6a00`, `needs_redesign` `#c2410c`, `no_safe_match` `#b42318`. Labels: Drop-in, Drop-in with caveats, Needs redesign, No safe match.

Evaluation panel: one table from `GET /api/eval`, one row per approach, columns from section 4.17, and the headline sentence built from the file's numbers. When `ready` is false show "Evaluation not generated yet." Never hardcode numbers.

Extraction check (`GET /api/extract/{mpn}`): `{available, parser, fields: [{key, verified_raw, extracted_raw, status}]}` with `status` of `match`, `mismatch`, or `missing`. Rendered as a small table titled "Extracted by Nemotron vs. human-verified".

`frontend/src/types.ts` mirrors `Decision`, `Check`, `DesignContext`, `BomLine`, `PartSpec`, and the SSE event union with the exact field names above.

### 4.17 Evaluation

`data/eval/pairs.json`, 20 entries:

```json
{
  "id": "A1-schottky-vrrm-20",
  "class": "A",
  "original_mpn": "MBR0540T1G",
  "candidate_mpn": "B0520LW-7-F",
  "description": "Reverse-polarity Schottky on the 24 V input",
  "requirements": {"req_vrrm_v": 32, "req_iout_a": 0.5},
  "expected_verdict": "no_safe_match",
  "dangerous_if_drop_in": true
}
```

| Class | Count | What it is | Baseline says | Rules alone say | Expected |
| --- | --- | --- | --- | --- | --- |
| A | 5 | Rating trap: headline matches, a rating the headline ignores is too low (Vrrm, Vgs(th) vs gate drive, input voltage, ESD direction, temperature) | drop_in | no_safe_match | no_safe_match |
| B | 3 | Pinout trap: same package, different pin functions | drop_in | needs_redesign | needs_redesign |
| C | 3 | Judgment trap: every number passes, but a `condition` or a datasheet excerpt shows it does not hold in this circuit | drop_in | drop_in | drop_in_with_caveats |
| D | 3 | Different package | no_safe_match | needs_redesign | needs_redesign |
| E | 4 | True drop-in | drop_in | drop_in | drop_in |
| F | 2 | True caveat (for example much higher quiescent current) | drop_in | drop_in_with_caveats | drop_in_with_caveats |

`dangerous_if_drop_in` is true for classes A, B, C, D (14 pairs).

Class C is where the model has to earn its place. The three patterns to author (synthetic `SYN-` parts are fine; the description states the circuit fact):

1. MOSFET whose `rds_on_ohm` condition is `VGS = 10 V` only, on a line whose description says the gate is driven from a 3.3 V GPIO (`req_vgs_v: 3.3`, threshold passes).
2. LDO whose `application` excerpt requires an output capacitor larger than the one the description says is fitted, or a minimum ESR that a ceramic capacitor does not have.
3. Schottky whose 25 °C leakage passes the ratio check while its excerpt gives leakage in milliamps at high temperature, on a line described as blocking reverse current into a backup supply at 85 °C.

Real pairs available from the demo catalog: A (MBR0540T1G → B0520LW-7-F, MBR0540T1G → B0530W-7-F), B (MCP1700-3302E/TT → AP7333-33SAG-7), E (MBR0540T1G → B0540W-7-F), F (MCP1700-3302E/TT → AP7333-33SRG-7). The rest may be synthetic.

Approaches:

| Name | How a verdict is produced |
| --- | --- |
| `naive_baseline` | `drop_in` if `headline_match`, else `no_safe_match`. |
| `partswap_rules` | `suggest_verdict(evaluate_pair(...))`. No model. |
| `partswap_bolt` | `run_part` with the fast model and `only_candidates=[candidate]`. |
| `partswap_super` | `run_part` with the reasoning model and `only_candidates=[candidate]`. |

`data/eval/results.json`:

```json
{
  "generated_at": "2026-11-21T18:30:00-06:00",
  "pair_count": 20,
  "dangerous_count": 14,
  "prompt_version": "v1",
  "approaches": [
    {"name": "naive_baseline", "accuracy": 0.0, "false_drop_in_count": 0, "model_false_drop_in_count": null,
     "tightened_count": null, "fallback_count": null, "median_latency_ms": 0}
  ],
  "per_pair": [{"id": "A1-schottky-vrrm-20", "expected": "no_safe_match",
                "naive_baseline": "drop_in", "partswap_rules": "no_safe_match"}]
}
```

- `accuracy` = exact verdict matches / 20.
- `false_drop_in_count` = dangerous pairs whose final verdict is `drop_in`. This is the error that damages boards.
- `model_false_drop_in_count` = dangerous pairs where `model_verdict` (before the guardrail) was `drop_in`. It measures the model on its own.
- `tightened_count` = decisions the guardrail tightened. `fallback_count` = decisions with `source: deterministic_fallback`.
- An approach that did not run is omitted. Never write an estimated number.

Headline under the table, built from the file: `A basic cross-reference approved {naive.false_drop_in_count} of {dangerous_count} dangerous swaps. PartSwap approved {best.false_drop_in_count}.` where `best` is `partswap_super` if present, else `partswap_rules`.

## 5. Assumptions and Open Questions

Decided; do not reopen during implementation:

- The demo runs on verified JSON and cached runs. Extraction writes side files and never overwrites verified specs.
- PDFs are fetched once before the demo (by a person, or by the Phase 1 executor with `curl` from the manufacturer URL) and are never fetched at run time. The PartSwap agent has no network tools.
- Search returns every part in the category so traps stay visible. The trap is shown as a rejected candidate on a line that still gets a good recommendation.
- An unverified critical spec means `no_safe_match`. An unverified secondary spec means `drop_in_with_caveats`.
- The stage path is `cache` mode plus one live line. A cache miss runs the deterministic pipeline, never a surprise live call.
- "Max current per rail" from the brief is a per-line `req_iout_a`, not a board-level field.
- The brief's `search_candidates(category, constraints, preferred_manufacturer)` drops `constraints` on purpose: filtering would hide traps.
- The remote is `origin` (`sohamjad789/tinyml-edge-vs-cloud`), branch `main`.

There are no open questions that block coding.

Verify in Phase 0 and record in `docs/model_probe.md`:

- Which reasoning and fast model IDs answer, with latency.
- Whether each returns `tool_calls` with thinking on, and whether it accepts a tool result and continues.
- Whether Bolt needs the `stg/` prefix.
- Whether the Parse URL accepts the key.
- `import fitz` works in the venv.

Verify in Phase 1 against the PDF, never from memory or from this plan:

- Package code, pin numbering, and every critical spec of every demo part.
- If a part does not support its intended role, swap the part or the line's requirement. Never edit `data/categories.json` to make a story true.

Datasheet facts found by web search while planning. They are leads for Phase 1, not verified data:

- Diodes B0520LW / B0530W / B0540W: SOD-123, 0.5 A, Vrrm 20 / 30 / 40 V. Max Vf at 0.5 A: 0.385 / 0.430 / 0.510 V. Max leakage at rated voltage, 25 °C: 250 / 130 / 20 µA. B0520LW leakage reaches 8 mA at 100 °C. Junction range to +125 °C (B0520LW, B0530W) and +150 °C (B0540W).
- Diodes AP7333: 300 mA fixed LDO, input 2–6 V (7 V absolute max), Iq 55 µA typical at no load, dropout 300 mV typical at 300 mA, ambient −40 to 85 °C. Two SOT-23 pin assignments: `SA` (SOT23) is 1 IN, 2 OUT, 3 GND; `SR` (SOT23R) is 1 GND, 2 OUT, 3 IN.
- Microchip MCP1700 in SOT-23: 1 GND, 2 VOUT, 3 VIN. Input 2.3–6.0 V (6.5 V absolute max), 250 mA, Iq 1.6 µA typical.
- Consequence: AP7333-33**SR**G-7 is pin-compatible with the MCP1700 and has about 34× the quiescent current (a real caveat). AP7333-33**SA**G-7 is the same chip in the same body with IN and GND swapped (a real pinout trap).
- URL pattern that worked: `https://www.diodes.com/datasheet/download/{family}.pdf` (for example `B0540W.pdf`, `AP7333.pdf`).

## 6. Risks / Edge Cases

| Risk | Mitigation |
| --- | --- |
| Hand-entered spec is wrong (the riskiest part of the project) | Two tiers of data: Tier A (7 parts, the three demo beats) is verified first and finishes by 3:00 PM. Executor drafts from the PDF with `verified: false`; a person checks each value against the cited page and flips it. `test_specs_valid.py` and `test_manifest.py` fail when a part cannot produce its intended outcome. |
| Pin numbering copied from memory | Pinout always comes from the datasheet page. AP7333 SA vs SR shows why. |
| Package alias merges different bodies | Alias file contains punctuation variants only. TSOT, SC-70, SOD-123F are never aliased. |
| Unit notation mismatch (`3V3`, `3300 mV`, `µ` vs `u`) | `units.py` with tests; specs stored as numbers; requirement cells parsed by the same code. |
| Missing spec treated as pass | Null → `unknown` → `no_safe_match` for critical checks, caveat for secondary ones. Tested. |
| Value passes but was measured under a condition the circuit does not meet | `condition` is carried on every check; the system prompt tells the model to compare it with the circuit; evaluation class C measures it. |
| Model approves a failing part | `record_decision` floors the verdict and sets `tightened`. The raw `model_verdict` is kept for the evaluation. |
| Model invents a number | Spec table is built from `evaluate_pair` only. |
| Model stops after looking at one bad candidate | Guardrail step 2 names the uncompared better candidate once. |
| Model returns bad JSON, an unknown tool, or nothing | Structured tool errors, one content-JSON recovery, then deterministic fallback for that line. The run continues. |
| Tool calls missing with thinking on, or cut off by `max_tokens` | Probe tests real tool calls in Phase 0. `max_tokens=4096`. `length` retry with thinking off. |
| Brief's model ID is deprecated; 3.5 Super is early access | Probe picks the first working ID from three. `.env` holds the choice. |
| API slow, down, or rate-limited (40 rpm shared) | 60 s timeout, 3 backoff retries, 150 s per-line budget, fallback. Stage path is cache replay; warm it before judges arrive. Eval concurrency 3, cached per pair. |
| Parse endpoint unavailable | pdfplumber / PyMuPDF text into the same structuring prompt and grounding check. The demo does not depend on it. |
| Scanned or image-only PDF | Page text shorter than 40 characters → use Parse output; if Parse is unavailable the fields come back null with `parser: "pdf_text"`. No crash. |
| Datasheet covers several parts in one table | `STRUCTURE_PROMPT` names the MPN; grounding check validates `raw`; extraction is compared against verified data in `extraction_report.json`. |
| Malformed BOM | 400 with row-level errors rendered in the form. Tested. |
| MPN not in catalog | Line becomes `no_safe_match` with a clear explanation. Other lines continue. |
| Frontend and backend drift | `shared/examples/*.json` validated against Pydantic models; `types.ts` copies the names; contract changes go through the Lead. |
| Server restart loses a run before export | Runs are also written to `data/cache/runs/`. Run the demo without `--reload`. |
| Stale cache after a spec or prompt change | `prompt_version` is in the key. Delete `data/cache/` after spec edits; Phase 8 re-warms. |
| Evaluation numbers made up under time pressure | Approaches that did not run are omitted. Rules and baseline arms need no API and always run. |
| Datasheets or key committed | PDFs, `.env`, and caches are gitignored. Excerpts are short chunks, not page dumps. |
| Demo machine has no network at the venue | `fixture` and `deterministic` modes need none. Backup video recorded at 7:30 PM. |
| Behind schedule | Cut list in section 11. Checkpoints at 4:00, 4:30, and 7:30. |

**Review focus.** These five behaviors each have a named test. Do not delete or weaken them:

1. `3V3`, `3300 mV`, and `3.3V` parse to the same voltage (`test_units.py`).
2. A null critical spec yields `unknown` and `no_safe_match`, never `pass` (`test_compare_unknown.py`).
3. The 20 V Schottky on a 32 V line: `headline_match` is true and the floor is `no_safe_match` (`test_headline.py`).
4. A model `drop_in` on a failing pair is stored as the floor with `tightened: true` and `model_verdict: "drop_in"` (`test_agent_loop.py`).
5. A timeout on one line produces a fallback decision and the next line still runs (`test_agent_loop.py`).

## 7. Implementation Plan

### Team workflow

Four lanes. Everyone starts at 1:00 PM; nobody waits for Phase 0, because the contracts are in section 4 of this file.

| Lane | Owns (only this lane edits) | Phases |
| --- | --- | --- |
| Lead | `backend/app/schemas.py`, `config.py`, `paths.py`, `main.py`, `runs.py`, `export.py`, `shared/examples/`, `data/categories.json`, `data/package_aliases.json`, `data/pin_functions.json`, `data/topics.json`, `backend/app/extract/`, `docs/`, `README.md`, `PLAN.md` | 0, 3, 5a (with Backend), 6, writeup |
| Data | `data/specs/`, `data/catalog.json`, `data/bom/`, `data/demo_manifest.json`, `data/datasheets/`, `data/excerpts/`, `data/eval/pairs.json`, `data/fixtures/` | 1, eval pairs, demo script |
| Backend | `backend/app/{units,bom,catalog,requirements_build,compare,package,headline,verdict,decide,candidates,excerpts,categorize}.py`, `backend/app/agent/`, `backend/app/eval/` | 2, 5a, 5b, 7 |
| Frontend | `frontend/` | 4 |

- **Tests** in `backend/tests/` belong to the lane that owns the module under test. One test file per module, so two lanes never edit the same file.
- **Contract changes** (any field name, event shape, or tool signature in section 4): tell the Lead. The Lead changes `PLAN.md`, `schemas.py`, and `shared/examples/` together and tells the Frontend lane. Nobody else edits those files.
- **Git:** work on `main` in small commits and push to `origin`; `git pull --rebase` before each push. Lanes own disjoint paths, so conflicts should be rare. Agents commit and push only when their human asks.
- **Fewer than four people:** with three, the Lead and Backend lanes are one person and Phase 3 goes to whoever is free first; expect the deterministic checkpoint near 4:30 PM and the first live line near 5:15 PM. With one or two, follow the "minimum path" in section 10.

### Phase 0 — Contracts, scaffold, model probe

- **Goal:** Importable schemas, validated example payloads, a fixture stream the frontend can consume, and a written record of which NVIDIA model IDs work with tool calling.
- **Time:** 1:00–2:00 PM. **Owner:** Lead. Other lanes work in parallel from section 4.

**Inspect first:** `README.md`, `.gitignore`. Change nothing else that already exists.

**Create:**

- `.env.example` (section 4.15), `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`).
- `backend/requirements.txt`: `fastapi>=0.115`, `uvicorn>=0.32`, `pydantic>=2.9`, `openai>=1.50`, `httpx>=0.27`, `pymupdf>=1.24.10`, `pdfplumber>=0.11`, `python-dotenv>=1.0`, `pytest>=8.3`.
- `backend/app/schemas.py`: Pydantic v2 models `SpecField`, `Package`, `Pin`, `PartSpec`, `BomLine`, `BomError`, `DesignContext`, `Requirements`, `Check`, `Comparison`, `PackagePinoutResult`, `RejectedCandidate`, `Decision`, `Run`, `EvalPair`, `EvalApproach`, `EvalResults`, with string enums for category, verdict, goal, mode, source, and check result. Field names exactly as in section 4.
- `backend/app/config.py`, `paths.py`, package `__init__.py` files.
- `data/categories.json`, `data/package_aliases.json`, `data/pin_functions.json` verbatim from section 4.6.
- `data/topics.json`: `{"pinout": ["pin", "pinout", "pin assignment", "pin description"], "absolute_maximum": ["absolute maximum", "maximum ratings"], "electrical": ["electrical characteristics"], "thermal": ["thermal", "junction", "derating"], "application": ["capacitor", "stability", "esr", "application information", "layout"]}`.
- `shared/examples/`: `design_context.json`, `part_spec.json` (section 4.5), `comparison.json` (4.6), `decision.json` (4.8), `sse_events.jsonl` (one line per event name and per `agent_step` kind), `eval_results.json` (4.17).
- `data/fixtures/demo_run.json`: a hand-written starter with three lines covering `drop_in`, `drop_in_with_caveats`, and a decision whose `rejected` has a `headline_match: true` entry. Use the D1 and U2 examples from this plan. Phase 3 replaces it with a recorded run.
- `data/bom/demo_bom.csv`: the two-row example from section 4.3 (Data lane extends it).
- `backend/app/main.py`: `GET /api/health`, `GET /api/demo-bom`, and `POST /api/runs` supporting `mode=fixture` only (stream the fixture's events; any other mode returns an SSE `error`).
- `backend/tests/test_examples_match_models.py`: every file in `shared/examples/` and the starter fixture's decisions validate against the models.
- `backend/scripts/probe_models.py`.

**Steps:**

- [ ] `/opt/homebrew/bin/python3.11 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`.
- [ ] Append to `.gitignore`: `node_modules/`, `frontend/dist/`, `data/datasheets/*.pdf`, `data/cache/`, `data/specs/extracted/`, `docs/*.mp4`.
- [ ] Replace `README.md` with: one-paragraph description, prerequisites (Python 3.11 or 3.12, not 3.14; Node 20+), setup, the run and test commands from section 8, and "copy `.env.example` to `.env`". Under 60 lines; Phase 8 extends it.
- [ ] Write schemas, examples, and the validation test. `pytest -q` passes.
- [ ] Implement the three routes. `curl -N -X POST 'http://127.0.0.1:8000/api/runs?fast=1' -H 'content-type: application/json' -d '{"lines":[],"design_context":{},"mode":"fixture"}'` prints the starter events. (Quote the URL; zsh treats a bare `?` as a glob.)
- [ ] Implement `probe_models.py`. For each candidate ID in section 4.15's order, with thinking on and then off: (a) a plain completion; (b) a tool-call request offering `get_part_specs(mpn)` with the user message "Look up the specs for part MBR0540T1G." and a check that `tool_calls[0].function.name == "get_part_specs"`; (c) a follow-up sending a tool result and checking that a normal reply comes back. For Parse: render a one-page PDF in memory with PyMuPDF containing the text `VRRM 40 V`, convert it to PNG at 150 DPI, POST it, and check that `content` contains `40`. Write `docs/model_probe.md` with a table of ID, thinking setting, each test's pass/fail, HTTP status, and latency, plus the chosen IDs. Never print the key. With no key, write "not run: no NVIDIA_API_KEY" and exit 0.
- [ ] If a key exists, run the probe and set the winning IDs and thinking flags in `.env` and `MODEL_KWARGS`. Tell the team the result.

**Pitfalls:** No comparison logic here. Do not call the deprecated `nvidia/nemotron-parse`. Do not block on a missing key.

**Done when:** `pytest -q` passes; `/api/health` returns `status: ok`; the fixture stream works with `curl`; `docs/model_probe.md` exists.

### Phase 1 — Demo catalog and verified specs

- **Goal:** Verified spec files, catalog, demo BOM, and manifest. Tier A first.
- **Time:** Tier A 1:00–3:00 PM. Tier B 3:30–5:00 PM. **Owner:** Data.

**Inspect first:** sections 4.3–4.6, section 5's datasheet leads, and `backend/app/schemas.py` once it exists.

**Method for every part** (about 10 minutes each):

1. Get the PDF into `data/datasheets/` (`curl -L -o` from the manufacturer URL; if that fails, a person downloads it). Add a row to `data/datasheets/SOURCES.md`: `| mpn | url | retrieved |`.
2. The executor reads the PDF and drafts `data/specs/{MPN}.json` with `verified: false`: every key in that category's checks in `data/categories.json`, each with `raw`, `condition`, and `page`.
3. A person opens the cited page, checks each value, the package code, and the pin numbering, corrects mistakes, and sets `verified: true`. A value that is not in the datasheet is `null`; it is not guessed.

**Tier A — seven parts, both demo lines, all three beats. Due 3:00 PM.**

| Line | Original | Candidates and intended result |
| --- | --- | --- |
| D1, `req_vrrm_v=32`, `req_iout_a=0.5` | onsemi MBR0540T1G (40 V, 0.5 A, SOD-123) | Diodes B0540W-7-F → `drop_in` (recommended). B0530W-7-F → rejected, 30 V < 32 V, headline match. B0520LW-7-F → rejected, 20 V < 32 V, headline match. |
| U2, `req_vin_max_v=5.5`, `req_vout_v=3.3`, `req_iout_a=0.15`, `req_headroom_vin_v=5` | Microchip MCP1700-3302E/TT (SOT-23) | Diodes AP7333-33SRG-7 → `drop_in_with_caveats` (quiescent current, dropout; recommended). AP7333-33SAG-7 → rejected `needs_redesign`, IN and GND swapped, headline match. |

Record both AP7333 variants with `package.code` `SOT-23-3` (the datasheet calls them SOT23 and SOT23R; the body is the same, the pins are not). These roles come from web-search leads. If the PDF disagrees, change the part or the requirement cell and tell the Lead; do not change the rules.

**Tier B — add lines only after Tier A is green. Stop at 5:00 PM with whatever is verified.**

| Line | Original | First Diodes candidates to check | Note |
| --- | --- | --- | --- |
| D2, `req_vrrm_v=20`, `req_iout_a=0.5` | onsemi MBR0520LT1G | B0520LW-7-F | Likely a clean drop-in; candidates are already in the catalog. Cheapest line to add. |
| U3, `req_vin_max_v=5.5`, `req_vout_v=3.3`, `req_iout_a=0.25`, `req_headroom_vin_v=5` | TI TLV75533PDBVR (SOT-23-5) | AP2112K-3.3TRG1 | Check the EN pin position and polarity. |
| Q1, `req_vds_v=60`, `req_vgs_v=3.3`, `req_iout_a=0.2` | onsemi 2N7002LT1G (SOT-23) | Diodes 2N7002-7-F, DMN65D8L-7 | Record the Rds(on) test voltage in `condition`; the agent should notice it is above 3.3 V. |
| U1, `req_vin_max_v=32`, `req_vout_v=3.3`, `req_iout_a=0.5` | TI TPS560430X3FDBVR (SOT-23-6) | Diodes AP63203WU-7 | Expect a package or pinout difference (`needs_redesign`). Bucks take the longest; do this one last. |
| D3, `req_vrwm_v=5`, `req_esd_contact_kv=8` | Nexperia PESD5V0S1BL | A Diodes single-line 5 V ESD diode in the same package | Skip if no same-package part is found in 10 minutes. |

**Files and steps:**

- [ ] Tier A specs, then `data/catalog.json` and `data/bom/demo_bom.csv` (17 columns, section 4.3).
- [ ] `data/demo_manifest.json`:

  ```json
  {"design_context": {"input_voltage_v": 24, "input_voltage_max_v": 32, "operating_temp_min_c": -40, "operating_temp_max_c": 85, "preferred_manufacturer": "Diodes Incorporated", "goal": "lowest_risk"},
   "lines": [{"ref": "D1", "original_mpn": "MBR0540T1G", "expected_recommended_mpn": "B0540W-7-F", "expected_verdict": "drop_in",
              "candidates": [{"mpn": "B0540W-7-F", "expected_pair_verdict": "drop_in", "headline_match": true},
                             {"mpn": "B0530W-7-F", "expected_pair_verdict": "no_safe_match", "headline_match": true},
                             {"mpn": "B0520LW-7-F", "expected_pair_verdict": "no_safe_match", "headline_match": true}]}]}
  ```

  The manifest is test data and demo documentation. No tool, prompt, or route other than `/api/demo-bom` (which returns only `design_context`) reads it.
- [ ] `pytest -q backend/tests/test_specs_valid.py backend/tests/test_manifest.py` (written in Phase 2). Fix data until green.
- [ ] After Phase 3 lands: `python backend/scripts/record_fixture.py --mode deterministic` and confirm in the browser.
- [x] Tier B lines verified one at a time: D2, U3, Q1, U1. D3 skipped: no Diodes single-line 5 V candidate was verified as the same package and the datasheet did not establish the required 5 V working standoff rating within the search window. Phase 1 tests passed and the deterministic fixture was re-recorded after each added line.
- [x] 5:00–6:00 PM: author `data/eval/pairs.json` and the `SYN-` spec files it needs (section 4.17). Synthetic specs set `synthetic: true`, `verified: true`, and write `"synthetic"` in `table`. Class C parts also get a hand-written `data/excerpts/{MPN}.json`.

**Pitfalls:** Never type a pinout or a rating from memory. Never mark a guessed value verified. Do not add footprint aliases. Do not grow past 30 parts.

**Done when (Tier A):** seven spec files validate; `test_specs_valid.py` and `test_manifest.py` pass; `SOURCES.md` lists every PDF.

### Phase 2 — Deterministic core

- **Goal:** Units, BOM parsing, comparison, package/pinout, headline check, verdict floor, ranking, and decision assembly. Fully tested, no network.
- **Time:** 1:00–3:15 PM. **Owner:** Backend. Start with `units.py` and `bom.py` at 1:00; they need nothing from Phase 0 beyond the field names in section 4.

**Inspect first:** sections 4.3–4.8, `data/categories.json`, `backend/app/schemas.py`.

**Public functions** (exact names; later phases call them):

| Module | Function |
| --- | --- |
| `units.py` | `parse_quantity(text: str) -> Quantity` (`value: float`, `unit: str` one of `V A ohm Hz C F`), `parse_range(text: str) -> tuple[float, float]` |
| `bom.py` | `parse_bom(text: str) -> tuple[list[BomLine], list[BomError]]` |
| `catalog.py` | `load_part(mpn: str) -> PartSpec \| None` (case-insensitive), `all_parts() -> list[PartSpec]` |
| `requirements_build.py` | `build_requirements(line: BomLine, context: DesignContext) -> Requirements` |
| `package.py` | `normalize_package(code: str) -> str`, `normalize_pin_name(name: str) -> str`, `check_package_pinout(original: PartSpec, candidate: PartSpec) -> PackagePinoutResult` |
| `compare.py` | `evaluate_pair(original: PartSpec, candidate: PartSpec, requirements: Requirements) -> Comparison` |
| `headline.py` | `headline_match(original: PartSpec, candidate: PartSpec) -> bool` |
| `verdict.py` | `suggest_verdict(comparison: Comparison) -> str`, `rank_candidates(comparisons: list[Comparison], context: DesignContext) -> list[Comparison]`, `is_more_permissive(a: str, b: str) -> bool` |
| `candidates.py` | `search_candidates(category, preferred_manufacturer, original_mpn, include_synthetic=False, limit=8) -> list[PartSpec]` |
| `excerpts.py` | `excerpt_for(mpn: str, topic: str) -> dict` (score chunks by count of the topic's keywords from `data/topics.json`, return the top 2, trim to 1500 characters total) |
| `decide.py` | `build_decision(line, context, comparisons, compared_mpn, verdict, *, source, model=None, model_verdict=None, confidence=None, caveats=(), explanation="", tightened=False) -> Decision`, `decide_deterministic(line, context, emit=None) -> Decision` |

**Tests, written before the code they cover** (`backend/tests/`; synthetic parts live in `backend/tests/fixtures/parts/` so these tests never depend on the Data lane):

- `test_units.py`:
  - `3.3V`, `3300 mV`, `3V3`, `3.3 V` → 3.3 V
  - `1.5 A`, `1500mA`, `1A5` → 1.5 A
  - `2.2µA`, `2.2uA`, `2.2 μA` → 2.2e-6 A (micro sign U+00B5 and Greek mu U+03BC)
  - `4k7` → 4700 ohm; `65mΩ` → 0.065 ohm; `1.2 MHz` → 1.2e6 Hz
  - `parse_range("-40 to 125°C")`, `("-40°C ~ +125°C")`, `("−40 to +125 °C")` (Unicode minus) → `(-40, 125)`
  - `parse_quantity("abc")` raises `ValueError`
- `test_bom.py`: the section 4.3 example parses to two lines with `req_vrrm_v == 32` on D1 and `req_headroom_vin_v == 5` on U2; headers `Ref, MPN, Qty` in other cases parse; missing `description` column parses; a requirement cell `3V3` becomes 3.3; missing `mpn` column, blank `mpn`, `qty` of `0` or `two`, duplicate `ref`, wrong field count, and a semicolon-delimited file each produce an error and no run; a UTF-8 byte-order mark is ignored; an extra column is ignored.
- `test_requirements.py`: empty temperature cells inherit the context; empty `req_vin_max_v` stays null; `input_voltage_v` is always copied.
- `test_compare_schottky.py`: candidate Vrrm 20 with requirement 32 → `fail`, floor `no_safe_match`; requirement null and original 40 → `fail` (compared with the original); requirement 20 → `pass`; Vf worse by 0.2 V → `caveat` and floor `drop_in_with_caveats`; leakage 6× → `caveat`.
- `test_compare_ldo.py`: Iq 3× → `drop_in_with_caveats`; dropout 2.0 V with headroom 5 and Vout 3.3 → `no_safe_match`; dropout 0.12 V worse with headroom satisfied → `caveat`; fixed vs adjustable → `needs_redesign`; Vout 3.0 vs required 3.3 → `no_safe_match`.
- `test_compare_mosfet.py`: `vgs_th_max_v` 4.0 with `req_vgs_v` 3.3 → `no_safe_match`; `req_vgs_v` null → that check is `skip`; Rds(on) 2× → `caveat`; 4× → `fail`; `n` vs `p` → `no_safe_match`.
- `test_compare_buck.py`: synchronous vs asynchronous → `needs_redesign`; switching frequency 3× either direction → `caveat`; adjustable original skips the `vout_v` check.
- `test_compare_esd.py`: unidirectional vs bidirectional → `no_safe_match`; capacitance 3× → `caveat`; above `req_c_max_pf` → `no_safe_match`; one channel replacing two → `needs_redesign`.
- `test_compare_unknown.py`: candidate `vrrm_v` null → result `unknown`, floor `no_safe_match`; candidate `iq_a` missing → `unknown`, floor `drop_in_with_caveats`; in neither case is the result `pass`.
- `test_package.py`: `[anode, cathode]` vs `[cathode, anode]` → pinout `fail`; three-pin parts with pins 1 and 3 swapped → `fail`; `SOT23R` vs `SOT-23` → package `pass`; `SOT-23-5` vs `TSOT-23-5` → package `fail`; a `unknown` token → pinout `unknown` and floor `no_safe_match`; different pin counts → `fail`; `normalize_pin_name("NC") == "nc"` and `normalize_pin_name("/SHDN") == "enable_active_low"`.
- `test_headline.py`: Schottky 20 V vs 40 V, same package and current → `headline_match` true while the floor with `req_vrrm_v=32` is `no_safe_match`; pin-swapped LDO → `headline_match` true while the floor is `needs_redesign`; different package → false.
- `test_verdict.py`: order of precedence in `suggest_verdict`; `rank_candidates` puts a `drop_in` ahead of a `drop_in_with_caveats`, and the preferred manufacturer first among equals; `is_more_permissive("drop_in", "needs_redesign")` is true.
- `test_candidates.py`: preferred manufacturer first; original excluded; other categories excluded; a part that fails Vrrm is still returned; synthetic parts excluded by default.
- `test_decide.py`: with a safe candidate and two traps, `decide_deterministic` recommends the safe one, lists both traps in `rejected` with `headline_match: true`, and emits a `search_candidates` step and one `compare_specs` step per candidate; an MPN not in the catalog → `no_safe_match` with the section 4.8 explanation; an empty category → `no_safe_match`, `compared_mpn` null.
- `test_specs_valid.py` (reads `data/`; skipped when `data/specs/` is empty): every spec file validates; every `verified` part has every key its category's checks need, with `raw`, `condition`, and `page`; `package.pins` equals the pinout length; every function token is in the allowed list; `synthetic` parts have MPNs starting `SYN-`; every catalog entry points at a file.
- `test_manifest.py` (skipped when the manifest is absent): for each manifest candidate, `suggest_verdict(evaluate_pair(...))` equals `expected_pair_verdict` and `headline_match` equals the manifest value; for each line, `decide_deterministic` gives `expected_recommended_mpn` and `expected_verdict`; the demo BOM as a whole has at least one `drop_in`, one `drop_in_with_caveats`, and one rejected candidate with `headline_match: true`.

**Pitfalls:** `compare.py` never parses strings; specs are already numbers. Thresholds come from `data/categories.json`. `temp_min` uses `candidate_lte`, `temp_max` uses `candidate_gte`. No network anywhere in this phase.

**Done when:** `pytest -q` passes, including the two data tests once Tier A exists.

### Phase 3 — API, deterministic mode, exports

- **Goal:** The UI can run the real pipeline end to end with no API key.
- **Time:** 2:00–3:30 PM. **Owner:** Lead.

**Inspect first:** sections 4.11–4.13, and the Phase 2 function table for `parse_bom` and `decide_deterministic`. Build the routes and `fixture` mode first; they need nothing from Phase 2. Wire `deterministic` mode when `decide.py` lands (about 3:15 PM).

**Files:** `backend/app/main.py`, `runs.py`, `export.py`, `backend/scripts/record_fixture.py`, `backend/tests/test_api.py`.

**Steps:**

- [ ] `runs.py`: `stream_run(lines, context, mode) -> Iterator[str]` yields SSE frames; a run store (dict in memory, mirrored to `data/cache/runs/{run_id}.json`); mode dispatch for `fixture` and `deterministic` (`cache` and `live` are added in Phase 5 and until then return an SSE `error` saying so).
- [ ] Routes: `POST /api/bom/parse`, `GET /api/runs/{id}`, both exports, `GET /api/parts/{mpn}`, `GET /api/datasheets/{mpn}`, `GET /api/eval`, `GET /api/extract/{mpn}` (returns `{available: false}` until Phase 6).
- [ ] `record_fixture.py --mode deterministic|live`: runs the demo BOM through `stream_run`, writes `data/fixtures/demo_run.json`.
- [ ] `test_api.py` with FastAPI `TestClient`: a BOM with a missing `mpn` column → 400 with a row error; a `fixture` run (`fast=1`) ends with `run_completed`; a `deterministic` run on the test fixture parts yields one `part_decision` per line and a decision for an unknown MPN; `GET /api/runs/{id}` returns the decisions after the stream ends; the BOM export header equals section 4.13; the risk report contains each ref; unknown run → 404; `GET /api/parts/NOPE` → 404; `live` without a key → SSE `error`.
- [ ] Once Phase 2 and Tier A are in: set `PARTSWAP_MODE=deterministic` in `.env.example`, record the fixture, and run the demo BOM in the browser with the Frontend lane.

**Pitfalls:** Sync generator, no asyncio. Import the agent lazily inside the live branch so the app starts with no key. Set `Cache-Control: no-cache` on the stream.

**Done when:** `pytest -q backend/tests/test_api.py` passes and `mode=deterministic` streams decisions for the demo BOM.

### Phase 4 — Frontend

- **Goal:** A projector-readable UI covering upload, run, results, detail, trace, and export.
- **Time:** 1:00–4:00 PM, then continuing polish. **Owner:** Frontend.

**Inspect first:** sections 4.8, 4.11, 4.12, 4.16. Use those field names exactly. From 1:00 to 2:00 there is no backend; build against the JSON examples in this plan.

**Files:** the `frontend/` tree in section 4.2. `vite.config.ts`: port 5173, proxy `/api` → `http://127.0.0.1:8000`. Dependencies: `react`, `react-dom`; dev: `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`.

**Steps:**

- [ ] 1:00–2:00: `npm create vite@latest frontend -- --template react-ts`; `types.ts`; layout and styles; `ResultsTable` and `PartDetail` rendering the section 4.8 example from a local constant.
- [ ] `api.ts`: `getHealth`, `fetchDemoBom`, `parseBom`, `streamRun(body, onEvent)` (fetch POST, `response.body.getReader()`, `TextDecoder`, buffer and split on `\n\n`, read the `event:` and `data:` lines), `fetchPart`, `fetchEval`, `fetchExtraction`.
- [ ] `BomForm`: file input (reads text, calls `parseBom`, shows row errors), "Load demo BOM", context form, mode select, Run.
- [ ] State in `App.tsx`: `lines`, `decisions` by ref, `steps` by ref, `selectedRef`, `runId`, `running`. `part_started` adds a pending row; `part_decision` fills it; the first decision auto-selects its row.
- [ ] `PartDetail` and `AgentTrace` per section 4.16, including the rejected list and the Traps column.
- [ ] Export links use `runId`; disabled until `run_completed`.
- [ ] After 4:00: "Run live on this line", datasheet page links, `EvalPanel`, extraction check.
- [ ] Browser check (required before done): load the demo BOM; run `fixture`, then `deterministic`; the D1 row shows a green badge and "2 rejected"; its detail lists both rejected Schottkys with the cross-reference label; the U2 row is gold and its detail shows the caveat rows highlighted; the Agent tab fills in while the run streams; both exports download; an invalid CSV shows row errors; reloading the page leaves a usable form.

**Pitfalls:** No `EventSource`, no polling. Render spec values from `spec_checks`; never recompute a comparison in the browser. Keep text at 16 px or larger. A split SSE chunk must not break parsing (buffer until `\n\n`).

**Done when:** the browser check passes against `deterministic` mode and `npm run build` exits 0.

### Phase 5 — Live agent

Two parts, so a live line exists early.

#### Phase 5a — Minimal live loop

- **Goal:** `mode=live` decides one real line through Nemotron tool calls with the guardrail on.
- **Time:** 3:15–4:30 PM. **Owner:** Lead and Backend together (Lead: `client.py`, `prompts.py`, wiring in `runs.py`; Backend: `tools.py`, `loop.py`, tests).

**Inspect first:** `docs/model_probe.md` (model IDs, thinking flags), sections 4.9, 4.10, 4.14, 4.15.

**Files:** `backend/app/agent/{client,prompts,tools,loop}.py`, `backend/tests/fakes.py`, `backend/tests/test_agent_loop.py`.

**Steps:**

- [ ] `fakes.py`: `FakeClient` with a scripted list of responses (assistant messages with tool calls, or exceptions) exposing `chat.completions.create`. `run_part` takes the client as a parameter. A conftest fixture fails any test that constructs `openai.OpenAI`.
- [ ] `tools.py`: `TOOL_SCHEMAS` (the seven tools as OpenAI function definitions) and `execute_tool(name, arguments_json, state) -> dict`, where `state` holds the line, context, search results, and the set of compared MPNs.
- [ ] Tests first:
  - `test_happy_path`: scripted search → compare → record; decision has `source: model`, spec checks from `evaluate_pair`, and a `rejected` list.
  - `test_guardrail_tightens_drop_in`: model records `drop_in` on a Vrrm-failing candidate; stored verdict is `no_safe_match`, `tightened` true, `model_verdict` `drop_in`, confidence at most 0.6, and the stored candidate Vrrm equals the spec file's value.
  - `test_model_may_be_stricter`: floor is `drop_in`, model records `drop_in_with_caveats`; stored as given, `tightened` false.
  - `test_unknown_candidate_rejected`: an MPN not in the search results → tool error; a second one → `source: deterministic_fallback`.
  - `test_uncompared_better_candidate_nudge`: model records `no_safe_match` after comparing only the trap; first attempt returns the nudge naming the safe MPN.
  - `test_invalid_arguments_then_fallback`, `test_unknown_tool_error`, `test_invalid_verdict_enum`.
  - `test_content_json_recovery`: no `tool_calls`, content holds a valid call; accepted once.
  - `test_timeout_continues`: the client raises on line 1; line 1 gets a fallback decision plus a `part_error` event; line 2 is decided normally.
  - `test_rate_limit_retry`: two 429s then success → `source: model`.
  - `test_max_turns_fallback`: ten turns of `get_part_specs` → fallback.
  - `test_reasoning_emitted`: `reasoning_content` becomes an `agent_step` of kind `reasoning`.
- [ ] Implement until green. Wire `mode=live` into `runs.py`.
- [ ] With a key: `Run live on this line` for D1 in the browser. Check that the trace shows real tool calls and that the decision matches the manifest. Note the latency in `docs/model_probe.md`.

**Pitfalls:** Do not put spec data in the system prompt. Do not accept spec numbers from tool arguments. Tool result messages follow the assistant message directly. Do not disable the guardrail to make a demo line pass.

**Done when:** the tests pass and one live line has completed, or `docs/model_probe.md` records that no key or no working model was available (then tell the team at once; the demo falls back to `deterministic` and `cache` stays empty).

#### Phase 5b — Cache and hardening

- **Goal:** `cache` mode, a full live run of the demo BOM, and a recorded live fixture.
- **Time:** 4:30–5:45 PM. **Owner:** Backend.

**Steps:**

- [ ] Cache read/write per section 4.11; `mode=cache` replays hits and runs `decide_deterministic` on misses. Tests: a hit replays the stored events with no client call; a miss yields `source: deterministic`; a changed design context or `prompt_version` is a miss.
- [ ] `length` retry and the per-line time budget, with tests.
- [ ] Run the whole demo BOM live once. For each line compare the decision with the manifest. Where the model is wrong or wasteful, adjust `SYSTEM_PROMPT`, bump `PROMPT_VERSION`, and re-run that line. Record what changed and why in `docs/model_probe.md` (the writeup uses it).
- [ ] `python backend/scripts/record_fixture.py --mode live` so `fixture` mode replays a real agent run.

**Done when:** `mode=cache` replays the full demo BOM instantly with real agent traces, and all tests pass.

### Phase 6 — Excerpts and extraction pipeline

- **Goal:** Retrieval data for the agent, then a PDF-to-specs pipeline whose output is measured against the verified data.
- **Time:** 4:30–6:15 PM. **Owner:** Lead. Step 1 is needed by the agent; do it first.

**Inspect first:** `docs/model_probe.md` (Parse availability), section 4.14 (`STRUCTURE_PROMPT`, grounding), `data/topics.json`.

**Files:** `backend/app/extract/{pdf_pages,parse_api,structure,pipeline}.py`, `backend/scripts/{build_excerpts,extraction_report}.py`, `backend/tests/test_extract.py`, the extract routes in `main.py`.

**Steps:**

- [ ] `pdf_pages.py`: `page_texts(pdf_path, max_pages=4) -> list[{page, text}]` (PyMuPDF; if a page has under 40 characters, try pdfplumber) and `page_png(pdf_path, page, dpi=150) -> bytes`.
- [ ] `build_excerpts.py`: for each catalog part with a local PDF, split each of the first 6 pages into chunks of at most 700 characters on blank lines, keep chunks containing any keyword from `data/topics.json`, cap at 8 chunks per part, write `data/excerpts/{MPN}.json` as `{mpn, chunks: [{page, text}]}`. It does not overwrite a file that has `"authored": true`. Run it; confirm `get_datasheet_excerpt` returns text for D1's candidates.
- [ ] `parse_api.py`: `parse_page(png: bytes) -> str | None`. POST per section 4.15 with `max_output_tokens` 4096. Strip `<x_[0-9.]+>`, `<y_[0-9.]+>`, and `<class_[^>]+>` tokens. Return None on any HTTP error or timeout (30 s).
- [ ] `structure.py`: `structure_page(client, mpn, category, field_names, page, text) -> dict`. Calls the fast model with `STRUCTURE_PROMPT`, parses the first JSON object in the reply, applies the grounding check.
- [ ] `pipeline.py`: `extract_part(mpn) -> dict`. For pages 1–4: text = Parse output if available, else PDF text; structure; merge with "first non-null value wins, in page order". Write `data/specs/extracted/{MPN}.json` with `verified: false` and `parser: "nemotron_parse"` or `"pdf_text"`. Never writes to `data/specs/{MPN}.json`.
- [ ] `test_extract.py` (FakeClient, no network): the grounding check keeps a field whose `raw` is on the page and drops one whose `raw` is not; drops a field whose `value` disagrees with its `raw` (`raw: "20 V"`, `value: 40`); a reply wrapped in prose or a code fence still parses; a reply with no JSON yields all-null fields; a Parse failure falls back to PDF text; a zero-byte PDF returns `{error: "unreadable_pdf"}` without raising; coordinate tokens are stripped.
- [ ] `extraction_report.py`: for each part with both files, compare each critical field (`match` within 2 %, `mismatch`, `missing`) and write `data/eval/extraction_report.json` with per-part rows and totals. `GET /api/extract/{mpn}` serves the per-part view.
- [ ] Run the pipeline on the Tier A parts. Record the totals in `docs/model_probe.md`. Do not edit verified specs to match the extraction; if the extraction reveals a human error, the Data lane re-checks the PDF.

**Pitfalls:** One page image per Parse request, never the PDF. Do not block the demo on this phase. Do not commit `data/specs/extracted/`.

**Done when:** excerpts exist for the Tier A parts, `test_extract.py` passes, and `extraction_report.json` exists (or `docs/model_probe.md` records that neither Parse nor the fast model was reachable, with the PDF-text path still producing files).

### Phase 7 — Evaluation

- **Goal:** `data/eval/results.json` with measured numbers for every approach that ran, shown in the UI.
- **Time:** 5:45–7:15 PM. **Owner:** Backend. Needs `pairs.json` from Data (due 6:00 PM).

**Files:** `backend/app/eval/run_eval.py`, `backend/tests/test_eval.py`, `data/eval/results.json`.

**Steps:**

- [x] `test_eval.py`: `pairs.json` has 20 entries with the class counts in section 4.17; every MPN resolves; for every class A, B, C pair `headline_match` is true; for A, B, D, E, F the rules verdict equals `expected_verdict`; for class C the rules verdict is `drop_in` (so those pairs measure the model, not the rules); metric functions give the right counts on a hand-built example.
- [x] `run_eval.py --arms baseline,rules[,bolt][,super] [--refresh]`: computes each arm, merges into `results.json` (keeping arms from earlier runs), writes `per_pair`. Model arms build a synthetic `BomLine` from the pair (`ref` = pair id, requirement cells from `requirements`, `description`), call `run_part(..., only_candidates=[candidate])` with 3 worker threads, and cache each pair's decision in `data/cache/eval/{arm}/{id}.json`.
- [x] Run `--arms baseline,rules`. Expected by construction: baseline `false_drop_in_count` 11, rules 3 (the class C pairs). If not, fix the pairs.
- [x] Run `--arms super`, then `--arms bolt`. Look at `per_pair` for misses.
- [x] One improvement loop, 20 minutes at most: if Super misses class C pairs or over-tightens class E pairs, adjust `SYSTEM_PROMPT`, bump `PROMPT_VERSION`, re-run with `--refresh`. Save the earlier file as `data/eval/results_v1.json` so the writeup can show before and after. Stop after one loop whatever the numbers are.
- [x] Confirm the UI panel shows the table and the headline sentence from the file.

**Pitfalls:** Report the numbers that come out. An arm with more than 4 fallbacks is reported with its `fallback_count` and is not described as the model's accuracy. Never run the eval during the stage demo.

**Done when:** `test_eval.py` passes and `GET /api/eval` returns at least the baseline and rules rows.

### Phase 8 — Rehearsal, recording, writeup

- **Goal:** The 9:00 PM deliverables.
- **Time:** 7:15–8:30 PM. **Owner:** everyone. Writeup drafts start earlier (Lead, from 6:15 PM).

**Files:** `README.md`, `docs/nemotron.md`, `docs/demo_script.md`, `docs/demo-backup.mp4` (gitignored).

**Steps:**

- [ ] 7:15: stop feature work. Delete `data/cache/decisions/`, run the demo BOM live once to warm it, re-record the fixture, set `PARTSWAP_MODE=cache` in `.env`. Start the backend **without** `--reload`.
- [ ] `docs/demo_script.md`: the six beats from the brief with the real refs. For the trap beat: open D1, point at the rejected B0520LW-7-F and B0530W-7-F, and say that both match the original on package and current, a cross-reference tool lists them, and PartSwap rejected them because the input reaches 32 V. Then open U2 and show the AP7333 pin-swap variant.
- [ ] Dress rehearsal in the browser, following the script exactly, including one live line and both exports. Fix only what blocks the script.
- [ ] 7:30–8:00: record the rehearsal to `docs/demo-backup.mp4` (screen recording with voice).
- [ ] `docs/nemotron.md`, under 700 words: what each Nemotron model does here and why that model; why numbers and the verdict floor are deterministic; what the model adds beyond the rules (class C results); the evaluation table copied from `results.json`; the prompt change made after the first evaluation run, if any; the extraction totals; the model-ID finding from `docs/model_probe.md`. Every number comes from a generated file.
- [ ] `README.md`: setup, environment variables, how to fetch the PDFs in `SOURCES.md`, run commands, test commands, the four modes, links to the two docs.
- [ ] 8:30: code freeze. Run section 9's checklist. Push the final state to `origin main` when the human running the chat asks.

**Pitfalls:** No rule or threshold changes in this phase. No extraction on stage. Do not leave the recording to the end.

**Done when:** a cold start plus the demo script works in `cache` mode with the network cable out, and the video file exists.

### Phase 9 — Stretch: power tree assistant

Start only if Phase 8's rehearsal passed and it is before 8:00 PM. Otherwise skip it entirely.

- **Goal:** The user enters an input voltage and up to three rails (voltage, current). The app proposes up to three architectures from catalog bucks and LDOs and compares efficiency, heat, and cost.
- **Files:** `backend/app/power_tree.py`, `POST /api/power-tree`, `frontend/src/components/PowerTree.tsx`, `backend/tests/test_power_tree.py`.
- **Rules:** LDO efficiency is `vout / vin`; LDO heat is `(vin - vout) * iout`. Buck efficiency comes from an optional `efficiency` spec field; when it is null the option is shown as "efficiency not in catalog" and ranked last, never given an assumed number. No model calls. Rank by total loss, then part count.
- **Done when:** rails `5 V @ 0.5 A` and `3.3 V @ 0.2 A` from 24 V return options the panel renders, and the test checks the LDO arithmetic. If it is not working by 8:30 PM, remove the panel from the page.

## 8. Testing Plan

Everything runs from the repo root in the 3.11 venv.

```
source .venv/bin/activate
pytest -q                                   # whole suite; no network, no API key
```

Per phase:

```
pytest -q backend/tests/test_examples_match_models.py                      # Phase 0
pytest -q backend/tests/test_units.py backend/tests/test_bom.py backend/tests/test_requirements.py
pytest -q backend/tests -k "compare or package or headline or verdict or candidates or decide"
pytest -q backend/tests/test_specs_valid.py backend/tests/test_manifest.py  # Phase 1 data gate
pytest -q backend/tests/test_api.py                                         # Phase 3
pytest -q backend/tests/test_agent_loop.py                                  # Phase 5
pytest -q backend/tests/test_extract.py                                     # Phase 6
pytest -q backend/tests/test_eval.py                                        # Phase 7
```

Servers and scripts:

```
uvicorn app.main:app --app-dir backend --port 8000 --reload     # development
uvicorn app.main:app --app-dir backend --port 8000              # demo (no --reload)
cd frontend && npm install && npm run dev
cd frontend && npm run build

python backend/scripts/probe_models.py
python backend/scripts/record_fixture.py --mode deterministic
python backend/scripts/build_excerpts.py
python backend/scripts/extraction_report.py
cd backend && python -m app.eval.run_eval --arms baseline,rules
cd backend && python -m app.eval.run_eval --arms super
cd backend && python -m app.eval.run_eval --arms bolt
```

Scripts in `backend/scripts/` add `backend/` to `sys.path` themselves so they run from the repo root.

**Unit tests** (Phase 2): unit normalization, BOM parsing, per-category comparison rules, unknown handling, package and pinout, headline check, verdict floor, ranking, decision assembly.

**Data tests** (Phase 1 gate): `test_specs_valid.py` checks every spec file; `test_manifest.py` checks that the demo BOM produces the three beats from real data.

**Agent tests** (Phase 5): scripted `FakeClient` only. Valid tool calls, schema-valid output, guardrail tightening, stricter model verdicts kept, unknown candidate, invalid arguments, unknown tool, invalid verdict, content-JSON recovery, timeout, 429 retry, max turns, cache hit and miss.

**Extraction tests** (Phase 6): grounding, value/raw agreement, tolerant JSON parsing, Parse fallback, unreadable PDF. Extraction on known datasheets is measured by `extraction_report.json` against the verified specs (it needs the API, so it is a script, not a pytest).

**Integration** (Phase 3): `test_api.py` runs `fixture` and `deterministic` modes through the HTTP layer with no network.

**Evaluation run** (Phase 7): `test_eval.py` checks the pair set's structure; `run_eval.py` produces the numbers.

**Manual demo script** (until `docs/demo_script.md` exists):

1. Open `http://127.0.0.1:5173`. Click "Load demo BOM". Confirm 24 V / 32 V, −40 to 85 °C, Diodes Incorporated, lowest risk.
2. Run in `deterministic` mode (or `cache` once warmed). Every row gets a badge.
3. D1: green, recommends B0540W-7-F, Traps shows 2 rejected. Detail lists B0520LW-7-F and B0530W-7-F with the Vrrm reason and the cross-reference label.
4. U2: gold, recommends AP7333-33SRG-7, caveat rows highlighted (quiescent current, dropout). Rejected list shows AP7333-33SAG-7 with the pinout reason.
5. Agent tab shows the steps for the selected line. In `cache` or `live` mode it includes reasoning and tool calls.
6. "Run live on this line" on D1 completes and shows `source: model`.
7. Evaluation panel numbers equal `data/eval/results.json`.
8. Export BOM and risk report; open both; D1 and U2 match the screen.

**Error paths:**

| Path | How to trigger | Expected |
| --- | --- | --- |
| Malformed BOM | Header `ref,manufacturer,part,qty` | 400; the form lists the error; no run |
| Bad row | `qty` of `two`; duplicate `ref`; 16 fields | 400 with the row number |
| Unknown part | Row with `ZZZ999` | Run completes; that line is `no_safe_match`, "not in the local catalog" |
| No candidates | A category with only the original | `no_safe_match`, `compared_mpn` null |
| Missing spec | Set a candidate's `vrrm_v` value to null | `unknown` in the table; floor `no_safe_match` |
| Datasheet missing | Delete a PDF | Page citations render as plain text; excerpt tool returns `no_excerpt`; run completes |
| Unparseable PDF | Zero-byte file, `POST /api/extract/{mpn}` | `{error: "unreadable_pdf"}`, HTTP 200, no traceback |
| API down | `NVIDIA_BASE_URL=http://127.0.0.1:9`, `mode=live` | Each line retries, then `part_error` and a fallback decision; `run_completed` arrives |
| No key | `mode=live` with empty key | SSE `error`: `NVIDIA_API_KEY is not set` |
| Rate limited | FakeClient: 429, 429, success | Decision with `source: model` |
| Malformed model output | FakeClient: arguments `not json`; verdict `perfect` | Tool error, then fallback; stored verdict is one of the four |
| Cache miss on stage | `mode=cache` after changing the goal | Lines run deterministically at once; no live call |

## 9. Validation Checklist

Before calling any phase done:

- [ ] `pytest -q` passes in the 3.11 venv. Tests for phases not yet built may be absent, but none are deleted or weakened to get green.
- [ ] The phase's "Done when" is met, including the browser check for anything that touched the UI.
- [ ] No dependency beyond `backend/requirements.txt` (Phase 0) and the frontend packages (Phase 4).
- [ ] Only `agent/client.py`, `extract/parse_api.py`, and `scripts/probe_models.py` create network clients.
- [ ] Field names, event shapes, and function names match section 4 and the tables in section 7. Any contract change went through the Lead and updated `PLAN.md`, `schemas.py`, and `shared/examples/` together.
- [ ] Every `verified: true` value was checked by a person against the cited page.
- [ ] Nothing staged that should not be: `.env`, PDFs, `data/cache/`, `data/specs/extracted/`, the API key anywhere.
- [ ] Every number in a doc or on screen comes from a generated file.
- [ ] You wrote a short handoff note in the chat: what was built, the test command and result, what you could not verify, and what the next phase needs.

## 10. Suggested Execution Order

| Time | Lead | Data | Backend | Frontend |
| --- | --- | --- | --- | --- |
| 1:00–2:00 | Phase 0 | Tier A PDFs; draft specs from section 4.5 | Phase 2: `units.py`, `bom.py` with tests | Phase 4: scaffold, types, layout, static render |
| 2:00–3:15 | Phase 3 | Tier A verified by 3:00; catalog, BOM, manifest | Phase 2: compare, package, headline, verdict, decide | Phase 4 against the fixture stream |
| 3:15–4:00 | Phase 3 deterministic wiring; start Phase 5a | Fix data until `test_manifest.py` is green; record fixture | Phase 5a: tools, loop, tests | Deterministic mode end to end; rejected list |
| **4:00** | **Checkpoint 1:** demo BOM through `deterministic` mode in the browser, with D1 green plus two rejected traps, U2 gold, detail view, both exports. If red, everyone works on Phases 2–4 until it is green. | | | |
| 4:00–4:30 | Phase 5a live line | Tier B | Phase 5a | Checkpoint fixes |
| **4:30** | **Checkpoint 2:** one line decided live by Nemotron in the browser. If no working model or key, say so now and continue with `deterministic`. | | | |
| 4:30–5:45 | Phase 6 (excerpts first) | Tier B until 5:00; then eval pairs and `SYN-` specs | Phase 5b | Live-line button, datasheet links, trace polish |
| 5:45–7:15 | Phase 6 report; draft `docs/nemotron.md` and README | Finish pairs by 6:00; verify extraction mismatches; `docs/demo_script.md` | Phase 7 | Eval panel, extraction check, projector pass |
| 7:15–8:30 | Phase 8: warm cache, rehearse, **record video by 8:00**, finish writeup | | | |
| 8:30–9:00 | Code freeze, checklist, submit. Buffer. | | | |

Dependencies: Phase 0 blocks nothing at the start (contracts are in this file) but its schemas are needed by 2:00. Phase 3's deterministic mode needs Phase 2. Phase 5 needs Phases 2 and 3. Phase 6's excerpts feed Phase 5b's live runs but are not required by them. Phase 7's model arms need Phase 5a and the pairs. Phase 1 feeds the demo and the evaluation and never blocks code, because every code test uses its own fixture parts.

**Minimum path for one or two people:** Phase 0 → Phase 2 → Phase 1 Tier A → Phase 3 → Phase 4 → Phase 5a → Phase 7 with `baseline,rules,super` → Phase 8. Skip Tier B, Phase 5b's live fixture, Phase 6's extraction (keep `build_excerpts.py`), the Bolt arm, and Phase 9.

## 11. Cut List

Drop from the top when behind. Decide at each checkpoint, not at 8 PM.

1. Phase 9 power tree.
2. Tier B lines U1 (buck) and D3 (ESD).
3. Extraction check panel in the UI (keep the report numbers in the writeup).
4. The Bolt evaluation arm.
5. Phase 6 extraction altogether (keep `build_excerpts.py`; the writeup then describes extraction as designed, not measured).
6. The remaining Tier B lines. The demo works with D1 and U2 alone.
7. Datasheet page links, price and lead-time ranking (the goal selector stays; with null prices all goals rank like `lowest_risk`).
8. The prompt-improvement loop in Phase 7.
9. The Super evaluation arm (the table then shows baseline vs rules only, and the writeup says so).
10. Live mode on stage: show `cache` or `deterministic` plus the video.

Never cut: the verdict floor and its tests, Tier A data verified against the PDFs, the rejected-trap display, `deterministic` mode, the results table and one detail view, the BOM export, the README, the backup video, and the Nemotron writeup.

## 12. Final Notes for the Executor

- Do your phase only. Finish with the handoff note from section 9.
- Use `/opt/homebrew/bin/python3.11` for the venv on this machine. `python3` is 3.14.
- Commit and push only when asked. The remote is `origin` (`sohamjad789/tinyml-edge-vs-cloud`), branch `main`.
- If something in this plan is impossible or contradicts what you find, stop and report which sentence, rather than quietly doing something else. Contract changes go through the Lead.
- The datasheet facts in section 5 and the roles in Phase 1 are leads from a web search. The PDF decides. When the PDF disagrees, change the data or the part, not `data/categories.json`.
- Pin numbering is never portable between vendors or even between suffixes of one part (AP7333 SA vs SR). Read the page.
- Search must return bad candidates. Filtering them out removes the thing the demo exists to show.
- The trap is a rejected candidate on a line that still gets a recommendation. Do not remove good parts from the catalog to force a red row.
- The model is never the source of a number, and never the source of a more lenient verdict. Keep `model_verdict` so the evaluation can show what the model did on its own.
- Unknown is not pass. A critical spec that cannot be verified is `no_safe_match`.
- Bolt: one tool call per turn, tool result directly after the assistant message. Super: thinking tokens count against `max_tokens`.
- Parse takes one page image per request and returns Markdown with coordinate tokens. The old `nvidia/nemotron-parse` chat endpoint is deprecated.
- Free-tier limit is about 40 requests per minute, shared. Keep concurrency at 3, cache everything, and never run the evaluation or a full live BOM while someone is presenting.
- Delete `data/cache/` after changing specs; bump `PROMPT_VERSION` after changing a prompt.
- Report evaluation numbers as measured, including unflattering ones. Omit what did not run.
- Record the backup video at 7:30 PM even if something is still rough.
