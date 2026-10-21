# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""JSON-compatible, offline scientific API for independent consumers."""
from __future__ import annotations

from .contracts import normalize
from .power import fixed_power
from .provenance import provenance
from .references import analytic_reference
from .search import SearchBudgetExceeded
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
        from .contracts import finite_tree
        finite_tree(result)
        status = result.get("status", "complete")
    except SearchBudgetExceeded as exc:
        result, status = {"reason": str(exc)}, "budget_exhausted"
    except NotImplementedError as exc:
        result, status = {"reason": str(exc)}, "unsupported"
    envelope = {"schema_version": "1.0", "status": status, "operation": normalized["operation"], "normalized_request": normalized,
                "result": result, "assumptions": list(scenario.assumptions), "warnings": ["Conditional on the stated design and effect assumptions; this does not certify the study design."],
                "operation_policy_version": "1.2", "diagnostics": result.get("diagnostics", {}), "provenance": provenance(scenario.model, normalized)}
    if result.get("search_domain"):
        envelope["warnings"].append(result["search_domain"]["interpretation"])
    from .capabilities import FIXED_MODELS
    scalar = FIXED_MODELS.get(scenario.model)
    if normalized["operation"] == "detectable_effect" and scalar in request.get("scenario", {}).get("effect", {}):
        envelope["warnings"].append("The supplied effect is the parameter being solved; it was excluded from the canonical sensitivity inputs.")
    from .reproducibility import reproduction
    envelope["reproduction"] = reproduction(normalized)
    from .resources import method_attribution
    envelope["citations"] = [method_attribution(scenario.model)]
    if status == "complete":
        from .planning import _format_target_effect
        from .recruitment import recruitment_counts
        from .reporting import reporting
        rate = float(scenario.design.get("attrition_rate", 0))
        if not 0 <= rate < 1:
            raise ValueError("attrition_rate must lie in [0, 1)")
        if rate and normalized["operation"] != "plan":
            envelope["warnings"].append("Fixed sample counts are analysable; the declared attrition metadata is not applied to this fixed-sample calculation.")
        recruit_counts = recruitment_counts(result, rate) if normalized["operation"] == "plan" else None
        recruitment = recruit_counts["n_total"] if rate and recruit_counts else None
        envelope["recruitment_counts"] = recruit_counts
        envelope["recruitment_policy_version"] = "1.2"
        envelope["reporting"] = reporting(scenario, result, _format_target_effect(scenario), recruitment, scenario.design.get("family_alpha"))
    return envelope
