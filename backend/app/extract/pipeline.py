"""Offline PDF-to-provisional-spec extraction. Never replaces verified catalog specs."""

import json
from pathlib import Path
from typing import Any

from app.agent.client import make_client
from app.catalog import load_json, load_part
from app.paths import data_dir
from app.extract.parse_api import parse_page
from app.extract.pdf_pages import page_png, page_texts
from app.extract.structure import structure_page


def _safe_name(mpn: str) -> str:
    return mpn.replace("/", "_")


def _field_names(category: str) -> list[str]:
    policy = load_json("categories.json")[category]["checks"]
    return [item["key"] for item in policy if item["where"] == "specs"]


def _pdf_path(mpn: str) -> Path | None:
    part = load_part(mpn)
    if part is None or not part.datasheet_filename:
        return None
    path = data_dir() / "datasheets" / part.datasheet_filename
    return path if path.is_file() else None


def extract_part(mpn: str, *, client: Any = None) -> dict[str, Any]:
    part = load_part(mpn)
    if part is None:
        return {"error": "unknown_mpn"}
    path = _pdf_path(mpn)
    pages = page_texts(path) if path else []
    if not pages:
        return {"error": "unreadable_pdf"}
    fields = _field_names(part.category.value)
    client = client or make_client()
    merged = {key: {"value": None, "raw": None, "condition": None, "page": None, "table": None} for key in fields}
    parser = "pdf_text"
    for entry in pages[:4]:
        page, text = int(entry["page"]), str(entry["text"])
        parsed_text = parse_page(page_png(path, page)) if path else None
        if parsed_text:
            text, parser = parsed_text, "nemotron_parse"
        structured = structure_page(client, part.mpn, part.category.value, fields, page, text)
        for key, field in structured.items():
            if merged[key]["value"] is None and field.get("value") is not None:
                merged[key] = field | {"page": page, "table": None}
    output = {"mpn": part.mpn, "manufacturer": part.manufacturer, "category": part.category.value,
              "verified": False, "synthetic": False, "parser": parser, "specs": merged}
    destination = data_dir() / "specs" / "extracted" / f"{_safe_name(part.mpn)}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return output
