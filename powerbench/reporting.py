"""Deterministic manuscript drafts. Chronology and rationale are never invented."""
from __future__ import annotations

from .schema import Scenario

TEMPLATE_VERSION = "1.0"


def reporting(s: Scenario, result: dict, effect_text: str, recruitment: int | None = None, family_alpha: float | None = None) -> dict:
    unit = "complete pairs" if s.model == "paired_t" else "observations"
    if s.model.startswith("meta_analysis"):
        unit = f"observations across {s.design['studies']} studies"
    n = result.get("n_total", int(result.get("n1", 0)) + int(result.get("n2", 0)))
    allocation = f" ({result['n1']} in group 1 and {result['n2']} in group 2)" if "n1" in result and "n2" in result else ""
    alpha = s.decision_rule.alpha
    if s.framework == "bayesian":
        criterion = (f"BF10 threshold {s.design.get('bf_threshold')} under the stated prior" if s.model == "bayes_factor_t" else f"posterior ROPE probability threshold {s.design.get('rope_threshold')}")
        rule = f"The success criterion was {criterion}."
    else:
        rule = f"The decision rule used alpha = {alpha:g}, alternative = {s.decision_rule.alternative}"
        if family_alpha is not None and s.decision_rule.multiplicity_method != "none":
            rule += f", with family alpha = {family_alpha:g} and {s.decision_rule.multiplicity_method} planning for the primary family"
        rule += "."
    if s.goal == "sensitivity":
        body = (f"With a fixed analysable sample of {n} {unit}{allocation}, the detectable {result['effect_parameter']} was {result['detectable_effect']:.6g} at target power {float(s.target_power):.1%} under the stated design. "
                "This is a fixed-sample sensitivity analysis; it does not use an observed effect to establish evidence for a null hypothesis. ")
    elif s.goal == "achieved_power":
        body = (f"For a fixed analysable sample of {n} {unit}{allocation} and the hypothetical effect ({effect_text}), conditional power was {result['power']:.4f}. "
                "The effect is a planning assumption. This calculation does not establish evidence for or against a null hypothesis. ")
    else:
        criterion_word = "probability of meeting the stated success criterion" if s.framework == "bayesian" else "power"
        action = "establishing equivalence under the specified bounds" if s.model == "tost_equivalence" else "meeting the stated decision rule"
        body = (f"Under the stated planning assumptions for {s.title.lower()}, an analysable sample of {n} {unit}{allocation} was required for {action}. "
                f"The target effect ({effect_text}) is a planning assumption. Target {criterion_word} was {float(s.target_power):.1%}; the calculated value at the integer sample size was {result['power']:.4f}. ")
    if recruitment is not None:
        body += f"The recruitment target was {recruitment}, allowing for the stated attrition; the analysable sample was {n}. "
    body += rule
    from . import __version__, method_version
    body += f" Calculations used PowerBench {__version__}, method {s.model} version {method_version(s.model)}."
    return {"template_version": TEMPLATE_VERSION, "apa": body, "amj": body, "ready_to_insert": False,
            "author_tasks": ["Confirm when this analysis was conducted before describing it as a priori.", "Supply and cite the effect rationale or smallest effect of interest.", "Confirm the planned analysis, units, multiplicity and missing-data assumptions."],
            "distinctions": {"target_effect": effect_text + " (planning assumption, not an observed effect)", "family_alpha": family_alpha if family_alpha is not None else alpha,
                             "test_alpha": alpha, "analysable_n": n, "recruitment_n": recruitment if recruitment is not None else n, "framework": s.framework}}
