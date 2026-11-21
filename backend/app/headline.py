"""What a naive cross-reference tool checks (PLAN.md section 4.6). Never reads pinout, requirements, or conditions."""

from typing import Optional

from app.package import normalize_package
from app.schemas import PartSpec


def _value(part: PartSpec, key: str) -> Optional[float]:
    field = part.specs.get(key)
    return field.value if field else None


def _at_least(original: PartSpec, candidate: PartSpec, key: str, factor: float = 1.0) -> bool:
    o, c = _value(original, key), _value(candidate, key)
    return o is not None and c is not None and c >= o * factor


def headline_match(original: PartSpec, candidate: PartSpec) -> bool:
    if original.category != candidate.category:
        return False
    if normalize_package(original.package.code) != normalize_package(candidate.package.code):
        return False
    category = original.category.value
    if category == "ldo":
        o, c = _value(original, "vout_v"), _value(candidate, "vout_v")
        vout_ok = o is not None and c is not None and o != 0 and abs(c - o) / abs(o) <= 0.05
        return vout_ok and _at_least(original, candidate, "iout_max_a")
    if category == "buck":
        return _at_least(original, candidate, "iout_max_a") and _at_least(original, candidate, "vin_max_v")
    if category == "schottky":
        return _at_least(original, candidate, "if_avg_a", 0.8)
    if category == "mosfet":
        return _at_least(original, candidate, "vds_max_v") and _at_least(original, candidate, "id_max_a")
    if category == "esd":
        return _at_least(original, candidate, "vrwm_v")
    return False
