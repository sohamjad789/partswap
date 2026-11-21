"""Resolve one BOM line's circuit requirements against the design context (PLAN.md section 4.4)."""

from app.schemas import BomLine, DesignContext, Requirements


def build_requirements(line: BomLine, context: DesignContext) -> Requirements:
    fields = {name: getattr(line, name) for name in Requirements.model_fields if name.startswith("req_")}
    if fields["req_temp_min_c"] is None:
        fields["req_temp_min_c"] = context.operating_temp_min_c
    if fields["req_temp_max_c"] is None:
        fields["req_temp_max_c"] = context.operating_temp_max_c
    return Requirements(input_voltage_v=context.input_voltage_v, **fields)
