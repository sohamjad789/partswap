"""Parse datasheet and BOM notation into SI numbers, and format SI numbers for display."""

import math
import re
from dataclasses import dataclass

PREFIXES = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}
PREFIX_ALIASES = {"P": "p", "N": "n", "U": "u", "K": "k", "g": "G"}  # m and M are never folded
BASES = {"v": "V", "a": "A", "ohm": "ohm", "r": "ohm", "hz": "Hz", "c": "C", "f": "F"}
RKM_UNITS = {"V": ("V", 1.0), "A": ("A", 1.0), "R": ("ohm", 1.0), "k": ("ohm", 1e3), "M": ("ohm", 1e6)}

_NUMBER = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_QUANTITY = re.compile(rf"^({_NUMBER})([pnumkMG]?)(V|A|ohm|R|Hz|C|F)?$", re.IGNORECASE)
_RKM = re.compile(r"^(\d+)([VARkM])(\d+)$")
_RANGE_SPLIT = re.compile(r"\s*(?:\bto\b|~|…|\.\.\.)\s*")


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str  # "V", "A", "ohm", "Hz", "C", "F", or "" for a bare number


def _clean(value: float) -> float:
    return float(f"{value:.12g}")


def _normalize(text: str) -> str:
    text = text.replace("\u2212", "-").replace("±", "").replace("\u00b5", "u").replace("\u03bc", "u")
    text = text.replace("Ω", "ohm").replace("°", "")
    text = re.sub(r"\s+", "", text)
    return re.sub(r"(?i)ohms$", "ohm", text)


def parse_quantity(text: str) -> Quantity:
    s = _normalize(text)
    rkm = _RKM.match(s)
    if rkm:
        unit, scale = RKM_UNITS[rkm.group(2)]
        return Quantity(_clean(float(f"{rkm.group(1)}.{rkm.group(3)}") * scale), unit)
    m = _QUANTITY.match(s)
    if not m:
        raise ValueError(f"cannot parse quantity {text!r}")
    number, prefix, base = m.groups()
    if base is None:
        if prefix:
            raise ValueError(f"prefix without unit in {text!r}")
        return Quantity(_clean(float(number)), "")
    unit = BASES[base.lower()]
    prefix = PREFIX_ALIASES.get(prefix, prefix)
    if unit == "C" and prefix:
        raise ValueError(f"temperature with a prefix in {text!r}")
    return Quantity(_clean(float(number) * PREFIXES[prefix]), unit)


def parse_range(text: str) -> tuple[float, float]:
    parts = _RANGE_SPLIT.split(text.replace("\u2212", "-").strip())
    if len(parts) != 2:
        raise ValueError(f"cannot parse range {text!r}")
    low, high = (parse_quantity(p) for p in parts)
    if low.unit and high.unit and low.unit != high.unit:
        raise ValueError(f"mixed units in range {text!r}")
    return low.value, high.value


# ---------------------------------------------------------------- display

_ENGINEERING = {"_v": "V", "_a": "A", "_ohm": "Ω", "_hz": "Hz"}
_FIXED = {"_c": "°C", "_pf": "pF", "_kv": "kV"}
_SYMBOLS = {-12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}


def _suffix(key: str) -> str:
    return "_" + key.rsplit("_", 1)[-1] if "_" in key else ""


def format_quantity(value: float, key: str) -> str:
    """`format_quantity(0.15, "iout_a") == "150 mA"`. The unit comes from the key suffix."""
    suffix = _suffix(key)
    if suffix in _FIXED:
        return f"{value:.4g} {_FIXED[suffix]}"
    if suffix not in _ENGINEERING:
        return f"{value:g}"
    if value == 0:
        return f"0 {_ENGINEERING[suffix]}"
    exp = max(-12, min(9, int(math.floor(math.log10(abs(value)) / 3) * 3)))
    scaled = value / 10**exp
    if abs(float(f"{scaled:.3g}")) >= 1000 and exp < 9:
        exp += 3
        scaled = value / 10**exp
    return f"{scaled:.3g} {_SYMBOLS[exp]}{_ENGINEERING[suffix]}"
