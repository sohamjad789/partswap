"""Datasheet excerpt retrieval for the `get_datasheet_excerpt` tool (PLAN.md sections 4.9 and Phase 2)."""

import json
from typing import Any

from app.catalog import load_json, load_part
from app.paths import data_dir

MAX_CHUNKS = 2
MAX_CHARS = 1500


def excerpt_for(mpn: str, topic: str) -> dict[str, Any]:
    keywords = load_json("topics.json").get(topic)
    if keywords is None:
        return {"error": "unknown_topic"}
    part = load_part(mpn)
    name = part.mpn if part else mpn.strip()
    path = data_dir() / "excerpts" / f"{name.replace('/', '_')}.json"
    if not path.exists():
        return {"error": "no_excerpt"}
    chunks = json.loads(path.read_text(encoding="utf-8")).get("chunks", [])

    scored = []
    for index, chunk in enumerate(chunks):
        text = chunk["text"].lower()
        score = sum(text.count(k.lower()) for k in keywords)
        if score:
            scored.append((-score, index, chunk))
    if not scored:
        return {"error": "no_excerpt"}

    out, budget = [], MAX_CHARS
    for _, _, chunk in sorted(scored)[:MAX_CHUNKS]:
        if budget <= 0:
            break
        text = chunk["text"][:budget]
        budget -= len(text)
        out.append({"page": chunk["page"], "text": text})
    return {"mpn": name, "topic": topic, "chunks": out}
