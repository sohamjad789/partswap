"""Catalog and policy files under `data/`. Read on every call so spec edits show up without a restart."""

import json
from typing import Any, Optional

from app.paths import data_dir
from app.schemas import PartSpec


def load_json(name: str) -> Any:
    return json.loads((data_dir() / name).read_text(encoding="utf-8"))


def _entries() -> list[dict[str, Any]]:
    path = data_dir() / "catalog.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_entry(entry: dict[str, Any]) -> PartSpec:
    return PartSpec.model_validate_json((data_dir() / entry["spec_file"]).read_text(encoding="utf-8"))


def load_part(mpn: str) -> Optional[PartSpec]:
    wanted = mpn.strip().lower()
    for entry in _entries():
        if entry["mpn"].lower() == wanted:
            return _load_entry(entry)
    return None


def all_parts() -> list[PartSpec]:
    return [_load_entry(entry) for entry in _entries()]
