"""Probe NVIDIA model IDs for plain completion, tool calling, and Parse; write docs/model_probe.md.

Run from the repo root: python backend/scripts/probe_models.py
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.paths import repo_root  # noqa: E402

SUPER_CANDIDATES = [
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
]
FAST_CANDIDATES = [
    "nvidia/nemotron-3.5-bolt-e4b",
    "stg/nvidia/nemotron-3.5-bolt-e4b",
]
TIMEOUT_S = 60
OUTPUT = repo_root() / "docs" / "model_probe.md"

GET_PART_SPECS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_part_specs",
        "description": "Return the verified spec record for one manufacturer part number.",
        "parameters": {
            "type": "object",
            "properties": {"mpn": {"type": "string", "description": "Manufacturer part number"}},
            "required": ["mpn"],
        },
    },
}
TOOL_USER_MESSAGE = "Look up the specs for part MBR0540T1G."
TOOL_RESULT = {"mpn": "MBR0540T1G", "category": "schottky", "specs": {"vrrm_v": {"value": 40, "raw": "40 V"}}}


@dataclass
class TestResult:
    name: str
    ok: Optional[bool] = None  # None = skipped
    status: str = "-"
    latency_ms: Optional[int] = None
    note: str = ""


@dataclass
class ProbeRow:
    model_id: str
    role: str
    thinking: bool
    tests: list[TestResult] = field(default_factory=list)

    @property
    def tool_ready(self) -> bool:
        return all(t.ok for t in self.tests)


def completion_kwargs(model_id: str, thinking: bool, tools: bool) -> dict[str, Any]:
    extra: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": thinking}}
    if "bolt" in model_id:
        extra["skip_special_tokens"] = False
    kwargs: dict[str, Any] = {
        "model": model_id,
        "temperature": 0.2,
        "top_p": 0.95,
        "max_tokens": 4096,
        "extra_body": extra,
    }
    if tools:
        kwargs["tools"] = [GET_PART_SPECS_TOOL]
        kwargs["parallel_tool_calls"] = False
    return kwargs


def call(client, kwargs: dict[str, Any]) -> tuple[Any, str, int, str]:
    """Return (response or None, status, latency_ms, error note). Never includes the key."""
    import openai

    start = time.monotonic()
    try:
        response = client.chat.completions.create(**kwargs)
        return response, "200", int((time.monotonic() - start) * 1000), ""
    except openai.APIStatusError as exc:
        return None, str(exc.status_code), int((time.monotonic() - start) * 1000), short(exc.message)
    except openai.APIError as exc:
        return None, type(exc).__name__, int((time.monotonic() - start) * 1000), short(str(exc))


def short(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split()).replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def probe_chat(client, model_id: str, role: str, thinking: bool) -> ProbeRow:
    row = ProbeRow(model_id, role, thinking)

    plain = TestResult("plain")
    response, plain.status, plain.latency_ms, plain.note = call(
        client,
        completion_kwargs(model_id, thinking, tools=False)
        | {"messages": [{"role": "user", "content": "Reply with the single word: ready"}]},
    )
    if response is not None:
        content = response.choices[0].message.content or ""
        plain.ok = bool(content.strip())
        plain.note = short(f"finish={response.choices[0].finish_reason}; reply={content.strip()[:40]!r}")
    else:
        plain.ok = False
    row.tests.append(plain)

    tool = TestResult("tool_call")
    messages: list[dict[str, Any]] = [{"role": "user", "content": TOOL_USER_MESSAGE}]
    response, tool.status, tool.latency_ms, tool.note = call(
        client, completion_kwargs(model_id, thinking, tools=True) | {"messages": messages}
    )
    tool_call = None
    if response is not None:
        message = response.choices[0].message
        calls = message.tool_calls or []
        tool.ok = bool(calls) and calls[0].function.name == "get_part_specs"
        if tool.ok:
            tool_call = calls[0]
            tool.note = short(f"args={tool_call.function.arguments}")
        else:
            tool.note = short(f"finish={response.choices[0].finish_reason}; no get_part_specs call; content={(message.content or '')[:60]!r}")
    else:
        tool.ok = False
    row.tests.append(tool)

    follow = TestResult("tool_result")
    if tool_call is None:
        follow.note = "skipped: no tool call to answer"
        row.tests.append(follow)
        return row
    messages += [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {"name": tool_call.function.name, "arguments": tool_call.function.arguments},
                }
            ],
        },
        {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(TOOL_RESULT)},
    ]
    response, follow.status, follow.latency_ms, follow.note = call(
        client, completion_kwargs(model_id, thinking, tools=True) | {"messages": messages}
    )
    if response is not None:
        content = response.choices[0].message.content or ""
        follow.ok = bool(content.strip())
        follow.note = short(f"finish={response.choices[0].finish_reason}; reply={content.strip()[:60]!r}")
    else:
        follow.ok = False
    row.tests.append(follow)
    return row


def one_page_png() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 120), "VRRM 40 V", fontsize=24)
    png = page.get_pixmap(dpi=150).tobytes("png")
    doc.close()
    return png


def find_content(payload: Any) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("content"), str):
            return payload["content"]
        return " ".join(find_content(v) for v in payload.values())
    if isinstance(payload, list):
        return " ".join(find_content(v) for v in payload)
    return ""


def probe_parse(url: str, api_key: str) -> TestResult:
    import httpx

    result = TestResult("parse")
    start = time.monotonic()
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            files={"document": ("page.png", one_page_png(), "image/png")},
            data={"options": json.dumps({"decoding": {"max_output_tokens": 1024}})},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        result.ok, result.status, result.note = False, type(exc).__name__, short(str(exc))
        result.latency_ms = int((time.monotonic() - start) * 1000)
        return result
    result.latency_ms = int((time.monotonic() - start) * 1000)
    result.status = str(response.status_code)
    if response.status_code != 200:
        result.ok, result.note = False, short(response.text)
        return result
    try:
        content = find_content(response.json())
    except ValueError:
        content = response.text
    result.ok = "40" in content
    result.note = short(f"content={content[:80]!r}")
    return result


def fitz_status() -> str:
    try:
        import pymupdf

        return f"ok (PyMuPDF {pymupdf.VersionBind})"
    except Exception as exc:  # noqa: BLE001
        return f"failed: {type(exc).__name__}: {exc}"


def mark(ok: Optional[bool]) -> str:
    return "skip" if ok is None else ("pass" if ok else "FAIL")


def choose(rows: list[ProbeRow], role: str) -> Optional[ProbeRow]:
    """First ID in preference order that passes every test; thinking on preferred over off."""
    ordered = SUPER_CANDIDATES if role == "super" else FAST_CANDIDATES
    for model_id in ordered:
        for thinking in (True, False):
            for row in rows:
                if row.role == role and row.model_id == model_id and row.thinking == thinking and row.tool_ready:
                    return row
    return None


def write_report(lines: list[str]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(repo_root())}")


def main() -> int:
    settings = get_settings()
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    header = [
        "# Model probe",
        "",
        f"Generated by `backend/scripts/probe_models.py` at {stamp}.",
        "",
        f"- `import pymupdf` (fitz) in this venv: {fitz_status()}",
    ]
    if not settings.has_api_key:
        write_report(header + ["", "not run: no NVIDIA_API_KEY"])
        return 0

    from openai import OpenAI

    client = OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key, timeout=TIMEOUT_S, max_retries=0)
    rows: list[ProbeRow] = []
    for role, candidates in (("super", SUPER_CANDIDATES), ("fast", FAST_CANDIDATES)):
        for model_id in candidates:
            for thinking in (True, False):
                print(f"probing {model_id} thinking={'on' if thinking else 'off'} …", flush=True)
                rows.append(probe_chat(client, model_id, role, thinking))
    print("probing parse …", flush=True)
    parse = probe_parse(settings.parse_url, settings.nvidia_api_key)

    super_row, fast_row = choose(rows, "super"), choose(rows, "fast")
    lines = header + [
        f"- Base URL: `{settings.nvidia_base_url}`",
        "",
        "## Chat models",
        "",
        "Tests: **plain** = one completion; **tool_call** = offered `get_part_specs(mpn)` with "
        f"\"{TOOL_USER_MESSAGE}\" and checked `tool_calls[0].function.name == \"get_part_specs\"`; "
        "**tool_result** = sent the tool result back and checked for a normal reply.",
        "",
        "| Role | Model ID | Thinking | Test | Result | HTTP | Latency ms | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        for t in row.tests:
            latency = "-" if t.latency_ms is None else str(t.latency_ms)
            lines.append(
                f"| {row.role} | `{row.model_id}` | {'on' if row.thinking else 'off'} | {t.name} | "
                f"{mark(t.ok)} | {t.status} | {latency} | {t.note} |"
            )
    parse_latency = "-" if parse.latency_ms is None else str(parse.latency_ms)
    lines += [
        "",
        "## Parse",
        "",
        "One-page PDF rendered in memory with PyMuPDF (text `VRRM 40 V`), converted to PNG at 150 DPI, "
        "POSTed as multipart `document`; pass when `content` contains `40`.",
        "",
        "| URL | Result | HTTP | Latency ms | Note |",
        "| --- | --- | --- | --- | --- |",
        f"| `{settings.parse_url}` | {mark(parse.ok)} | {parse.status} | {parse_latency} | {parse.note} |",
        "",
        "## Chosen",
        "",
    ]
    for label, env_name, row in (("Reasoning", "NEMOTRON_SUPER_MODEL", super_row), ("Fast", "NEMOTRON_FAST_MODEL", fast_row)):
        if row is None:
            lines.append(f"- {label}: none passed all three tests. Keep `deterministic` / `cache` modes.")
        else:
            lines.append(
                f"- {label}: `{env_name}={row.model_id}`, `enable_thinking={row.thinking}`."
            )
    lines.append(f"- Parse: {'usable' if parse.ok else 'not usable; extraction falls back to PDF text'}.")
    write_report(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
