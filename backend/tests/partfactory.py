"""Test parts built from `fixtures/parts/{category}.json` with overrides, and temporary catalogs."""

import copy
import json
import shutil
from pathlib import Path

from app.paths import repo_root
from app.schemas import PartSpec, Requirements
from app.units import format_quantity

PARTS_DIR = Path(__file__).parent / "fixtures" / "parts"
POLICY_FILES = ["categories.json", "package_aliases.json", "pin_functions.json", "topics.json"]
MISSING = object()


def part(category: str, mpn: str | None = None, *, specs: dict | None = None, **root) -> PartSpec:
    """`specs={"vrrm_v": 20}` sets a value, `None` nulls it, `MISSING` removes the key."""
    data = copy.deepcopy(json.loads((PARTS_DIR / f"{category}.json").read_text(encoding="utf-8")))
    if mpn:
        data["mpn"] = mpn
    for key, value in (specs or {}).items():
        if value is MISSING:
            data["specs"].pop(key, None)
        else:
            field = data["specs"].setdefault(key, {"condition": "test", "page": 2, "table": "test"})
            field["value"] = value
            field["raw"] = None if value is None else format_quantity(value, key)
    data.update(root)
    if "pinout" in root and root["pinout"] is not None and "package" not in root:
        data["package"]["pins"] = len(root["pinout"])
    return PartSpec.model_validate(data)


def pins(*functions: str) -> list[dict]:
    return [{"pin": i + 1, "name": f.upper(), "functions": [f]} for i, f in enumerate(functions)]


def reqs(**values) -> Requirements:
    return Requirements(**values)


def install_catalog(root: Path, monkeypatch, parts: list[PartSpec]) -> Path:
    for name in POLICY_FILES:
        shutil.copy(repo_root() / "data" / name, root / name)
    (root / "specs").mkdir(exist_ok=True)
    catalog = []
    for p in parts:
        filename = f"{p.mpn.replace('/', '_')}.json"
        (root / "specs" / filename).write_text(p.model_dump_json(), encoding="utf-8")
        catalog.append({"mpn": p.mpn, "manufacturer": p.manufacturer, "category": p.category.value,
                        "description": p.description, "spec_file": f"specs/{filename}"})
    (root / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setenv("PARTSWAP_DATA_DIR", str(root))
    return root
