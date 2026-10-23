"""Portable study-planning orchestration. No website or database dependencies."""
from __future__ import annotations

from dataclasses import asdict, replace
from math import isfinite
from typing import Any

from .adapters.r_pwr import RPwrAdapter
from .references import analytic_reference, chi_square_gof_w
from .schema import DecisionRule, Scenario
from .simulation import simulate
from .specialist_extras import derive_logrank_event_probability

DEFAULT_TARGET_POWER = 0.95

# Model-specific wizard fields; unknown keys must never silently alter a request.
WIZARD_FIELDS = {
    'two_sample_t': ['allocation_ratio', 'attrition_rate', 'effect', 'equal_variance'],
    'welch_t': ['allocation_ratio', 'attrition_rate', 'effect', 'sd_group1', 'sd_group2'],
    'paired_t': ['attrition_rate', 'effect'],
    'one_sample_proportion': ['attrition_rate', 'effect', 'p_null'],
    'two_sample_proportion': ['allocation_ratio', 'attrition_rate', 'effect', 'p_group1'],
    'chi_square_gof': ['attrition_rate', 'p_alternative', 'p_null'],
    'one_way_anova': ['attrition_rate', 'effect', 'groups'],
    'linear_regression': ['attrition_rate', 'effect', 'predictors'],
    'incremental_regression': ['attrition_rate', 'effect', 'tested_predictors', 'total_predictors'],
    'correlation': ['attrition_rate', 'effect'],
    'chi_square_independence': ['attrition_rate', 'joint_probabilities'],
    'factorial_anova': ['attrition_rate', 'effect', 'levels_a', 'levels_b', 'tested_term'],
    'ancova': ['attrition_rate', 'covariate_r2', 'effect', 'groups'],
    'planned_contrast': ['attrition_rate', 'contrast_weights', 'effect'],
    'moderation': ['attrition_rate', 'effect', 'total_predictors'],
    'logistic_regression': ['allocation_ratio', 'attrition_rate', 'effect', 'p_baseline', 'predictor_type'],
    'poisson_regression': ['attrition_rate', 'baseline_rate', 'effect', 'exposure'],
    'tost_equivalence': ['allocation_ratio', 'attrition_rate', 'lower_bound', 'sd', 'true_difference', 'upper_bound'],
    'mediation_indirect': ['a_path', 'attrition_rate', 'b_path', 'direct_cprime', 'residual_sd_m', 'residual_sd_y'],
    'meta_analysis_fixed': ['attrition_rate', 'effect', 'studies'],
    'meta_analysis_random': ['attrition_rate', 'effect', 'studies', 'tau'],
    'noninferiority_t': ['allocation_ratio', 'attrition_rate', 'margin', 'sd', 'true_difference'],
    'ordinal_regression': ['allocation_ratio', 'attrition_rate', 'categories', 'effect'],
    'bayes_factor_t': ['allocation_ratio', 'attrition_rate', 'bf_method', 'bf_threshold', 'effect', 'r_scale'],
    'group_sequential_t': ['allocation_ratio', 'attrition_rate', 'effect', 'looks'],
    'logrank_two_arm': ['accrual_years', 'allocation_ratio', 'attrition_rate', 'control_hazard', 'dropout_hazard', 'effect', 'followup_years', 'hazard_ratio', 'p_event'],
    'rope_equivalence_t': ['allocation_ratio', 'attrition_rate', 'lower_bound', 'prior_sd', 'rope_threshold', 'sd', 'true_difference', 'upper_bound'],
}

# Values the wizard parser substitutes when a caller leaves the field blank. Every
# substitution is disclosed (assumption text and the reporting defaults ledger),
# because several of them change the headline sample size.
WIZARD_DEFAULTS = {
    "allocation_ratio": 1.0, "exposure": 1.0, "true_difference": 0.0, "direct_cprime": 0.0,
    "residual_sd_m": 1.0, "residual_sd_y": 1.0, "r_scale": 0.7071, "accrual_years": 0.0,
    "followup_years": 1.0, "dropout_hazard": 0.0, "control_hazard": 1.0, "prior_sd": 10.0,
    "rope_threshold": 0.95,
}
WIZARD_DEFAULT_PREFIX = "Planning default applied (field not supplied): "


def checked_default_disclosures(assumptions: Any, effect: dict, design: dict, target_power: Any) -> dict[str, Any]:
    """Parse the parser's default-disclosure lines; each must match the value it describes.

    Returns ``{"design.key": value, ...}``. A line naming a field that is absent or holds a
    different value raises ValueError, so a disclosure cannot be forged or go stale.
    """
    import json as _json
    found: dict[str, Any] = {}
    for item in assumptions or []:
        if not (isinstance(item, str) and item.startswith(WIZARD_DEFAULT_PREFIX)):
            continue
        key, _, raw = item[len(WIZARD_DEFAULT_PREFIX):].partition(" = ")
        value = _json.loads(raw)
        section, _, field = key.partition(".")
        if key == "target_power":
            actual, present = target_power, target_power is not None
        elif section in {"effect", "design"} and field:
            values = effect if section == "effect" else design
            actual, present = values.get(field), field in values
        else:
            raise ValueError(f"Default disclosure names an unknown field: {key}")
        if not present or isinstance(value, bool) or not isinstance(value, (int, float)) or actual != value:
            raise ValueError(f"Default disclosure for {key} does not match the scenario value")
        found[key] = value
    return found


def default_disclosure_lines(defaults: dict[str, Any]) -> list[str]:
    import json as _json
    return [f"{WIZARD_DEFAULT_PREFIX}{key} = {_json.dumps(value)}" for key, value in defaults.items()]

COMMON_WIZARD_FIELDS = {"model", "goal", "target_power", "alpha", "alternative", "attrition_rate", "multiplicity_method", "primary_tests", "n1", "n2", "n_total"}


def _number(payload: dict[str, Any], key: str) -> float:
    try:
        value=payload[key]
        if isinstance(value,bool):raise TypeError("A boolean is not a scientific numeric input")
        number=float(value)
        if not isfinite(number):raise ValueError("Scientific inputs must be finite")
        return number
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{key.replace('_', ' ').capitalize()} must be a number.") from error


def _probabilities(payload: dict[str, Any], key: str) -> list[float]:
    raw = payload.get(key)
    values = raw if isinstance(raw, list) else str(raw or "").split(",")
    try:
        numbers=[float(value) for value in values if not isinstance(value,bool)]
        if len(numbers)!=len(values) or not all(isfinite(value) for value in numbers):raise ValueError("Probabilities must be finite numeric inputs")
        return numbers
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key.replace('_', ' ').capitalize()} must be comma-separated probabilities.") from error


def scenario_from_fields(payload: dict[str, Any]) -> tuple[Scenario, float, float, int]:
    """Create an assumption-visible plan from the app's intentionally small v0.1 wizard."""
    if not isinstance(payload,dict):
        raise ValueError("Planner fields must be an object")  # noqa: TRY004 -- portable JSON validation contract
    model = payload.get("model")
    if not isinstance(model,str) or model not in WIZARD_FIELDS:
        raise ValueError("Unrecognized planner model")
    from .schema import EXACT_ALLOCATION_MODELS
    pair_fields={"allocation_numerator","allocation_denominator"} if model in EXACT_ALLOCATION_MODELS else set()
    unknown=set(payload)-COMMON_WIZARD_FIELDS-set(WIZARD_FIELDS[model])-pair_fields
    if unknown:
        raise ValueError("Unrecognized planner field(s): "+", ".join(sorted(unknown)))
    payload=dict(payload)
    allocation=payload.get("allocation_ratio")
    if isinstance(allocation,str) and ":" in allocation:
        from .schema import EXACT_ALLOCATION_MODELS
        if model not in EXACT_ALLOCATION_MODELS:
            raise ValueError("This method currently accepts a decimal allocation ratio only")
        parts=allocation.split(":")
        if len(parts)!=2 or any(not value.strip().isdigit() for value in parts):
            raise ValueError("Use an integer n2:n1 allocation pair, such as 5:3")
        from .allocation import declared_allocation_ratio
        payload["allocation_numerator"],payload["allocation_denominator"]=map(int,parts)
        payload.pop("allocation_ratio")
        payload["allocation_ratio"]=float(declared_allocation_ratio(payload))
    if "allocation_numerator" in payload or "allocation_denominator" in payload:
        from .allocation import declared_allocation_ratio
        pair={key:payload[key] for key in ("allocation_numerator","allocation_denominator") if key in payload}
        if "allocation_ratio" in payload:pair["allocation_ratio"]=_number(payload,"allocation_ratio")
        payload["allocation_ratio"]=float(declared_allocation_ratio(pair))
    if isinstance(payload.get("equal_variance"),str):
        value=payload["equal_variance"].lower()
        if value not in {"true","false"}:raise ValueError("equal_variance must be boolean")
        payload["equal_variance"]=value=="true"
    blank = {key for key in ("target_power", "attrition_rate") if key not in payload}
    payload = {**payload, **{key: value for key, value in (("target_power", DEFAULT_TARGET_POWER), ("attrition_rate", 0)) if key in blank}}
    target_power = _number(payload, "target_power")
    rate = _number(payload, "attrition_rate")
    if not 0 <= rate < 1:
        raise ValueError("attrition_rate must lie in [0, 1)")
    family_alpha = _number(payload, "alpha")
    multiplicity_method = str(payload.get("multiplicity_method", "none")).lower()
    if multiplicity_method not in {"none", "bonferroni", "hochberg"}:
        raise ValueError("multiplicity_method must be none, bonferroni, or hochberg.")
    from .power import count
    primary_tests = count(payload["primary_tests"], "primary_tests", 1) if "primary_tests" in payload else 1
    if multiplicity_method == "none" and primary_tests != 1:
        raise ValueError("Multiple primary tests require an explicit multiplicity planning adjustment")
    if primary_tests < 1:
        raise ValueError("Number of primary tests must be at least 1.")
    # Hochberg step-up planning for equal-weight primaries uses the most stringent step (alpha/m),
    # matching Bonferroni for the worst-case primary; power is therefore slightly conservative.
    alpha = family_alpha / primary_tests if multiplicity_method in {"bonferroni", "hochberg"} else family_alpha
    alternative = payload.get("alternative", "two.sided")
    framework = "frequentist"
    if model == "two_sample_t":
        effect = {"cohens_d": _number(payload, "effect"), "parameterization": "standardized_mean_difference"}
        design = {"allocation_ratio": _number(payload, "allocation_ratio"), "equal_variance": payload.get("equal_variance", True), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Independent two-sample t-test plan"
        assumptions = [
            "Independent observations and approximately normal outcomes.",
            "The displayed reference targets a pooled-variance Student t-test.",
            "If unequal variances are plausible, review the Welch path before using this N.",
        ]
    elif model == "welch_t":
        effect = {
            "mean_difference": _number(payload, "effect"),
            "sd_group1": _number(payload, "sd_group1"),
            "sd_group2": _number(payload, "sd_group2"),
            "parameterization": "raw_mean_difference_and_group_specific_sds",
        }
        design = {
            "allocation_ratio": _number(payload, "allocation_ratio"),
            "equal_variance": False,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Welch unequal-variance two-sample t-test plan"
        assumptions = [
            "Independent observations and approximately normal outcomes within each group.",
            "The planned analysis is Welch's unequal-variance t-test, using a raw mean difference and one SD for each group.",
            "The analytic result is a Welch-Satterthwaite noncentral-t planning approximation, not a pooled-variance t calculation.",
            "When requested, the separate simulation check generates group-specific variances and applies Welch's t-test directly.",
        ]
    elif model == "paired_t":
        effect = {"cohens_dz": _number(payload, "effect"), "parameterization": "standardized_mean_change"}
        design = {"attrition_rate": _number(payload, "attrition_rate")}
        title = "Paired-samples t-test plan"
        assumptions = [
            "The effect is dz: the mean change divided by the standard deviation of the within-person changes.",
            "Pairs are correctly matched and the change scores are approximately normal.",
            "This is not interchangeable with an independent-groups Cohen's d.",
        ]
    elif model == "one_sample_proportion":
        effect = {"p_null": _number(payload, "p_null"), "p_alternative": _number(payload, "effect"), "parameterization": "null_and_alternative_proportion"}
        design = {"attrition_rate": _number(payload, "attrition_rate")}
        title = "One-sample proportion plan"
        assumptions = [
            "Each observation is an independent Bernoulli outcome with the stated alternative proportion.",
            "The reference uses the exact binomial rejection region, rather than a normal approximation.",
            "The null proportion must be specified substantively, not chosen after observing the data.",
        ]
    elif model == "two_sample_proportion":
        effect = {"p_group1": _number(payload, "p_group1"), "p_group2": _number(payload, "effect"), "parameterization": "two_group_proportions"}
        design = {"allocation_ratio": _number(payload, "allocation_ratio"), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Two independent proportions plan"
        assumptions = [
            "The planned analysis is the pooled two-proportion z-test with independent observations.",
            "The analytic reference is a normal approximation under the stated alternative; sparse or boundary probabilities need an exact or simulation-first design-specific analysis.",
            "The target identifies a difference in proportions, not an odds ratio or regression coefficient.",
        ]
    elif model == "chi_square_gof":
        p_null, p_alternative = _probabilities(payload, "p_null"), _probabilities(payload, "p_alternative")
        effect = {
            "p_null": p_null,
            "p_alternative": p_alternative,
            "cohens_w": chi_square_gof_w(p_null, p_alternative),
            "parameterization": "null_and_alternative_multinomial_probabilities",
        }
        design = {"categories": len(p_null), "min_expected_count": 5, "attrition_rate": _number(payload, "attrition_rate")}
        title = "Chi-square goodness-of-fit plan"
        assumptions = [
            "The primary analysis is Pearson's multinomial chi-square goodness-of-fit test against the stated null probabilities.",
            "All null and alternative category probabilities are explicit and sum to one; categories are mutually exclusive and observations independent.",
            "The analytic result is a noncentral chi-square planning approximation and is available only when every expected null cell count is at least five.",
            "Sparse, collapsed, adaptive, or post-hoc categorical analyses need a design-specific simulation or exact procedure.",
        ]
    elif model == "one_way_anova":
        effect = {"cohens_f": _number(payload, "effect"), "parameterization": "cohens_f"}
        design = {"groups": count(_number(payload, "groups"), "groups", 1), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Balanced one-way ANOVA omnibus plan"
        assumptions = [
            "Groups are equally sized; the result is for the omnibus F test, not a particular pairwise contrast.",
            "Cohen's f describes the spread of all population group means relative to the within-group SD.",
            "If pairwise tests or multiplicity correction drive the question, plan those tests directly.",
        ]
    elif model == "linear_regression":
        effect = {"cohens_f2": _number(payload, "effect"), "parameterization": "cohens_f_squared"}
        design = {"predictors": count(_number(payload, "predictors"), "predictors", 1), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Linear regression overall-model plan"
        assumptions = [
            "The target is the overall R-squared test for the stated number of predictors, using Cohen's f-squared.",
            "The analytic reference is a fixed-design noncentral-F approximation; the optional separate simulation check uses normal predictors and errors.",
            "For one focal predictor, covariates, interactions, collinearity, or non-normal outcomes, use a design-specific simulation path.",
        ]
    elif model == "incremental_regression":
        effect = {"cohens_f2": _number(payload, "effect"), "parameterization": "incremental_cohens_f_squared"}
        design = {"total_predictors": count(_number(payload, "total_predictors"), "total_predictors", 1), "tested_predictors": count(_number(payload, "tested_predictors"), "tested_predictors", 1), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Incremental linear regression plan"
        assumptions = [
            "The target is a pre-specified block of predictors, expressed as incremental Cohen's f-squared.",
            "The reference uses a fixed-design noncentral F calculation; the optional separate simulation check uses independent normal predictors and errors.",
            "Correlated covariates, interactions, reliability, nonlinear terms, and non-normal outcomes must be modeled in a design-specific simulation.",
        ]
    elif model == "correlation":
        effect = {"rho": _number(payload, "effect"), "parameterization": "pearson_correlation"}
        design = {"distribution": "bivariate_normal", "attrition_rate": _number(payload, "attrition_rate")}
        title = "Pearson correlation plan"
        assumptions = [
            "The target is Pearson's correlation, not a rank or partial correlation.",
            "The analytic result uses a Fisher-z normal approximation.",
            "The optional separate simulation check assumes a bivariate normal population.",
        ]
    elif model == "chi_square_independence":
        rows = [[float(cell) for cell in str(row).split(":")] for row in str(payload.get("joint_probabilities", "")).split(";")]
        if len(rows) < 2 or any(len(row) < 2 for row in rows):
            raise ValueError("Provide joint probabilities as rows separated by ';' and cells by ':' (example: 0.4:0.1;0.2:0.3).")
        effect = {"joint_probabilities": rows, "parameterization": "joint_cell_probabilities"}
        design = {"rows": len(rows), "cols": len(rows[0]), "min_expected_count": 5, "attrition_rate": _number(payload, "attrition_rate")}
        title = "Chi-square independence plan"
        assumptions = [
            "The primary analysis is Pearson's chi-square test of independence on the stated contingency table.",
            "Joint cell probabilities under the alternative are fully specified and sum to one.",
            "The analytic result is a noncentral chi-square approximation and expects adequate cell counts.",
        ]
    elif model == "factorial_anova":
        effect = {"cohens_f": _number(payload, "effect"), "parameterization": "cohens_f_tested_term"}
        design = {
            "levels_a": count(_number(payload, "levels_a"), "levels_a", 1),
            "levels_b": count(_number(payload, "levels_b"), "levels_b", 1),
            "tested_term": payload.get("tested_term", "AB"),
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Balanced factorial ANOVA plan"
        assumptions = [
            "Cells are equally sized; the result targets one pre-specified term (A, B, or AB).",
            "Cohen's f is defined for that tested term relative to the within-cell SD.",
            "Omnibus multi-term error control needs an explicit multiplicity rule.",
        ]
    elif model == "ancova":
        effect = {"cohens_f": _number(payload, "effect"), "parameterization": "cohens_f_adjusted_treatment"}
        design = {
            "groups": count(_number(payload, "groups"), "groups", 1),
            "covariate_r2": _number(payload, "covariate_r2"),
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "ANCOVA adjusted-treatment plan"
        assumptions = [
            "One pre-treatment covariate reduces residual variance by the stated R-squared.",
            "Slopes are homogeneous across groups; the covariate is not affected by treatment.",
            "The analytic result is a noncentral-F ANCOVA approximation with one covariate.",
        ]
    elif model == "planned_contrast":
        weights = [float(value) for value in str(payload.get("contrast_weights", "")).split(",")]
        effect = {"cohens_f": _number(payload, "effect"), "parameterization": "cohens_f_contrast"}
        design = {"groups": len(weights), "contrast_weights": weights, "attrition_rate": _number(payload, "attrition_rate")}
        title = "Planned contrast plan"
        assumptions = [
            "Contrast weights are fixed before seeing the outcome data and sum to zero.",
            "Groups are balanced; the result powers this single contrast, not every pairwise test.",
        ]
    elif model == "moderation":
        effect = {"cohens_f2": _number(payload, "effect"), "parameterization": "incremental_interaction_f2"}
        design = {"total_predictors": count(_number(payload, "total_predictors"), "total_predictors", 1), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Moderation interaction plan"
        assumptions = [
            "The focal test is the interaction increment after lower-order terms.",
            "total_predictors counts focal predictor, moderator, interaction, and any covariates in the final model.",
            "Measurement error, non-linearity, and logistic outcomes need a design-specific simulation.",
        ]
    elif model == "logistic_regression":
        effect = {
            "odds_ratio": _number(payload, "effect"),
            "p_baseline": _number(payload, "p_baseline"),
            "parameterization": "odds_ratio_at_baseline_risk",
        }
        design = {"predictor_type": payload.get("predictor_type", "binary"), "attrition_rate": _number(payload, "attrition_rate")}
        if design["predictor_type"] == "binary":
            design["allocation_ratio"] = _number(payload, "allocation_ratio") if payload.get("allocation_ratio") not in (None, "") else 1.0
        elif payload.get("allocation_ratio") not in (None, ""):
            raise ValueError("allocation_ratio applies only to a binary predictor")
        title = "Logistic regression coefficient plan"
        assumptions = [
            "The target is a single logistic coefficient expressed as an odds ratio at the stated baseline risk.",
            "The analytic result uses a Hsieh-style normal approximation; rare events or many covariates need simulation.",
            "Binary predictors use the displayed group-2/group-1 allocation ratio; continuous predictors are assumed standard-normal.",
        ]
    elif model == "poisson_regression":
        effect = {"rate_ratio": _number(payload, "effect"), "parameterization": "rate_ratio"}
        design = {
            "baseline_rate": _number(payload, "baseline_rate"),
            "exposure": _number(payload, "exposure") if payload.get("exposure") not in (None, "") else 1.0,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Poisson rate-ratio plan"
        assumptions = [
            "The target is a single Poisson log-rate coefficient expressed as a rate ratio.",
            "Exposure is equal across observations; overdispersion is not modelled here.",
            "The analytic result is a normal approximation under a balanced binary predictor.",
        ]
    elif model == "tost_equivalence":
        effect = {
            "lower_bound": _number(payload, "lower_bound"),
            "upper_bound": _number(payload, "upper_bound"),
            "true_difference": _number(payload, "true_difference") if payload.get("true_difference") not in (None, "") else 0.0,
            "sd": _number(payload, "sd"),
            "parameterization": "raw_equivalence_bounds",
        }
        design = {"allocation_ratio": _number(payload, "allocation_ratio"), "attrition_rate": _number(payload, "attrition_rate")}
        title = "TOST mean-equivalence plan"
        assumptions = [
            "Equivalence is declared only when both one-sided tests reject at the stated alpha.",
            "Bounds are in the same raw units as the mean difference and SD.",
            "This is an equivalence framework result, not a superiority or non-inferiority claim.",
        ]
        framework = "equivalence"
    elif model == "mediation_indirect":
        effect = {
            "a_path": _number(payload, "a_path"),
            "b_path": _number(payload, "b_path"),
            "direct_cprime": _number(payload, "direct_cprime") if payload.get("direct_cprime") not in (None, "") else 0.0,
            "parameterization": "standardized_paths",
        }
        design = {
            "residual_sd_m": _number(payload, "residual_sd_m") if payload.get("residual_sd_m") not in (None, "") else 1.0,
            "residual_sd_y": _number(payload, "residual_sd_y") if payload.get("residual_sd_y") not in (None, "") else 1.0,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Simple mediation indirect-effect plan"
        assumptions = [
            "The decision rule is joint significance of the a and b paths.",
            "Paths are linear OLS coefficients; no unmeasured confounding is assumed.",
            "Bootstrap CI or SEM identification needs a design-specific simulation contract.",
        ]
    elif model == "meta_analysis_fixed":
        effect = {"cohens_d": _number(payload, "effect"), "parameterization": "average_smd"}
        design = {"studies": count(_number(payload, "studies"), "studies", 1), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Fixed-effect meta-analysis plan"
        assumptions = [
            "All studies share one common true standardized mean difference.",
            "Each study is a balanced two-group continuous design; N is total across studies.",
            "Random-effects heterogeneity requires a different contract.",
        ]
    elif model == "meta_analysis_random":
        effect = {"cohens_d": _number(payload, "effect"), "parameterization": "average_smd_with_heterogeneity"}
        design = {
            "studies": count(_number(payload, "studies"), "studies", 1),
            "tau": _number(payload, "tau"),
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Random-effects meta-analysis plan"
        assumptions = [
            "Study-specific true effects are drawn around an average SMD with between-study SD tau.",
            "Each study is a balanced two-group continuous design; N is total across studies.",
            "Inference uses a Hartung–Knapp / Sidik-style t critical with df = studies − 1 when studies > 2.",
            "The reference also reports a 95% prediction interval for a new study's true effect under the random-effects model.",
        ]
    elif model == "noninferiority_t":
        effect = {
            "margin": _number(payload, "margin"),
            "true_difference": _number(payload, "true_difference") if payload.get("true_difference") not in (None, "") else 0.0,
            "sd": _number(payload, "sd"),
            "parameterization": "raw_noninferiority_margin",
        }
        design = {"allocation_ratio": _number(payload, "allocation_ratio"), "attrition_rate": _number(payload, "attrition_rate")}
        title = "Non-inferiority mean-difference plan"
        assumptions = [
            "Non-inferiority is declared when a one-sided test rejects H0: difference <= -margin.",
            "Margin and SD are in the same raw units as the mean difference.",
            "This is not an equivalence (TOST) or superiority claim.",
        ]
    elif model == "ordinal_regression":
        effect = {"odds_ratio": _number(payload, "effect"), "parameterization": "proportional_odds_ratio"}
        design = {"categories": count(_number(payload, "categories"), "categories", 1), "attrition_rate": _number(payload, "attrition_rate")}
        design["allocation_ratio"] = _number(payload, "allocation_ratio") if payload.get("allocation_ratio") not in (None, "") else 1.0
        title = "Ordinal proportional-odds plan"
        assumptions = [
            "The outcome has ordered categories and the proportional-odds assumption holds.",
            "The analytic result uses a latent-normal/logistic approximation for a binary predictor.",
            "Sparse categories or non-proportional odds need a design-specific simulation.",
        ]
    elif model == "bayes_factor_t":
        effect = {"cohens_d": _number(payload, "effect"), "parameterization": "standardized_mean_difference"}
        design = {
            "allocation_ratio": _number(payload, "allocation_ratio"),
            "bf_threshold": _number(payload, "bf_threshold"),
            "bf_method": str(payload.get("bf_method", "jzs")).lower(),
            "r_scale": _number(payload, "r_scale") if payload.get("r_scale") not in (None, "") else 0.7071,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Bayes-factor two-sample design analysis"
        assumptions = [
            "The decision threshold is BF10 against a point-null, using a JZS Cauchy prior by default (or a BIC approximation if selected).",
            "This is a Bayesian design-analysis module, not a frequentist power calculation.",
            "One-sided Bayes factors and custom priors beyond the JZS r-scale need a custom analysis.",
        ]
        framework = "bayesian"
    elif model == "group_sequential_t":
        effect = {"cohens_d": _number(payload, "effect"), "parameterization": "standardized_mean_difference"}
        design = {
            "allocation_ratio": _number(payload, "allocation_ratio"),
            "looks": count(_number(payload, "looks"), "looks", 1),
            "equal_variance": True,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Group-sequential two-sample t plan"
        assumptions = [
            "Equally spaced looks with Lan-DeMets O'Brien-Fleming alpha-spending efficacy boundaries.",
            "Boundaries are solved so the cumulative type I error equals the stated alpha exactly; reported power is the sequential operating characteristic, not the fixed-design power at the same N.",
            "Efficacy stopping only: no futility boundary, so this is the power to cross an efficacy bound at some look.",
            "Unequal information fractions or futility rules need a design-specific sequential simulation.",
        ]
    elif model == "logrank_two_arm":
        allocation_ratio = _number(payload, "allocation_ratio")
        accrual_years = _number(payload, "accrual_years") if payload.get("accrual_years") not in (None, "") else 0.0
        followup_years = _number(payload, "followup_years") if payload.get("followup_years") not in (None, "") else 1.0
        dropout_hazard = _number(payload, "dropout_hazard") if payload.get("dropout_hazard") not in (None, "") else 0.0
        control_hazard = _number(payload, "control_hazard") if payload.get("control_hazard") not in (None, "") else 1.0
        hazard_ratio = _number(payload, "effect") if payload.get("effect") not in (None, "") else _number(payload, "hazard_ratio")
        if payload.get("effect") not in (None, "") and payload.get("hazard_ratio") not in (None, "") and _number(payload,"hazard_ratio") != hazard_ratio:
            raise ValueError("Conflicting hazard ratio aliases: effect and hazard_ratio differ")
        hazard_fields=("control_hazard","accrual_years","followup_years","dropout_hazard")
        supplied_hazards=any(payload.get(key) not in (None,"") for key in hazard_fields)
        if payload.get("p_event") not in (None, ""):
            p_event = _number(payload, "p_event")
            if supplied_hazards:
                derived=derive_logrank_event_probability(hazard_ratio,control_hazard,accrual_years,followup_years,dropout_hazard,allocation_ratio)
                if abs(derived-p_event)>1e-10:
                    raise ValueError("Conflicting event probability and hazard/follow-up inputs; choose one parameterization or supply matching values")
        else:
            # Single source of truth: the engine owns this derivation, so the planner and
            # `required_n_logrank_two_arm` cannot drift apart.
            p_event = derive_logrank_event_probability(
                hazard_ratio, control_hazard, accrual_years, followup_years, dropout_hazard, allocation_ratio
            )
        effect = {
            "hazard_ratio": hazard_ratio,
            "p_event": p_event,
            "parameterization": "hazard_ratio_and_event_probability",
        }
        design = {
            "allocation_ratio": allocation_ratio,
            "accrual_years": accrual_years,
            "followup_years": followup_years,
            "dropout_hazard": dropout_hazard,
            "control_hazard": control_hazard,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        if payload.get("p_event") not in (None, "") and not supplied_hazards:
            # Supplied event probability is the declared parameterization; do not
            # insert hazard/follow-up defaults that cause the reference to replace it.
            design = {"allocation_ratio": allocation_ratio, "attrition_rate": _number(payload, "attrition_rate")}
        title = "Two-arm log-rank survival plan"
        assumptions = [
            "The primary analysis is a two-arm log-rank test under proportional hazards.",
            "Events are planned via the Schoenfeld formula; total N = required events / p_event under administrative censoring.",
            (f"Planning event probability p_event={p_event:.17g} is supplied directly; hazard-based event derivation is not used." if payload.get("p_event") not in (None, "") and not supplied_hazards else f"Planning event probability p_event={p_event:.17g} is derived from accrual={accrual_years:g}y, follow-up={followup_years:g}y, and dropout hazard={dropout_hazard:g}."),
            "The optional separate simulation check assumes exponential event times; delayed entry, competing risks, and non-PH need a design-specific simulation.",
        ]
    elif model == "rope_equivalence_t":
        effect = {
            "lower_bound": _number(payload, "lower_bound"),
            "upper_bound": _number(payload, "upper_bound"),
            "true_difference": _number(payload, "true_difference") if payload.get("true_difference") not in (None, "") else 0.0,
            "sd": _number(payload, "sd"),
            "parameterization": "raw_rope_bounds",
        }
        design = {
            "allocation_ratio": _number(payload, "allocation_ratio"),
            "prior_sd": _number(payload, "prior_sd") if payload.get("prior_sd") not in (None, "") else 10.0,
            "rope_threshold": _number(payload, "rope_threshold") if payload.get("rope_threshold") not in (None, "") else 0.95,
            "attrition_rate": _number(payload, "attrition_rate"),
        }
        title = "Bayesian ROPE mean-equivalence plan"
        assumptions = [
            "Equivalence is declared when the posterior probability that the mean difference lies inside the ROPE meets the stated threshold.",
            "A normal–normal conjugate update is used with a normal prior on the mean difference (default prior_sd is diffuse).",
            "ROPE is Bayesian equivalence and is distinct from frequentist TOST; do not describe this as a TOST plan.",
        ]
        framework = "bayesian"
    else:
        raise ValueError("Choose one of the currently supported planning paths.")
    if multiplicity_method == "bonferroni" and primary_tests > 1:
        assumptions.append(
            f"Bonferroni adjusts the per-test alpha to family alpha / {primary_tests} "
            f"({family_alpha:g} / {primary_tests} = {alpha:g}) for equally weighted primary tests."
        )
    elif multiplicity_method == "hochberg" and primary_tests > 1:
        assumptions.append(
            f"Hochberg is a step-up procedure; this N is planned at the most stringent step "
            f"(family alpha / {primary_tests} = {alpha:g}), which is slightly conservative for Hochberg power "
            "relative to the full stepwise rule."
        )
    if multiplicity_method != "none":
        design.update(family_alpha=family_alpha, primary_tests=primary_tests)
    if "allocation_numerator" in payload or "allocation_denominator" in payload:
        from .allocation import declared_allocation_ratio
        pair={key:payload[key] for key in ("allocation_numerator","allocation_denominator") if key in payload}
        if "allocation_ratio" in payload:pair["allocation_ratio"]=_number(payload,"allocation_ratio")
        design.update(pair)
        design["allocation_ratio"]=float(declared_allocation_ratio(design))
    import json as _json
    for key, default in WIZARD_DEFAULTS.items():
        if payload.get(key) not in (None, ""):
            continue
        for section, values in (("effect", effect), ("design", design)):
            if key in values and values[key] == default:
                assumptions.append(f"{WIZARD_DEFAULT_PREFIX}{section}.{key} = {_json.dumps(default)}")
    if "target_power" in blank:
        assumptions.append(f"{WIZARD_DEFAULT_PREFIX}target_power = {_json.dumps(DEFAULT_TARGET_POWER)}")
    if "attrition_rate" in blank and design.get("attrition_rate") == 0:
        assumptions.append(f"{WIZARD_DEFAULT_PREFIX}design.attrition_rate = 0")
    scenario = Scenario(
        id="studio-preview",
        title=title,
        framework=framework,
        goal="required_sample_size",
        model=model,
        target_power=target_power,
        effect=effect,
        design=design,
        decision_rule=DecisionRule(alpha=alpha, alternative=alternative, multiplicity_method=multiplicity_method),
        simulation={"replications": 2000, "seed": 20260718},
        assumptions=assumptions,
        status="draft",
    )
    scenario.validate()
    return scenario, family_alpha, alpha, primary_tests


def make_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("goal","required_sample_size") != "required_sample_size" or any(payload.get(key) not in (None,"") for key in ("n1","n2","n_total")):
        raise ValueError("make_plan requires a required-sample-size goal without fixed sample counts")
    scenario, family_alpha, alpha, primary_tests = scenario_from_fields(payload)
    model, design = scenario.model, scenario.design
    reference = analytic_reference(scenario)
    two_arm = {
        "two_sample_t", "welch_t", "two_sample_proportion", "tost_equivalence", "noninferiority_t",
        "bayes_factor_t", "group_sequential_t", "logrank_two_arm", "rope_equivalence_t",
    }
    if model in two_arm:
        simulation = simulate(scenario, n1=reference["n1"], n2=reference["n2"])
    else:
        simulation = simulate(scenario, n_total=reference["n_total"])
    tool = RPwrAdapter().run(scenario)
    attrition = design.get("attrition_rate", 0)
    recruitment = None
    if attrition:
        from .recruitment import recruitment_counts
        recruitment = recruitment_counts(reference, attrition)["n_total"]
    reporting = _build_reporting(scenario, reference, recruitment, family_alpha, alpha)
    report = _plan_report(scenario, reference, simulation, tool, recruitment, reporting)
    alignment = _reference_simulation_alignment(reference, simulation)
    result = {
        "scenario": asdict(scenario),
        "reference": reference,
        "simulation": simulation,
        "tool_result": tool,
        "recruitment_total": recruitment,
        "report_markdown": report,
        "reporting": reporting,
        "reference_simulation_alignment": alignment,
        "family_alpha": family_alpha,
        "effective_alpha": alpha,
        "primary_tests": primary_tests,
        "sensitivity": _sensitivity_curve(scenario, reference),
        "heterogeneity_sensitivity": _heterogeneity_curve(scenario),
        "sensitivity_policy_version": SENSITIVITY_POLICY_VERSION, "planning_policy_version": "1.3",
        "caution": "This is a matched calculation under the displayed assumptions. It is not a declaration that the overall study plan is correct.",
    }
    from .provenance import provenance
    from .reproducibility import python_script, r_script
    request = {"schema_version": "1.0", "operation": "plan", "scenario": scenario.to_dict()}
    result["provenance"] = provenance(model, request)
    result["reproduction"] = [{"language": "python", "kind": "exact_reproduction", "code": python_script(payload, "make_plan")}]
    r = r_script(request)
    if r:
        result["reproduction"].append({"language": "r", "kind": "matched_independent_check", "code": r, "browser_status": "available_unverified_request"})
    result["normalized_request"] = request
    from .resources import method_attribution
    result["citations"] = [method_attribution(model)]
    return result



SENSITIVITY_POLICY_VERSION = "1.1"


def assumption_sensitivity(payload: dict[str, Any]) -> dict[str, Any]:
    """Required-N curves around the stated effect (and tau), without simulation or tool calls.

    Uses the same rows as ``make_plan`` so the browser planner can show them.
    """
    if payload.get("goal", "required_sample_size") != "required_sample_size" or any(payload.get(key) not in (None, "") for key in ("n1", "n2", "n_total")):
        raise ValueError("Assumption sensitivity requires a required-sample-size goal without fixed sample counts")
    scenario, *_ = scenario_from_fields(payload)
    return {
        "sensitivity": _sensitivity_curve(scenario, {}),
        "heterogeneity_sensitivity": _heterogeneity_curve(scenario),
        "sensitivity_policy_version": SENSITIVITY_POLICY_VERSION,
    }


def analyze_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wizard calculation; native required-N includes its checks."""
    request=request_from_fields(payload)
    if payload.get("goal","required_sample_size") == "required_sample_size":
        return make_plan(payload)
    from .api import analyze
    return analyze(request)


def request_from_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize wizard fields without running a calculation or external tool."""
    if not isinstance(payload,dict):
        raise ValueError("Planner fields must be an object")  # noqa: TRY004 -- portable JSON contract
    goal = payload.get("goal", "required_sample_size")
    if goal == "required_sample_size":
        if any(payload.get(key) not in (None, "") for key in ("n1", "n2", "n_total")):
            raise ValueError("Sample counts require an explicit achieved_power or sensitivity goal")
        scenario,*_=scenario_from_fields(payload)
        return {"operation":"plan","scenario":scenario.to_dict()}
    if goal not in {"achieved_power", "sensitivity"}:
        raise ValueError("Unrecognized analysis goal")
    from .capabilities import FIXED_MODELS
    from .power import count
    model = payload.get("model")
    if model not in FIXED_MODELS:
        raise ValueError("This method does not yet support a validated fixed-sample mode")
    sample = {k: payload[k] for k in ("n1", "n2", "n_total") if payload.get(k) not in (None, "")}
    source = {"target_power": DEFAULT_TARGET_POWER, "attrition_rate": 0, **payload}
    if model in {"two_sample_t", "welch_t"}:
        source["allocation_numerator"] = count(sample.get("n2"), "n2")
        source["allocation_denominator"] = count(sample.get("n1"), "n1")
        source["allocation_ratio"] = source["allocation_numerator"] / source["allocation_denominator"]
    if goal == "sensitivity" or payload.get("effect") in (0, "0", "0.0"):
        source["effect"] = 1e-6
    scenario, *_ = scenario_from_fields(source)
    if goal == "achieved_power" and payload.get("effect") in (0, "0", "0.0"):
        scenario = replace(scenario, effect={**scenario.effect, FIXED_MODELS[model]: 0.0})
    # The temporary target validates the legacy required-N field parser only.
    # Fixed-power requests retain a target solely when the caller supplied it.
    target = None if goal == "achieved_power" and payload.get("target_power") in (None, "") else scenario.target_power
    scenario = replace(scenario, goal=goal, target_power=target)
    return {"operation": "power" if goal == "achieved_power" else "detectable_effect", "scenario": scenario.to_dict(), "sample": sample}


def _reference_simulation_alignment(reference: dict[str, Any], simulation: dict[str, Any]) -> dict[str, str]:
    if simulation.get("failures", 0):
        return {"status": "fit_failures_unresolved", "message": "Some simulated fits failed. The estimate is conditional on successful fits and cannot establish alignment; inspect convergence before interpreting it."}
    low, high = simulation["mc_ci95"]
    if low <= reference["power"] <= high:
        return {"status": "compatible", "message": "The analytic reference lies within the simulation's Monte Carlo uncertainty interval under the displayed data-generating assumptions."}
    return {"status": "requires_assumption_review", "message": "The analytic reference lies outside the simulation's Monte Carlo uncertainty interval. Inspect whether the analytic approximation and simulated design make the same assumptions before choosing N."}


def _sensitivity_curve(scenario: Scenario, reference: dict[str, Any]) -> list[dict[str, float | int]]:
    """Required-N sensitivity across an interpretable range around the stated effect."""
    key = {
        "two_sample_t": "cohens_d", "welch_t": "mean_difference", "paired_t": "cohens_dz", "correlation": "rho",
        "one_way_anova": "cohens_f", "factorial_anova": "cohens_f", "ancova": "cohens_f", "planned_contrast": "cohens_f",
        "linear_regression": "cohens_f2", "incremental_regression": "cohens_f2", "moderation": "cohens_f2",
        "logistic_regression": "odds_ratio", "poisson_regression": "rate_ratio", "mediation_indirect": "a_path",
        "meta_analysis_fixed": "cohens_d", "meta_analysis_random": "cohens_d", "ordinal_regression": "odds_ratio",
        "bayes_factor_t": "cohens_d", "group_sequential_t": "cohens_d", "noninferiority_t": "margin",
        "logrank_two_arm": "hazard_ratio",
    }.get(scenario.model)
    rows = []
    for multiplier in (0.5, 0.75, 1.0, 1.25, 1.5):
        effect = dict(scenario.effect)
        if scenario.model == "one_sample_proportion":
            p0, p1 = effect["p_null"], effect["p_alternative"]
            effect["p_alternative"] = p0 + (p1 - p0) * multiplier
            displayed = effect["p_alternative"]
        elif scenario.model == "two_sample_proportion":
            p1, p2 = effect["p_group1"], effect["p_group2"]
            effect["p_group2"] = p1 + (p2 - p1) * multiplier
            displayed = effect["p_group2"]
        elif scenario.model == "chi_square_gof":
            p0, p1 = effect["p_null"], effect["p_alternative"]
            effect["p_alternative"] = [null + (alternative - null) * multiplier for null, alternative in zip(p0, p1)]
            effect["cohens_w"] = chi_square_gof_w(effect["p_null"], effect["p_alternative"])
            displayed = effect["cohens_w"]
        elif scenario.model == "chi_square_independence":
            # Shrink dependence toward independence margins.
            import numpy as np

            from .references import chi_square_independence_w
            table = np.array(effect["joint_probabilities"], dtype=float)
            row, col = table.sum(axis=1, keepdims=True), table.sum(axis=0, keepdims=True)
            independent = row @ col
            mixed = independent + (table - independent) * multiplier
            effect["joint_probabilities"] = mixed.tolist()
            displayed = chi_square_independence_w(effect["joint_probabilities"])
        elif scenario.model in {"tost_equivalence", "rope_equivalence_t"}:
            effect["lower_bound"] *= multiplier
            effect["upper_bound"] *= multiplier
            displayed = effect["upper_bound"] - effect["lower_bound"]
        elif scenario.model == "mediation_indirect":
            effect["a_path"] = effect["a_path"] * multiplier
            effect["b_path"] = effect["b_path"] * multiplier
            displayed = abs(effect["a_path"] * effect["b_path"])
        else:
            if key is None:
                continue
            if key in {"odds_ratio", "rate_ratio", "hazard_ratio"}:
                from math import exp, log
                effect[key] = exp(log(effect[key]) * multiplier)
                design = scenario.design
                if key == "hazard_ratio" and design.get("control_hazard") is not None and design.get("followup_years") is not None:
                    # The event probability depends on the hazard ratio; holding the
                    # baseline hazard and follow-up fixed, re-derive it for each row.
                    effect["p_event"] = derive_logrank_event_probability(
                        effect[key], float(design["control_hazard"]), float(design.get("accrual_years") or 0.0),
                        float(design["followup_years"]), float(design.get("dropout_hazard", 0.0)),
                        float(design.get("allocation_ratio", 1.0)))
            else:
                effect[key] = effect[key] * multiplier
            displayed = effect[key]
        try:
            candidate = replace(scenario, effect=effect)
            candidate.validate()
            result = analytic_reference(candidate)
        except (ValueError, RuntimeError, NotImplementedError) as error:
            rows.append({"effect": float(displayed), "multiplier": multiplier, "n_total": None, "status": "unavailable", "reason": str(error)})
            continue
        rows.append({"effect": float(displayed), "multiplier": multiplier, "n_total": int(result["n_total"]), "status": "complete"})
    return rows


def _heterogeneity_curve(scenario: Scenario) -> list[dict[str, float | int]]:
    """Required-N sensitivity across tau for random-effects meta-analysis."""
    if scenario.model != "meta_analysis_random":
        return []
    tau0 = float(scenario.design.get("tau", 0.0))
    rows: list[dict[str, float | int]] = []
    for multiplier in (0.5, 0.75, 1.0, 1.25, 1.5):
        design = dict(scenario.design)
        design["tau"] = max(0.0, tau0 * multiplier)
        try:
            result = analytic_reference(replace(scenario, design=design))
        except (ValueError, RuntimeError, NotImplementedError) as error:
            rows.append({"multiplier": float(multiplier), "tau": float(design["tau"]), "n_total": None, "status": "unavailable", "reason": str(error)})
            continue
        rows.append({"multiplier": float(multiplier), "tau": float(design["tau"]), "n_total": int(result["n_total"]), "status": "complete"})
    return rows


def _format_target_effect(scenario: Scenario) -> str:
    effect = scenario.effect
    model = scenario.model
    mapping = {
        "two_sample_t": ("Cohen's d", "cohens_d"),
        "welch_t": ("raw mean difference", "mean_difference"),
        "paired_t": ("Cohen's dz", "cohens_dz"),
        "correlation": ("Pearson rho", "rho"),
        "one_way_anova": ("Cohen's f", "cohens_f"),
        "factorial_anova": ("Cohen's f", "cohens_f"),
        "ancova": ("Cohen's f", "cohens_f"),
        "planned_contrast": ("Cohen's f", "cohens_f"),
        "linear_regression": ("Cohen's f²", "cohens_f2"),
        "incremental_regression": ("incremental f²", "cohens_f2"),
        "moderation": ("interaction f²", "cohens_f2"),
        "logistic_regression": ("odds ratio", "odds_ratio"),
        "poisson_regression": ("rate ratio", "rate_ratio"),
        "ordinal_regression": ("odds ratio", "odds_ratio"),
        "meta_analysis_fixed": ("average Cohen's d", "cohens_d"),
        "meta_analysis_random": ("average Cohen's d", "cohens_d"),
        "bayes_factor_t": ("Cohen's d", "cohens_d"),
        "group_sequential_t": ("Cohen's d", "cohens_d"),
        "noninferiority_t": ("non-inferiority margin", "margin"),
        "logrank_two_arm": ("hazard ratio", "hazard_ratio"),
        "one_sample_proportion": ("alternative proportion", "p_alternative"),
        "two_sample_proportion": ("group-2 proportion", "p_group2"),
    }
    if model in mapping:
        label, key = mapping[model]
        return f"{label} = {float(effect[key]):.3g}"
    if model == "chi_square_gof":
        return f"Cohen's w = {float(effect.get('cohens_w', 0)):.3g}"
    if model in {"tost_equivalence", "rope_equivalence_t"}:
        return f"bounds [{float(effect['lower_bound']):.3g}, {float(effect['upper_bound']):.3g}]"
    if model == "mediation_indirect":
        return f"a={float(effect['a_path']):.3g}, b={float(effect['b_path']):.3g}"
    return "the stated planning effect"


def _build_reporting(
    scenario: Scenario,
    reference: dict[str, Any],
    recruitment: int | None,
    family_alpha: float,
    alpha: float,
) -> dict[str, Any]:
    from .reporting import reporting
    return reporting(scenario, reference, _format_target_effect(scenario), recruitment, family_alpha)


def _tool_comparison_text(tool: dict[str, Any], reference: dict[str, Any]) -> str:
    """State what the external tool returned against the reference; never just its run status."""
    status = tool.get("status", "not run")
    if status != "ok":
        reason = f" ({tool['reason']})" if tool.get("reason") else ""
        return f"not compared: tool status {status}{reason}"
    label = f"{tool.get('package', tool.get('adapter', 'external tool'))} {tool.get('package_version', '')}".strip()
    other = (tool.get("result") or {}).get("n_total")
    if isinstance(other, bool) or not isinstance(other, (int, float)):
        return f"not compared: {label} returned no total sample size"
    if int(other) == other == reference["n_total"]:
        return f"{label} total N {int(other)} matches the reference total N {reference['n_total']}"
    return (f"{label} total N {other:g} differs from the reference total N {reference['n_total']}; "
            "check that both use the same parameterization before relying on either")


def _plan_report(
    scenario: Scenario,
    reference: dict[str, Any],
    simulation: dict[str, Any],
    tool: dict[str, Any],
    recruitment: int | None,
    reporting: dict[str, Any] | None = None,
) -> str:
    """Portable, reader-first hand-off summary generated by the same engine as Studio."""
    if reporting is None:
        reporting = _build_reporting(
            scenario,
            reference,
            recruitment,
            family_alpha=float(scenario.decision_rule.alpha),
            alpha=float(scenario.decision_rule.alpha),
        )
    allocations = f"{reference['n1']} + {reference['n2']}" if "n1" in reference else str(reference["n_total"])
    distinctions = reporting["distinctions"]
    lines = [
        "# PowerBench Studio plan",
        "",
        f"**Analysis:** {scenario.title}",
        f"**Framework:** {scenario.framework}",
        f"**Target effect (planning assumption, not observed):** {distinctions['target_effect']}",
        f"**Required analysable sample:** {reference['n_total']} total ({allocations}); this is not an observed sample size.",
        f"**Target and calculated power:** {scenario.target_power:.3%}; {reference['power']:.3f}",
        (
            f"**Decision rule:** {scenario.decision_rule.alternative}; "
            f"family alpha = {distinctions['family_alpha']}; "
            f"per-test alpha = {distinctions['test_alpha']} "
            f"({scenario.decision_rule.multiplicity_method})."
        ),
        f"**Reference method:** {reference['method'].replace('_', ' ')}",
        f"**Independent simulation:** {simulation['power']:.1%} (Monte Carlo 95% interval {simulation['mc_ci95'][0]:.1%}-{simulation['mc_ci95'][1]:.1%}; {simulation['replications_completed']} replications)",
        f"**Tool comparison:** {_tool_comparison_text(tool, reference)}",
    ]
    if recruitment:
        lines.append(
            f"**Recruitment target:** {recruitment} total after stated attrition; "
            f"analysable N ({distinctions['analysable_n']}) differs from recruitment N ({distinctions['recruitment_n']})."
        )
    else:
        lines.append(
            f"**Analysable vs recruitment N:** analysable N = {distinctions['analysable_n']}; "
            f"recruitment N = {distinctions['recruitment_n']} (no attrition inflation applied)."
        )
    if scenario.decision_rule.multiplicity_method != "none":
        lines.append(
            f"**Multiplicity:** family alpha ({distinctions['family_alpha']}) differs from "
            f"per-test alpha ({distinctions['test_alpha']}) under {scenario.decision_rule.multiplicity_method}."
        )
    if "prediction_interval_95" in reference:
        low, high = reference["prediction_interval_95"]
        lines.append(f"**Prediction interval (95%, new study):** [{low:.3f}, {high:.3f}]")
    if reference.get("hartung_knapp"):
        lines.append("**Hartung–Knapp:** enabled (t critical with df = studies − 1).")
    lines.extend([
        "",
        "## APA reporting draft",
        reporting["apa"],
        "",
        "## AMJ-style reporting draft",
        reporting["amj"],
        "",
        "## Assumptions to confirm",
        *[f"- {item}" for item in scenario.assumptions],
        "",
        "This report documents a matched calculation under stated assumptions. It does not certify that the overall study design is correct.",
    ])
    return "\n".join(lines)


