"""`evaluate_pair`: the one comparison function (PLAN.md section 4.6). Thresholds come from `data/categories.json`."""

from typing import Any, Optional, Union

from app.catalog import load_json
from app.headline import headline_match
from app.package import check_package_pinout
from app.schemas import Check, CheckResult, CheckValue, Comparison, PartSpec, Requirements, Verdict
from app.units import format_quantity
from app.verdict import verdict_from_checks

PASS, FAIL, CAVEAT, UNKNOWN, SKIP = (CheckResult.pass_, CheckResult.fail, CheckResult.caveat,
                                     CheckResult.unknown, CheckResult.skip)
EPS = 1e-9

Value = Union[float, str, None]


def _label(required_from: str) -> str:
    if required_from in ("req_temp_min_c", "req_temp_max_c"):
        return "operating range"
    if required_from == "input_voltage_v":
        return "design context"
    return "line requirement"


def _ge(a: float, b: float) -> bool:
    return a >= b - EPS * max(1.0, abs(b))


def _le(a: float, b: float) -> bool:
    return a <= b + EPS * max(1.0, abs(b))


class _Ctx:
    """Values one rule needs, plus display helpers."""

    def __init__(self, rule: dict[str, Any], original: PartSpec, candidate: PartSpec, requirements: Requirements):
        self.rule = rule
        self.key = rule["key"]
        self.requirements = requirements
        self.original_part = original
        self.o_cv, self.o = self._side(original)
        self.c_cv, self.c = self._side(candidate)

    def _side(self, part: PartSpec) -> tuple[Optional[CheckValue], Value]:
        if self.rule["where"] == "root":
            value = getattr(part, self.key)
            if value is None:
                return None, None
            return CheckValue(value=value, raw=str(value)), value
        field = part.specs.get(self.key)
        if field is None:
            return None, None
        return CheckValue(value=field.value, raw=field.raw, condition=field.condition, page=field.page), field.value

    def req(self, name: Optional[str]) -> Optional[float]:
        return getattr(self.requirements, name) if name else None

    def target(self) -> tuple[Value, str]:
        required_from = self.rule.get("required_from")
        value = self.req(required_from)
        if value is not None:
            return value, _label(required_from)
        return self.o, "original"

    def fmt(self, value: Value) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return format_quantity(value, self.key)
        return str(value)

    def shown(self, cv: Optional[CheckValue], value: Value) -> str:
        return cv.raw if cv is not None and cv.raw else self.fmt(value)

    @property
    def cs(self) -> str:
        return self.shown(self.c_cv, self.c)

    @property
    def os(self) -> str:
        return self.shown(self.o_cv, self.o)


Outcome = tuple[CheckResult, Optional[str], str]  # result, requirement text, reason


def _missing(x: _Ctx, need_original: bool = True) -> Optional[Outcome]:
    if x.c is None:
        return UNKNOWN, None, "candidate value is not given"
    if need_original and x.o is None:
        return UNKNOWN, None, "original value is not given, so there is nothing to compare against"
    return None


def _bound(x: _Ctx, at_least: bool) -> Outcome:
    target, label = x.target()
    if x.c is None:
        return UNKNOWN, None, "candidate value is not given"
    if target is None:
        return UNKNOWN, None, "original value is not given, so there is nothing to compare against"
    op = ">=" if at_least else "<="
    requirement = f"{op} {x.fmt(target)} ({label})"
    whose = "the original" if label == "original" else "the required"
    if (_ge if at_least else _le)(x.c, target):
        return PASS, requirement, f"candidate {x.cs} meets {whose} {x.fmt(target)}"
    return FAIL, requirement, f"candidate {x.cs} is {'below' if at_least else 'above'} {whose} {x.fmt(target)}"


def _relative_match(x: _Ctx) -> Outcome:
    only = x.rule.get("only_when_output_type")
    if only and x.original_part.output_type != only:
        return SKIP, None, f"original output is {x.original_part.output_type}, not {only}"
    target, label = x.target()
    if x.c is None:
        return UNKNOWN, None, "candidate value is not given"
    if target is None or target == 0:
        return UNKNOWN, None, "original value is not given, so there is nothing to compare against"
    tol = x.rule["tolerance"]
    requirement = f"{x.fmt(target)} ± {tol * 100:g} % ({label})"
    if abs(x.c - target) / abs(target) <= tol + EPS:
        return PASS, requirement, f"candidate {x.cs} matches {x.fmt(target)}"
    return FAIL, requirement, f"candidate {x.cs} differs from {x.fmt(target)} by more than {tol * 100:g} %"


def _enum_equal(x: _Ctx) -> Outcome:
    if (missing := _missing(x)):
        return missing
    requirement = f"equal to original ({x.o})"
    if x.c == x.o:
        return PASS, requirement, f"both {x.o}"
    return FAIL, requirement, f"candidate is {x.c}, original is {x.o}"


def _not_worse_ratio(x: _Ctx) -> Outcome:
    if (missing := _missing(x)):
        return missing
    ratio = x.rule["ratio"]
    requirement = f"<= {x.fmt(x.o * ratio)} ({ratio:g} x original)"
    if _le(x.c, x.o * ratio):
        return PASS, requirement, f"candidate {x.cs} is within {ratio:g}x the original {x.os}"
    return CAVEAT, requirement, f"candidate {x.cs} is more than {ratio:g}x the original {x.os}"


def _within_ratio(x: _Ctx) -> Outcome:
    if (missing := _missing(x)):
        return missing
    ratio = x.rule["ratio"]
    requirement = f"within {ratio:g}x of the original {x.os}"
    low, high = sorted((x.c, x.o))
    if low <= 0:
        return UNKNOWN, requirement, "a non-positive value cannot be compared as a ratio"
    if _le(high / low, ratio):
        return PASS, requirement, f"candidate {x.cs} is within {ratio:g}x of the original {x.os}"
    return CAVEAT, requirement, f"candidate {x.cs} differs from the original {x.os} by more than {ratio:g}x"


def _worse_by_abs(x: _Ctx) -> Outcome:
    if (missing := _missing(x)):
        return missing
    margin = x.rule["caveat_abs"]
    requirement = f"<= {x.fmt(x.o + margin)} (original + {x.fmt(margin)})"
    if _le(x.c, x.o + margin):
        return PASS, requirement, f"candidate {x.cs} is within {x.fmt(margin)} of the original {x.os}"
    return CAVEAT, requirement, f"candidate {x.cs} is more than {x.fmt(margin)} above the original {x.os}"


def _dropout_fits(x: _Ctx) -> Outcome:
    if x.c is None:
        return UNKNOWN, None, "candidate value is not given"
    vin, vout = x.req("req_headroom_vin_v"), x.req("req_vout_v")
    margin = x.rule["caveat_abs"]
    parts = []
    headroom = None
    if vin is not None and vout is not None:
        headroom = vin - vout
        parts.append(f"<= {x.fmt(headroom)} headroom")
        if not _le(x.c, headroom):
            return FAIL, "; ".join(parts), (f"candidate {x.cs} exceeds the {x.fmt(headroom)} of headroom "
                                            f"({x.fmt(vin)} in, {x.fmt(vout)} out)")
    if x.o is None:
        return UNKNOWN, "; ".join(parts) or None, "original value is not given, so there is nothing to compare against"
    parts.append(f"caveat above {x.fmt(x.o + margin)} (original + {x.fmt(margin)})")
    requirement = "; ".join(parts)
    fits = f"fits the {x.fmt(headroom)} headroom" if headroom is not None else "has no headroom requirement to check"
    if _le(x.c, x.o + margin):
        return PASS, requirement, f"candidate {x.cs} {fits} and is within {x.fmt(margin)} of the original {x.os}"
    return CAVEAT, requirement, f"candidate {x.cs} {fits} but is more than {x.fmt(margin)} above the original {x.os}"


def _rds_on(x: _Ctx) -> Outcome:
    if (missing := _missing(x)):
        return missing
    if x.o <= 0:
        return UNKNOWN, None, "original value is not positive"
    cr, fr = x.rule["caveat_ratio"], x.rule["fail_ratio"]
    requirement = f"<= {x.fmt(x.o * cr)} ({cr:g} x original); fail above {x.fmt(x.o * fr)} ({fr:g} x original)"
    r = x.c / x.o
    if _le(r, cr):
        return PASS, requirement, f"candidate {x.cs} is within {cr:g}x the original {x.os}"
    if _le(r, fr):
        return CAVEAT, requirement, f"candidate {x.cs} is {r:.1f}x the original {x.os}"
    return FAIL, requirement, f"candidate {x.cs} is {r:.1f}x the original {x.os}, above the {fr:g}x limit"


def _vgs_th_drive(x: _Ctx) -> Outcome:
    drive = x.req(x.rule.get("required_from"))
    if drive is None:
        return SKIP, None, "no gate drive voltage is given for this line"
    requirement = f"<= {x.fmt(drive)} (gate drive)"
    if x.c is None:
        return UNKNOWN, requirement, "candidate value is not given"
    if _le(x.c, drive):
        return PASS, requirement, f"candidate threshold {x.cs} is at or below the {x.fmt(drive)} gate drive"
    return FAIL, requirement, f"candidate threshold {x.cs} is above the {x.fmt(drive)} gate drive"


def _esd_c(x: _Ctx) -> Outcome:
    if x.c is None:
        return UNKNOWN, None, "candidate value is not given"
    limit = x.req(x.rule.get("required_from"))
    ratio = x.rule.get("ratio", 2.0)
    parts = [f"<= {x.fmt(limit)} (line requirement)"] if limit is not None else []
    if limit is not None and not _le(x.c, limit):
        return FAIL, "; ".join(parts), f"candidate {x.cs} is above the {x.fmt(limit)} limit for this line"
    if x.o is None:
        return UNKNOWN, "; ".join(parts) or None, "original value is not given, so there is nothing to compare against"
    parts.append(f"caveat above {x.fmt(x.o * ratio)} ({ratio:g} x original)")
    if _le(x.c, x.o * ratio):
        return PASS, "; ".join(parts), f"candidate {x.cs} is within {ratio:g}x the original {x.os}"
    return CAVEAT, "; ".join(parts), f"candidate {x.cs} is more than {ratio:g}x the original {x.os}"


RULES = {
    "candidate_gte": lambda x: _bound(x, at_least=True),
    "candidate_lte": lambda x: _bound(x, at_least=False),
    "relative_match": _relative_match,
    "enum_equal": _enum_equal,
    "not_worse_ratio": _not_worse_ratio,
    "within_ratio": _within_ratio,
    "worse_by_abs": _worse_by_abs,
    "dropout_fits": _dropout_fits,
    "rds_on": _rds_on,
    "vgs_th_drive": _vgs_th_drive,
    "esd_c": _esd_c,
}


def _run_rule(rule: dict[str, Any], original: PartSpec, candidate: PartSpec, requirements: Requirements) -> Check:
    x = _Ctx(rule, original, candidate, requirements)
    result, requirement, reason = RULES[rule["rule"]](x)
    return Check(spec=x.key, result=result, on_fail=rule.get("on_fail"), on_unknown=rule.get("on_unknown"),
                 requirement=requirement, original=x.o_cv, candidate=x.c_cv, reason=reason)


def _pinout_value(part: PartSpec) -> Optional[CheckValue]:
    if not part.pinout:
        return None
    pins = sorted(part.pinout, key=lambda p: p.pin)
    return CheckValue(
        value="; ".join(f"{p.pin}: {' + '.join(sorted(p.functions))}" for p in pins),
        raw=", ".join(f"{p.pin} {p.name}" for p in pins),
        page=part.pinout_page,
    )


def _package_checks(original: PartSpec, candidate: PartSpec) -> list[Check]:
    pp = check_package_pinout(original, candidate)
    pkg = pp.package
    package_reason = (f"Same {pkg.original} package." if pkg.result == PASS
                      else f"Different package: {pkg.original} on the original, {pkg.candidate} on the candidate.")
    common = {"on_fail": Verdict.needs_redesign, "on_unknown": Verdict.no_safe_match}
    return [
        Check(spec="package", result=pkg.result, requirement="same package as original", reason=package_reason,
              original=CheckValue(value=pkg.original, raw=original.package.code, page=original.package.page),
              candidate=CheckValue(value=pkg.candidate, raw=candidate.package.code, page=candidate.package.page),
              **common),
        Check(spec="pinout", result=pp.pinout.result, requirement="same pin functions as original",
              reason="Same pin functions." if pp.pinout.result == PASS else pp.detail,
              original=_pinout_value(original), candidate=_pinout_value(candidate), **common),
    ]


def evaluate_pair(original: PartSpec, candidate: PartSpec, requirements: Requirements) -> Comparison:
    if original.category != candidate.category:
        o, c = original.category.value, candidate.category.value
        checks = [Check(spec="category", result=FAIL, on_fail=Verdict.no_safe_match, on_unknown=Verdict.no_safe_match,
                        requirement=f"same category as original ({o})", reason=f"candidate is a {c} part, not a {o} part",
                        original=CheckValue(value=o, raw=o), candidate=CheckValue(value=c, raw=c))]
    else:
        policy = load_json("categories.json")[original.category.value]["checks"]
        checks = [_run_rule(rule, original, candidate, requirements) for rule in policy]
    checks += _package_checks(original, candidate)
    return Comparison(
        original_mpn=original.mpn,
        candidate_mpn=candidate.mpn,
        category=original.category,
        checks=checks,
        suggested_verdict=verdict_from_checks(checks),
        headline_match=headline_match(original, candidate),
    )
