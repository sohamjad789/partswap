"""Fast-model JSON extraction plus deterministic grounding checks."""

import json
import re
from typing import Any

from app.agent.client import completion_kwargs
from app.agent.prompts import STRUCTURE_PROMPT
from app.config import get_settings
from app.units import parse_quantity


def _first_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value if isinstance(value, dict) else None
        except ValueError:
            continue
    return None


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def grounding_check(fields: dict[str, Any], page_text: str) -> dict[str, dict[str, Any]]:
    """Keep only raw text grounded in this page and numerically consistent when unit-bearing."""
    out: dict[str, dict[str, Any]] = {}
    source = _normalized(page_text)
    for key, value in fields.items():
        item = value if isinstance(value, dict) else {}
        raw, number, condition = item.get("raw"), item.get("value"), item.get("condition")
        clean = {"value": None, "raw": None, "condition": None}
        if raw is None or number is None:
            out[key] = clean
            continue
        raw_text = str(raw)
        if _normalized(raw_text) not in source:
            out[key] = clean
            continue
        try:
            parsed = parse_quantity(raw_text)
            if parsed.unit and abs(float(number) - parsed.value) > max(abs(parsed.value), 1e-12) * 0.01:
                out[key] = clean
                continue
        except (TypeError, ValueError):
            pass  # Bare table values are valid when their column supplies the unit.
        out[key] = {"value": float(number), "raw": raw_text, "condition": str(condition or "")}
    return out


def structure_page(client: Any, mpn: str, category: str, field_names: list[str], page: int, text: str) -> dict[str, dict[str, Any]]:
    prompt = STRUCTURE_PROMPT.format(mpn=mpn, category=category, field_names=field_names, page=page, text=text)
    settings = get_settings()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        **completion_kwargs(settings.fast_model),
    )
    content = response.choices[0].message.content or ""
    parsed = _first_object(content) or {}
    requested = {key: parsed.get(key) for key in field_names}
    return grounding_check(requested, text)
