"""Phase 1 data gate: every spec file under the real `data/` is usable by the comparison."""

import json

import pytest

from app.paths import repo_root
from app.schemas import PartSpec, PinFunction

DATA = repo_root() / "data"
SPEC_FILES = sorted((DATA / "specs").glob("*.json")) if (DATA / "specs").exists() else []

pytestmark = pytest.mark.skipif(not SPEC_FILES, reason="data/specs/ is empty")


def load_spec(path):
    return PartSpec.model_validate_json(path.read_text(encoding="utf-8"))


def categories():
    return json.loads((DATA / "categories.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SPEC_FILES, ids=lambda p: p.name)
def test_spec_validates_and_is_complete(path):
    spec = load_spec(path)
    assert path.name == f"{spec.mpn.replace('/', '_')}.json"
    if spec.synthetic:
        assert spec.mpn.startswith("SYN-")
    if spec.pinout is not None:
        assert spec.package.pins == len(spec.pinout)
        allowed = set(PinFunction.__args__)
        assert {f for pin in spec.pinout for f in pin.functions} <= allowed
    if not spec.verified:
        return
    assert spec.pinout, f"{spec.mpn}: verified part needs a pinout"
    for check in categories()[spec.category.value]["checks"]:
        key = check["key"]
        if check["where"] == "root":
            assert getattr(spec, key) is not None, f"{spec.mpn}: root field {key} missing"
            continue
        if check.get("only_when_output_type") and spec.output_type != check["only_when_output_type"]:
            continue
        assert key in spec.specs, f"{spec.mpn}: spec {key} missing"
        field = spec.specs[key]
        if field.value is not None:
            assert field.raw and field.condition and field.page, f"{spec.mpn}: {key} needs raw, condition, and page"


def test_catalog_entries_point_at_files():
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    mpns = [e["mpn"] for e in catalog]
    assert len(mpns) == len({m.lower() for m in mpns}), "duplicate MPN in catalog"
    for entry in catalog:
        spec = load_spec(DATA / entry["spec_file"])
        assert spec.mpn == entry["mpn"]
        assert spec.category.value == entry["category"]
