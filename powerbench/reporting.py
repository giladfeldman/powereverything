"""Deterministic manuscript drafts. Chronology and rationale are never invented."""
from __future__ import annotations

import json
from decimal import Decimal

from .schema import Scenario

TEMPLATE_VERSION = "1.2"


def reporting(s: Scenario, result: dict, effect_text: str, recruitment: int | None = None, family_alpha: float | None = None) -> dict:
    effect_text = "; ".join(f"{key.replace('_', ' ')} = {json.dumps(value, ensure_ascii=False)}" for key, value in s.effect.items() if key != "parameterization")
    target_percent = f"{Decimal(str(s.target_power)) * 100:f}%" if s.target_power is not None else "not specified"
    unit = "complete pairs" if s.model == "paired_t" else "observations"
    if s.model.startswith("meta_analysis"):
        unit = f"participants across {s.design['studies']} studies"
    n = result.get("n_total", int(result.get("n1", 0)) + int(result.get("n2", 0)))
    allocation = f" ({result['n1']} in group 1 and {result['n2']} in group 2)" if "n1" in result and "n2" in result else ""
    alpha = s.decision_rule.alpha
    if s.model == "logrank_two_arm":
        unit = "participants (event-driven log-rank design)"
    if s.framework == "bayesian":
        criterion = (f"BF10 threshold {s.design.get('bf_threshold')} under the stated prior" if s.model == "bayes_factor_t" else f"posterior ROPE probability threshold {s.design.get('rope_threshold')}")
        rule = f"The success criterion was {criterion}."
    else:
        test = {"noninferiority_t": "a one-sided non-inferiority test", "tost_equivalence": "two one-sided equivalence tests", "mediation_indirect": "joint significance of two-sided path tests"}.get(s.model)
        if s.model in {"one_way_anova", "factorial_anova", "ancova", "planned_contrast", "linear_regression", "incremental_regression", "moderation"}:
            test = "an upper-tail omnibus F test"
        rule = f"The decision rule used alpha = {alpha:g}, " + (test if test else f"alternative = {s.decision_rule.alternative}")
        if family_alpha is not None and s.decision_rule.multiplicity_method != "none":
            rule += f", with family alpha = {family_alpha:g} and {s.decision_rule.multiplicity_method} planning for the primary family"
        rule += "."
    if s.goal == "sensitivity":
        body = (f"With a fixed analysable sample of {n} {unit}{allocation}, the detectable {result['effect_parameter']} was approximately {result['detectable_effect']:.9g} at target power {target_percent} under the stated design. "
                "This is a fixed-sample sensitivity analysis; it does not use an observed effect to establish evidence for a null hypothesis. ")
    elif s.goal == "achieved_power":
        body = (f"For a fixed analysable sample of {n} {unit}{allocation} and the hypothetical effect ({effect_text}), conditional power was {result['power']:.4f}. "
                "The effect is a planning assumption. This calculation does not establish evidence for or against a null hypothesis. ")
    else:
        criterion_word = "probability of meeting the stated success criterion" if s.framework == "bayesian" else "power"
        action = "establishing equivalence under the specified bounds" if s.model == "tost_equivalence" else "meeting the stated decision rule"
        body = (f"Under the stated planning assumptions for {s.title.lower()}, an analysable sample of {n} {unit}{allocation} was required for {action}. "
                f"The target effect ({effect_text}) is a planning assumption. Target {criterion_word} was {target_percent}; the calculated value at the integer sample size was {result['power']:.4f}. ")
    if recruitment is not None:
        body += f"The recruitment target was {recruitment}, allowing for the stated attrition; the analysable sample was {n}. "
    if s.goal != "required_sample_size" and s.design.get("attrition_rate", 0):
        body += "The fixed counts are analysable; attrition metadata was not applied as an inflation or reduction. "
    if s.design:
        body += "Design parameters: " + "; ".join(f"{key.replace('_', ' ')} = {json.dumps(value, ensure_ascii=False)}" for key, value in sorted(s.design.items())) + ". "
    if s.model == "meta_analysis_random":
        body += (f"Hartung-Knapp inference used df = {int(s.design['studies']) - 1}. " if result.get("hartung_knapp") else "The two-study boundary uses a normal approximation rather than Hartung-Knapp inference; small-study calibration is not established by this calculation. ")
    body += rule
    from . import __version__, method_version
    body += f" Calculations used PowerBench {__version__}, method {s.model} version {method_version(s.model)}."
    if recruitment is not None:
        body += "Recruitment inflation uses expected retention and ceilings within each declared arm/cell; it does not guarantee realized retention. "
    return {"template_version": TEMPLATE_VERSION, "apa": body, "amj": body, "ready_to_insert": False,
            "author_tasks": ["Confirm when this analysis was conducted before describing it as a priori.", "Supply and cite the effect rationale or smallest effect of interest.", "Confirm the planned analysis, units, multiplicity and missing-data assumptions."],
            "distinctions": {"target_effect": effect_text + " (planning assumption, not an observed effect)", "family_alpha": family_alpha if family_alpha is not None else alpha,
                             "test_alpha": alpha, "analysable_n": n, "recruitment_n": recruitment if recruitment is not None else n, "framework": s.framework}}
