"""Package code and pin-function comparison (PLAN.md section 4.6)."""

import re
from typing import Optional

from app.catalog import load_json
from app.schemas import CheckResult, PackageComparison, PackagePinoutResult, PartSpec, PinoutComparison


def normalize_package(code: str) -> str:
    cleaned = re.sub(r"\([^)]*\)$", "", code.upper().replace(" ", ""))
    return load_json("package_aliases.json").get(cleaned, cleaned)


def normalize_pin_name(name: str) -> str:
    return load_json("pin_functions.json").get(name.upper().replace(" ", ""), "unknown")


def pin_map(part: PartSpec) -> Optional[dict[str, list[str]]]:
    if not part.pinout:
        return None
    return {str(p.pin): sorted(p.functions) for p in sorted(part.pinout, key=lambda p: p.pin)}


def _functions(fns: Optional[list[str]]) -> str:
    return " + ".join(fns) if fns else "absent"


def _pinout_differences(original: dict[str, list[str]], candidate: dict[str, list[str]]) -> str:
    if len(original) != len(candidate):
        return f"The original has {len(original)} pins and the candidate has {len(candidate)}."
    diffs = []
    for pin in sorted(set(original) | set(candidate), key=int):
        o, c = original.get(pin), candidate.get(pin)
        if o != c:
            diffs.append(f"pin {pin} is {_functions(o)} on the original and {_functions(c)} on the candidate")
    text = "; ".join(diffs)
    return text[0].upper() + text[1:] + "."


def check_package_pinout(original: PartSpec, candidate: PartSpec) -> PackagePinoutResult:
    o_pkg, c_pkg = normalize_package(original.package.code), normalize_package(candidate.package.code)
    package_result = CheckResult.pass_ if o_pkg == c_pkg else CheckResult.fail

    o_pins, c_pins = pin_map(original), pin_map(candidate)
    if o_pins is None or c_pins is None or any("unknown" in f for pins in (o_pins, c_pins) for f in pins.values()):
        pinout_result = CheckResult.unknown
    elif o_pins == c_pins:
        pinout_result = CheckResult.pass_
    else:
        pinout_result = CheckResult.fail

    if package_result == CheckResult.pass_ and pinout_result == CheckResult.pass_:
        detail = f"Same {o_pkg} package and pin functions."
    else:
        package_text = (f"Same {o_pkg} package." if package_result == CheckResult.pass_
                        else f"Different package: {o_pkg} on the original, {c_pkg} on the candidate.")
        if pinout_result == CheckResult.pass_:
            pinout_text = "Same pin functions."
        elif pinout_result == CheckResult.fail:
            pinout_text = _pinout_differences(o_pins, c_pins)
        else:
            missing = [p.mpn for p, pins in ((original, o_pins), (candidate, c_pins))
                       if pins is None or any("unknown" in f for f in pins.values())]
            pinout_text = f"Pin functions are not verified for {' and '.join(missing)}."
        detail = f"{package_text} {pinout_text}"

    return PackagePinoutResult(
        package=PackageComparison(original=o_pkg, candidate=c_pkg, result=package_result),
        pinout=PinoutComparison(original=o_pins, candidate=c_pins, result=pinout_result),
        detail=detail,
    )
