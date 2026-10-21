"""Deterministic, benefit-of-the-doubt checks for approved Meta-Power records.

This module deliberately does not retrieve articles or use AI. An extractor may propose
fields, but only a retained source excerpt and structured fields reach this checker.
"""

from __future__ import annotations

from typing import Any

from ..references import analytic_reference
from ..schema import DecisionRule, Scenario

FAMILY_TO_MODEL = {
    "independent_two_sample_t": "two_sample_t",
    "paired_t": "paired_t",
    "one_sample_proportion": "one_sample_proportion",
    "two_sample_proportion": "two_sample_proportion",
    "one_way_anova": "one_way_anova",
    "overall_linear_regression": "linear_regression",
    "incremental_regression": "incremental_regression",
    "pearson_correlation": "correlation",
}

REVIEW_STATUS_REASONS = {
    "analysis_family_unresolved": "The excerpt does not establish that the extracted power-test family matches the planned primary analysis.",
    "attrition_unresolved": "The excerpt does not establish whether the stated N is analysable or inflated for attrition.",
    "multiplicity_unresolved": "The excerpt does not establish the multiplicity rule for the planned primary tests.",
    "variance_model_unresolved": "The excerpt does not establish whether the pooled-variance or unequal-variance test was planned.",
    "incremental_regression_structure_unresolved": "The excerpt does not establish the tested block and full-model predictor count required for incremental-regression matching.",
}


def _missing(fields: dict[str, Any], names: list[str]) -> list[str]:
    return [name for name in names if fields.get(name) in (None, "", [])]


def _result(base: dict[str, Any], classification: str, verdict: str, **details: Any) -> dict[str, Any]:
    return {**base, "classification": classification, "verdict": verdict, **details}


def check(record: dict[str, Any]) -> dict[str, Any]:
    """Check a human-approved extraction without inventing missing assumptions.

    A mismatch is only a review flag. It never implies that the article is wrong: an
    unreported allocation, different analysis, rounding convention, or omitted
    information may explain the difference.
    """
    fields = record.get("fields", {})
    family = fields.get("analysis_family")
    model = FAMILY_TO_MODEL.get(family)
    base = {"article_id": record.get("article_id"), "family": family, "source_text": record.get("source_text"), "provenance": record.get("provenance")}
    review_status = fields.get("review_status")
    if review_status:
        reason = REVIEW_STATUS_REASONS.get(review_status, "A source-completeness issue requires a human review before matching this calculation.")
        return _result(
            base,
            "requires_review_before_matching",
            "needs_review",
            reason=reason,
            review_action="Retain the excerpt and resolve this match from the protocol, supplement, or author clarification; do not infer an assumption.",
        )
    if not model:
        return _result(base, "not_checkable_with_current_coverage", "needs_review", reason="The extracted analysis family is not yet covered by a verified PowerBench path.")

    required = ["alpha", "target_power", "planned_n", "effect", "alternative"]
    absent = _missing(fields, required)
    if absent:
        return _result(base, "insufficiently_reported", "incomplete", reason=f"Missing explicit fields: {', '.join(absent)}.", review_action="Retain the excerpt and seek the protocol, supplement, or author clarification; do not infer values.")
    try:
        scenario = _scenario_from_fields(model, fields)
        result = analytic_reference(scenario)
    except (ValueError, KeyError, TypeError) as error:
        return _result(base, "insufficiently_reported", "incomplete", reason=f"The stated fields cannot be mapped unambiguously: {error}", review_action="Human review of parameterization and analysis specification required.")
    expected = int(result["n_total"])
    reported = int(fields["planned_n"])
    tolerance = 0  # Required sample sizes are already integer-rounded by the engine.
    difference = reported - expected
    if abs(difference) <= tolerance:
        label, explanation = "verified_or_consistent", "Reported N is compatible with the matched calculation, with exact agreement after the method's integer allocation rounding."
    elif reported > expected:
        label, explanation = "consistent_under_plausible_assumptions", "Reported N exceeds the matched minimum; attrition, multiplicity, allocation, or a more conservative design may explain it."
    else:
        label, explanation = "potentially_inconsistent_requires_review", "Reported N is below the matched minimum under the explicit fields. This is a review flag, not an error finding."
    verdict = "checkable" if label != "potentially_inconsistent_requires_review" else "needs_review"
    return _result(base, label, verdict, reported_n=reported, matched_required_n=expected, difference=difference, tolerance=tolerance, method=result["method"], explanation=explanation, review_action="Compare the source text, protocol, allocation, tails, multiplicity rule, attrition treatment, and final analysis before drawing any conclusion.")


def _scenario_from_fields(model: str, fields: dict[str, Any]) -> Scenario:
    effect_value = fields["effect"]
    effect_map = {
        "two_sample_t": {"cohens_d": effect_value},
        "paired_t": {"cohens_dz": effect_value},
        "one_sample_proportion": {"p_null": fields.get("null_value"), "p_alternative": effect_value},
        "two_sample_proportion": {"p_group1": fields.get("group1_value"), "p_group2": effect_value},
        "one_way_anova": {"cohens_f": effect_value},
        "linear_regression": {"cohens_f2": effect_value},
        "incremental_regression": {"cohens_f2": effect_value},
        "correlation": {"rho": effect_value},
    }[model]
    design = dict(fields.get("design", {}))
    return Scenario(id="metapower-review", title="Meta-Power matched review", framework="frequentist", goal="required_sample_size", model=model, target_power=float(fields["target_power"]), effect=effect_map, design=design, decision_rule=DecisionRule(alpha=float(fields["alpha"]), alternative=fields["alternative"]), assumptions=[], status="draft")
