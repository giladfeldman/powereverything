# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Deterministic checks of explicitly confirmed scientific records."""
from __future__ import annotations

from ..api import analyze
from ..provenance import input_hash
from .evidence import _finite_number

REVIEW_POLICY_VERSION = "1.3"


def review(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Review record must be an object")
    mode=record.get("mode","compare")
    if mode not in {"compare","calculate"}:
        raise ValueError("Choose comparison or calculation without comparison")
    source = record.get("source_text", "")
    if not isinstance(source, str) or (mode=="compare" and not source.strip()) or len(source) > 100_000:
        raise ValueError("A source section of up to 100,000 characters is required")
    if record.get("confirmed") is not True:
        return {"status": "incomplete", "classification": "incomplete_reporting", "reason": "Confirm the source match and all calculation inputs before checking arithmetic."}
    request = record.get("confirmed_request")
    if not isinstance(request, dict):
        raise ValueError("A confirmed portable calculation request is required")
    if request.get("operation", "plan") not in {"plan", "power", "detectable_effect"}:
        raise ValueError("Review requires a plan, fixed-sample power, or detectable-effect request")
    # A stated value is required; no .95/.05 or sample defaults are inferred from prose.
    scenario = request.get("scenario", {})
    if not isinstance(scenario,dict):
        raise ValueError("scenario must be an object")
    rule = scenario.get("decision_rule", {})
    if not isinstance(rule,dict):
        raise ValueError("decision_rule must be an object")
    required = {"model": scenario.get("model"), "alpha": rule.get("alpha"), "alternative": rule.get("alternative")}
    if request.get("operation", "plan") != "power":
        required["target_power"] = scenario.get("target_power")
    design = scenario.get("design", {})
    if not isinstance(design,dict):
        raise ValueError("design must be an object")
    model = scenario.get("model")
    if model is not None and not isinstance(model,str):
        raise ValueError("model must be a named model")
    required["multiplicity_method"] = rule.get("multiplicity_method")
    model_keys = {
        "one_way_anova": ("groups",), "linear_regression": ("predictors",),
        "poisson_regression": ("baseline_rate", "exposure"),
        "incremental_regression": ("total_predictors", "tested_predictors"), "moderation": ("total_predictors",),
        "meta_analysis_fixed": ("studies",), "meta_analysis_random": ("studies", "tau"),
        "group_sequential_t": ("looks",), "ordinal_regression": ("categories",),
    }
    for key in model_keys.get(model, ()):
        required[key] = design.get(key)
    if request.get("operation", "plan") == "plan" and model in {"two_sample_t", "welch_t", "two_sample_proportion", "logrank_two_arm", "group_sequential_t", "noninferiority_t", "tost_equivalence", "rope_equivalence_t", "bayes_factor_t", "ordinal_regression"}:
        required["allocation_ratio"] = design.get("allocation_ratio")
    if model == "logistic_regression":
        required["predictor_type"] = design.get("predictor_type")
        if design.get("predictor_type") == "binary":
            required["allocation_ratio"] = design.get("allocation_ratio")
    if model == "bayes_factor_t":
        required["bf_method"] = design.get("bf_method")
        required["bf_threshold"] = design.get("bf_threshold")
        if str(design.get("bf_method", "")).lower() == "jzs":
            required["r_scale"] = design.get("r_scale")
    for key in {"rope_equivalence_t": ("prior_sd", "rope_threshold"), "mediation_indirect": ("residual_sd_m", "residual_sd_y"), "chi_square_gof": ("min_expected_count",), "chi_square_independence": ("min_expected_count",)}.get(model, ()):
        required[key] = design.get(key)
    if model == "ordinal_regression":
        required["baseline_category_probs"] = scenario.get("effect", {}).get("baseline_category_probs")
    missing = [name for name, value in required.items() if value is None or value == ""]
    if missing:
        return {"status": "incomplete", "classification": "incomplete_reporting", "reason": "Not explicitly supplied: " + ", ".join(missing)}
    result = analyze(request)
    if result["status"] != "complete":
        status = result["status"]
        return {"status": status, "classification": {"unreachable": "unreachable_in_declared_domain", "budget_exhausted": "calculation_budget_exhausted"}.get(status, "unsupported_method"), "calculation": result}
    if mode=="calculate":
        return {"schema_version":"1.0","review_policy_version":REVIEW_POLICY_VERSION,"status":"complete","classification":"calculation_only",
                "source_completeness":"user_confirmed_assumptions_without_numeric_comparison","design_match":"user_confirmed","source_sha256":input_hash(source) if source else None,
                "explanation":"Calculated under your explicitly confirmed assumptions. No reported numeric value was supplied or compared; this does not establish that uploaded code runs or that a manuscript is correct.",
                "calculation":result,"suggestions":["Compare the confirmed assumptions and sample units with the source, where supplied.","Supply the effect rationale and timing before using the reporting draft."],
                "execution":"The deterministic calculation ran; uploaded user code was not executed."}
    reported = record.get("reported_value")
    if not _finite_number(reported):
        raise ValueError("An explicit numeric reported value is required")
    op = result["operation"]
    field = "n_total" if op == "plan" else "power" if op == "power" else "detectable_effect"
    expected = result["result"][field]
    quantity = record.get("reported_quantity", field)
    if quantity == "per_group_n":
        if op != "plan" or result["result"].get("n1") != result["result"].get("n2") or "n1" not in result["result"]:
            raise ValueError("A per-group count requires an explicitly balanced two-group plan")
        expected, field = result["result"]["n1"], "per_group_n"
    elif quantity == "recruitment_n":
        if op != "plan" or "attrition_rate" not in design:
            raise ValueError("Recruitment comparison requires an explicit attrition rate")
        expected, field = result["reporting"]["distinctions"]["recruitment_n"], "recruitment_n"
    elif quantity == "effect_magnitude":
        if op != "detectable_effect":
            raise ValueError("Effect magnitude is a sensitivity quantity")
        expected, field = abs(expected), "effect_magnitude"
    elif quantity != field:
        raise ValueError("Reported quantity does not match the analysis operation")
    # Reporting precision must be declared by the reviewer. No blanket 2% N rule.
    digits = record.get("reported_decimal_places", 0 if field in {"n_total", "per_group_n", "recruitment_n"} else None)
    if isinstance(digits, bool) or not isinstance(digits, int) or not 0 <= digits <= 10:
        raise ValueError("Declare the reported decimal places (0–10)")
    tolerance = .5 * 10 ** (-digits) if field not in {"n_total", "per_group_n", "recruitment_n"} else 0
    consistent = abs(reported - expected) <= tolerance + 1e-12
    classification = "consistent_under_stated_assumptions" if consistent else "possible_discrepancy"
    text = (f"The reported {field} ({reported:g}) is " + ("consistent with" if consistent else "different from") + f" the matched calculation ({expected:.10g}). This checks the confirmed assumptions; it does not certify the study or establish an author error.")
    return {"schema_version": "1.0", "review_policy_version": REVIEW_POLICY_VERSION, "status": "complete", "classification": classification,
            "arithmetic": {"field": field, "reported": reported, "recomputed": expected, "difference": reported - expected, "tolerance": tolerance},
            "source_completeness": "user_confirmed_not_independently_certified", "design_match": "user_confirmed", "source_sha256": input_hash(source),
            "explanation": text, "calculation": result, "suggestions": ["Justify the effect using a smallest effect of interest or documented evidence.", "Inspect a plausible range of effect and design assumptions.", "Verify sample units, allocation, missingness, multiplicity and the final analysis model."],
            "execution": "The deterministic calculation ran; uploaded user code was not executed."}
