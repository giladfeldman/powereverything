"""Deterministic manuscript drafts. Chronology and rationale are never invented."""
from __future__ import annotations

import json
from decimal import Decimal

from .schema import Scenario

TEMPLATE_VERSION = "1.7"


def defaulted_parameters(s: Scenario) -> dict:
    """Catalogued numerical-method defaults absent from the supplied scenario.

    This ledger discloses consumed design/effect defaults, not arbitrary prose
    assumptions. Fixed sample allocation comes from explicit arm counts.
    """
    from .schema import DESIGN_FIELDS
    design = {}
    if s.goal == "required_sample_size":
        design["attrition_rate"] = 0
        if "allocation_ratio" in DESIGN_FIELDS[s.model]:
            design["allocation_ratio"] = 1.0
    specific = {
        "logistic_regression": {"predictor_type": "binary"},
        "poisson_regression": {"exposure": 1.0},
        "chi_square_gof": {"min_expected_count": 5},
        "chi_square_independence": {"min_expected_count": 5},
        "mediation_indirect": {"residual_sd_m": 1.0, "residual_sd_y": 1.0},
        "meta_analysis_random": {"tau": .2},
        "bayes_factor_t": {"bf_method": "jzs"},
        "rope_equivalence_t": {"prior_sd": 10.0, "rope_threshold": .95},
        "correlation": {"distribution": "bivariate_normal"},
    }
    design.update(specific.get(s.model, {}))
    if s.model == "logistic_regression" and s.design.get("predictor_type", "binary") == "continuous":
        design.pop("allocation_ratio", None)
    if s.model == "bayes_factor_t" and str(s.design.get("bf_method", "jzs")).lower() == "jzs":
        design["r_scale"] = .7071
    if s.model == "logrank_two_arm" and "control_hazard" in s.design and "followup_years" in s.design:
        design.update(accrual_years=0., dropout_hazard=0.)
    defaults = {"design." + key: value for key, value in design.items() if key not in s.design}
    if s.model in {"tost_equivalence", "noninferiority_t", "rope_equivalence_t"} and "true_difference" not in s.effect:
        defaults["effect.true_difference"] = 0.
    if s.model == "ordinal_regression" and "baseline_category_probs" not in s.effect:
        from .specialist_extras import equally_spaced_latent_category_probs
        defaults["effect.baseline_category_probs"] = equally_spaced_latent_category_probs(int(s.design["categories"]))
    # Wizard-parsed requests carry their substitutions as explicit values, so the
    # catalogue above cannot see them; the parser records each one as an assumption.
    from .planning import WIZARD_DEFAULT_PREFIX
    for item in s.assumptions:
        if isinstance(item, str) and item.startswith(WIZARD_DEFAULT_PREFIX):
            key, _, value = item[len(WIZARD_DEFAULT_PREFIX):].partition(" = ")
            defaults[key] = json.loads(value)
    return defaults


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
        criterion = ((f"BIC-style approximate BF10 threshold {s.design.get('bf_threshold')}" if str(s.design.get('bf_method','jzs')).lower()=='bic' else f"BF10 threshold {s.design.get('bf_threshold')} under a zero-centered Cauchy prior scale {s.design.get('r_scale', .7071):g}") if s.model == "bayes_factor_t" else f"posterior ROPE probability threshold {s.design.get('rope_threshold', .95)}")
        rule = f"The success criterion was {criterion}."
    else:
        test = {"noninferiority_t": "a one-sided non-inferiority test", "tost_equivalence": "two one-sided equivalence tests", "mediation_indirect": "joint significance of two-sided path tests"}.get(s.model)
        if s.model in {"one_way_anova", "factorial_anova", "ancova", "planned_contrast", "linear_regression", "incremental_regression", "moderation"}:
            test = "an upper-tail omnibus F test"
        rule = f"The decision rule used alpha = {alpha:g}, " + (test if test else f"alternative = {s.decision_rule.alternative}")
        if family_alpha is not None and s.decision_rule.multiplicity_method != "none":
            rule += f", with family alpha = {family_alpha:g} and {s.decision_rule.multiplicity_method} planning for the primary family"
        rule += "."
    if s.model == "rope_equivalence_t":
        rule += f" The zero-centered normal prior SD was {s.design.get('prior_sd', 10.):g} in raw mean-difference units."
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
    defaults = defaulted_parameters(s)
    if defaults:
        body += "Defaulted assumptions: " + "; ".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in sorted(defaults.items())) + ". "
    if s.model == "poisson_regression":
        body += "This approximation assumes a balanced binary predictor with equal exposure in both arms. "
    if s.design:
        body += "Design parameters: " + "; ".join(f"{key.replace('_', ' ')} = {json.dumps(value, ensure_ascii=False)}" for key, value in sorted(s.design.items())) + ". "
    if s.model == "logrank_two_arm" and result.get("p_event_source")=="derived_from_accrual_followup_dropout":
        body += f"The hazard-derived event probability at the realized integer allocation was {result['p_event']:.9g}; the aggregate probability at the requested allocation was {result['requested_allocation_p_event']:.9g}. "
    if "n1" in result and "n2" in result and s.design.get("allocation_ratio") is not None:
        realized=result["n2"]/result["n1"]
        if abs(realized-float(s.design["allocation_ratio"]))>1e-12:
            body += f"The requested group-2/group-1 allocation ratio was {float(s.design['allocation_ratio']):.9g}; the realized integer ratio was {realized:.9g}. The reported arm counts define this calculation. "
    if s.model == "logrank_two_arm":
        body += "Power uses the Schoenfeld normal approximation under the stated event model; small-event operating characteristics require separate assessment. "
    if s.model == "welch_t":
        body += "Power uses the Welch-Satterthwaite noncentral-t planning approximation. "
    if s.model == "meta_analysis_random":
        body += (f"Hartung-Knapp inference used df = {int(s.design['studies']) - 1}. " if result.get("hartung_knapp") else "The two-study boundary uses a normal approximation rather than Hartung-Knapp inference; small-study calibration is not established by this calculation. ")
    if result.get("search_domain"):
        body += "Search constraints: " + json.dumps(result["search_domain"],ensure_ascii=False,sort_keys=True) + ". "
    body += rule
    from . import __version__, method_version
    body += f" Calculations used PowerBench {__version__}, method {s.model} version {method_version(s.model)}."
    if recruitment is not None:
        body += "Recruitment inflation uses expected retention and ceilings within each declared arm/cell; it does not guarantee realized retention. "
    return {"defaults_applied": defaults, "template_version": TEMPLATE_VERSION, "apa": body, "amj": body, "ready_to_insert": False,
            "author_tasks": ["Confirm when this analysis was conducted before describing it as a priori.", "Supply and cite the effect rationale or smallest effect of interest.", "Confirm the planned analysis, units, multiplicity and missing-data assumptions."],
            "distinctions": {"target_effect": (f"{result['effect_parameter']} = {result['detectable_effect']:.9g} (solved detectable effect)" if s.goal == "sensitivity" else effect_text + " (planning assumption, not an observed effect)"), "family_alpha": family_alpha if family_alpha is not None else alpha,
                             "test_alpha": alpha, "analysable_n": n, "recruitment_n": recruitment if recruitment is not None else n, "framework": s.framework}}
