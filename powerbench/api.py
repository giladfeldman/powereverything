# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""JSON-compatible, offline scientific API for independent consumers."""
from __future__ import annotations

from .contracts import normalize
from .power import fixed_power
from .provenance import provenance
from .references import analytic_reference
from .sensitivity import detectable_effect


def analyze(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("Request must be an object")
    if request.get("operation") == "compare":
        from .comparison import compare_fields
        return compare_fields(request)
    if request.get("operation") == "convert_effect":
        from .conversions import convert_effect
        return convert_effect(request)
    if request.get("operation") == "simulate":
        from .simulation_lab import run
        return run(request.get("payload", {}))
    normalized, scenario = normalize(request)
    try:
        if normalized["operation"] == "plan":
            result = analytic_reference(scenario)
        elif normalized["operation"] == "power":
            result = fixed_power(scenario, normalized["sample"])
        else:
            result = detectable_effect(scenario, normalized["sample"], normalized.get("domain"))
        status = result.get("status", "complete")
    except NotImplementedError as exc:
        result, status = {"reason": str(exc)}, "unsupported"
    envelope = {"schema_version": "1.0", "status": status, "operation": normalized["operation"], "normalized_request": normalized,
                "result": result, "assumptions": list(scenario.assumptions), "warnings": ["Conditional on the stated design and effect assumptions; this does not certify the study design."],
                "diagnostics": result.get("diagnostics", {}), "provenance": provenance(scenario.model, normalized)}
    from .reproducibility import reproduction
    envelope["reproduction"] = reproduction(normalized)
    from .resources import method_attribution
    envelope["citations"] = [method_attribution(scenario.model)]
    if status == "complete":
        from .planning import _format_target_effect
        from .reporting import reporting
        envelope["reporting"] = reporting(scenario, result, _format_target_effect(scenario))
    return envelope
