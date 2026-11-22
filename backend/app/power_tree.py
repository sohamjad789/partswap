"""Power tree assistant: arrange catalog bucks and LDOs to feed up to three rails. No model calls.

Each rail is fed by one fixed-output part, either from the input or from a higher rail.
LDO efficiency is vout / vin and its heat is (vin - vout) * iout. Buck efficiency comes only
from an `efficiency` spec field; without it the loss is unknown and the option ranks last.
"""

from itertools import product
from typing import Any, Optional

from pydantic import Field

from app.catalog import all_parts
from app.schemas import Category, Contract, PartSpec

INPUT = -1
VOUT_TOLERANCE = 0.01
MAX_OPTIONS = 3
NO_EFFICIENCY = "efficiency not in catalog"


class Rail(Contract):
    voltage_v: float = Field(gt=0)
    current_a: float = Field(gt=0)


class PowerTreeRequest(Contract):
    input_voltage_v: float = Field(gt=0)
    rails: list[Rail] = Field(min_length=1, max_length=3)


def _value(part: PartSpec, key: str) -> Optional[float]:
    field = part.specs.get(key)
    return None if field is None else field.value


def _fits(part: PartSpec, vsrc: float, vout: float) -> bool:
    if part.synthetic or part.category not in (Category.ldo, Category.buck) or part.output_type != "fixed":
        return False
    out, vin_min, vin_max = _value(part, "vout_v"), _value(part, "vin_min_v"), _value(part, "vin_max_v")
    if None in (out, vin_min, vin_max, _value(part, "iout_max_a")):
        return False
    if abs(out - vout) > vout * VOUT_TOLERANCE or not vin_min <= vsrc <= vin_max:
        return False
    if part.category is Category.ldo:
        dropout = _value(part, "dropout_v")
        return dropout is not None and vsrc - vout >= dropout
    return vsrc > vout


def _labels(rails: list[Rail]) -> list[str]:
    labels = [f"{r.voltage_v:g} V" for r in rails]
    return [f"{label} (rail {i + 1})" if labels.count(label) > 1 else label for i, label in enumerate(labels)]


def _stage(rail: str, rail_v: float, source: str, vsrc: Optional[float], part: Optional[PartSpec], load: float,
           iin: Optional[float], loss: Optional[float], efficiency: Optional[float], note: Optional[str]) -> dict[str, Any]:
    return {
        "rail": rail,
        "rail_voltage_v": rail_v,
        "source": source,
        "source_voltage_v": vsrc,
        "mpn": part.mpn if part else None,
        "manufacturer": part.manufacturer if part else None,
        "category": part.category.value if part else None,
        "load_a": load,
        "input_current_a": iin,
        "loss_w": loss,
        "efficiency": efficiency,
        "unit_price_usd": part.unit_price_usd if part else None,
        "note": note,
    }


def _evaluate(vin: float, rails: list[Rail], labels: list[str], assignment) -> Optional[dict[str, Any]]:
    """Rails are sorted high to low, so walking backwards settles every downstream load first."""
    load: list[Optional[float]] = [r.current_a for r in rails]
    stages: list[dict[str, Any]] = [{}] * len(rails)
    for i in reversed(range(len(rails))):
        vout = rails[i].voltage_v
        if assignment[i] is None:
            stages[i] = _stage(labels[i], vout, "", None, None, rails[i].current_a, None, None, None,
                               "no catalog buck or LDO can supply this rail")
            continue
        source, part = assignment[i]
        if load[i] is None or load[i] > _value(part, "iout_max_a"):
            return None
        vsrc = vin if source == INPUT else rails[source].voltage_v
        pout = vout * load[i]
        note = None
        if part.category is Category.ldo:
            efficiency, loss, iin = vout / vsrc, (vsrc - vout) * load[i], load[i]
        else:
            efficiency = _value(part, "efficiency")
            if efficiency is not None and 0 < efficiency <= 1:
                loss, iin = pout * (1 / efficiency - 1), pout / efficiency / vsrc
            else:
                efficiency, loss, iin, note = None, None, None, NO_EFFICIENCY
        if source != INPUT:
            load[source] = None if iin is None or load[source] is None else load[source] + iin
        source_label = f"{vin:g} V input" if source == INPUT else labels[source]
        stages[i] = _stage(labels[i], vout, source_label, vsrc, part, load[i], iin, loss, efficiency, note)

    served = [s for s in stages if s["mpn"]]
    losses = [s["loss_w"] for s in served]
    total_loss = None if None in losses else sum(losses)
    pout_total = sum(r.voltage_v * r.current_a for r, s in zip(rails, stages) if s["mpn"])
    prices = [s["unit_price_usd"] for s in served]
    return {
        "label": "; ".join(f"{s['rail']}: {s['category']} from {s['source']}" if s["mpn"] else f"{s['rail']}: no part"
                           for s in stages),
        "complete": len(served) == len(stages),
        "stages": stages,
        "part_count": len(served),
        "total_loss_w": total_loss,
        "efficiency": None if total_loss is None or not served else pout_total / (pout_total + total_loss),
        "cost_usd": None if not served or None in prices else sum(prices),
    }


def _rank(option: dict[str, Any]):
    loss = option["total_loss_w"]
    return (not option["complete"], loss is None, loss or 0.0, option["part_count"])


def propose(request: PowerTreeRequest) -> dict[str, Any]:
    vin = request.input_voltage_v
    rails = sorted(request.rails, key=lambda r: -r.voltage_v)
    labels = _labels(rails)
    parts = all_parts()
    choices: list[list] = []
    unserved = []
    for i, rail in enumerate(rails):
        sources = [INPUT] + [j for j in range(i) if rails[j].voltage_v > rail.voltage_v and choices[j][0] is not None]
        options = [(s, p) for s in sources for p in parts
                   if _fits(p, vin if s == INPUT else rails[s].voltage_v, rail.voltage_v)]
        if not options:
            unserved.append({"rail": labels[i], "reason": f"No catalog buck or LDO outputs {rail.voltage_v:g} V "
                                                          f"from the {vin:g} V input or a higher rail."})
        choices.append(options or [None])

    evaluated = [o for o in (_evaluate(vin, rails, labels, a) for a in product(*choices)) if o is not None]
    if all(not o["part_count"] for o in evaluated):
        evaluated = []
    evaluated.sort(key=_rank)
    return {"input_voltage_v": vin, "options": evaluated[:MAX_OPTIONS], "unserved": unserved}
