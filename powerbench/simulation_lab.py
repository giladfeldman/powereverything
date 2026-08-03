"""Simulation-first exemplars; intentionally not universal sample-size calculators."""

from __future__ import annotations

from math import sqrt
from typing import Any, Callable

import numpy as np
from scipy.stats import norm, t, ttest_ind


TEMPLATES: dict[str, dict[str, Any]] = {
    "clustered_continuous_two_arm": {
        "label": "Clustered continuous two-arm trial",
        "diagram": "arm -> clusters (random intercept, ICC) -> people -> outcome; analysis: Welch t-test of cluster means",
        "analysis_model": "Welch t-test of cluster means; cluster is the independent unit",
        "defaults": {"clusters_per_arm": 12, "cluster_size": 20, "icc": 0.05, "effect": 0.35, "outcome_sd": 1.0, "replications": 1000, "seed": 20260718},
        "boundary": "An exemplar DGP, not a universal cluster-trial N claim. Unequal cluster sizes, covariates, missingness, and mixed-model inference need their own scenario.",
    },
    "repeated_change_two_arm": {
        "label": "Two-arm repeated baseline/follow-up change design",
        "diagram": "arm -> person -> correlated baseline and follow-up -> change score; analysis: Welch t-test of change scores",
        "analysis_model": "Welch t-test of pre-specified person-level change scores",
        "defaults": {"participants_per_arm": 60, "correlation": 0.60, "effect": 0.35, "outcome_sd": 1.0, "replications": 1000, "seed": 20260718},
        "boundary": "An exemplar change-score analysis, not a generic mixed-model power calculation. Missing visits, unequal time spacing, random slopes, and MAR assumptions need a fitted-model simulation.",
    },
    "factorial_2x2_continuous": {
        "label": "2×2 between-subjects factorial with continuous outcome",
        "diagram": "A × B between subjects -> continuous outcome; analysis: OLS A + B + A:B",
        "analysis_model": "OLS with main effects and the pre-specified A × B interaction",
        "defaults": {"n_per_cell": 40, "effect_A": 0.20, "effect_B": 0.20, "effect_AB": 0.30, "outcome_sd": 1.0, "replications": 1000, "seed": 20260718},
        "boundary": "An equal-cell Gaussian factorial exemplar, not a universal ANOVA calculator. Unequal allocation, heteroscedasticity, covariates, missingness, and multiplicity need their own fitted-model simulation.",
    },
    "ancova_two_arm": {
        "label": "Two-arm ANCOVA with baseline covariate",
        "diagram": "arm + baseline covariate -> follow-up outcome; analysis: OLS outcome ~ arm + covariate",
        "analysis_model": "OLS follow-up outcome ~ treatment arm + covariate",
        "defaults": {"n_per_arm": 60, "effect": 0.35, "covariate_outcome_r": 0.60, "outcome_sd": 1.0, "replications": 1000, "seed": 20260718},
        "boundary": "An exemplar with a measured, linear, error-free covariate. Covariate imbalance, nonlinear prognostic effects, measurement error, missing follow-up, and covariate-selection rules need their own scenario.",
    },
    "logistic_two_arm": {
        "label": "Two-arm binary logistic trial",
        "diagram": "arm -> binary outcome; analysis: logistic treatment coefficient Wald test",
        "analysis_model": "Two-group logistic-regression Wald test of the treatment coefficient",
        "defaults": {"n_per_arm": 100, "p_control": 0.30, "odds_ratio": 1.60, "replications": 1000, "seed": 20260718},
        "boundary": "An equal-allocation, independent binary-outcome exemplar. Rare events, separation, covariate adjustment, clustering, attrition, and non-collapsibility need a purpose-built logistic simulation.",
    },
    "mediation_simple": {
        "label": "Simple X→M→Y mediation",
        "diagram": "X -> M -> Y, with optional direct X -> Y path; analysis: joint significance of a and b paths",
        "analysis_model": "OLS M ~ X and OLS Y ~ X + M; joint significance requires both a and b paths p < alpha",
        "defaults": {"n": 150, "a_path": 0.30, "b_path": 0.30, "direct_cprime": 0.10, "residual_sd": 1.0, "replications": 1000, "seed": 20260718},
        "boundary": "An observed-variable linear mediation exemplar, not evidence of causal mediation. Temporal ordering, confounding of all paths, measurement error, nonlinearity, and indirect-effect confidence intervals require a dedicated design and analysis plan.",
    },
    "mixed_model_two_arm_longitudinal": {
        "label": "Two-arm longitudinal mixed model (random intercept)",
        "diagram": "arm -> person (random intercept) -> 3 occasions; treatment on post-baseline; analysis: Welch on person-mean of follow-ups",
        "analysis_model": "Welch t-test of person-level means of post-baseline occasions (LMM surrogate; full REML LMM is not fitted)",
        "defaults": {"participants_per_arm": 40, "occasions": 3, "icc": 0.40, "effect": 0.35, "outcome_sd": 1.0, "replications": 1000, "seed": 20260727},
        "boundary": "An exemplar random-intercept longitudinal DGP, not a universal mixed-model calculator. No random slopes, MAR missingness, or unequal time spacing.",
    },
    "clustered_unequal_mar": {
        "label": "Clustered trial with unequal cluster sizes and MAR dropout",
        "diagram": "arm -> unequal clusters (ICC) -> people -> MAR dropout by outcome; analysis: Welch of complete-case cluster means",
        "analysis_model": "Welch t-test of observed (complete-case) cluster means among remaining people",
        "defaults": {"clusters_per_arm": 10, "cluster_size_min": 8, "cluster_size_max": 25, "icc": 0.05, "effect": 0.35, "outcome_sd": 1.0, "mar_intercept": -1.5, "mar_slope": -0.4, "replications": 1000, "seed": 20260727},
        "boundary": "A MAR dropout exemplar for teaching, not a multiple-imputation or MMRM calculator. Unequal cluster sizes and complete-case cluster means only.",
    },
    "mixed_model_random_slopes": {
        "label": "Two-arm longitudinal mixed model (random slopes)",
        "diagram": "arm -> person (random intercept + random slope on time) -> occasions; treatment × time interaction; analysis: Welch on person-level OLS slopes",
        "analysis_model": "Welch t-test of person-level OLS slopes on time (LMM surrogate; full REML random-slopes LMM is not fitted)",
        "defaults": {
            "participants_per_arm": 30,
            "occasions": 4,
            "intercept_sd": 0.5,
            "slope_sd": 0.2,
            "effect": 0.15,
            "residual_sd": 1.0,
            "replications": 1000,
            "seed": 20260727,
        },
        "boundary": "An exemplar random-intercept + random-slope DGP with a person-level OLS slope surrogate, not a universal REML mixed-model calculator. MAR missingness, correlated random effects, and fitted LMM inference need their own scenario.",
    },
    "sem_two_mediators": {
        "label": "Two-mediator path model (X→M1→M2→Y)",
        "diagram": "X -> M1 -> M2 -> Y with optional direct X -> Y; analysis: joint significance of a1, a2, and b paths",
        "analysis_model": "OLS M1 ~ X, M2 ~ M1, and Y ~ X + M2; joint significance requires a1, a2, and b all p < alpha",
        "defaults": {
            "n": 200,
            "a1": 0.30,
            "a2": 0.30,
            "b": 0.30,
            "direct": 0.05,
            "residual_sd": 1.0,
            "residual_corr": 0.0,
            "replications": 1000,
            "seed": 20260727,
        },
        "boundary": "An observed-variable path-model exemplar, not an identified CFA/SEM with latent variables. Measurement models, cross-lagged panels, bootstrapped indirect effects, and confounding of all paths need a dedicated SEM design.",
    },
}


def templates() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in TEMPLATES.items()]


def _ci(rate: float, completed: int) -> list[float]:
    se = sqrt(rate * (1 - rate) / completed)
    return [max(0, rate - 1.96 * se), min(1, rate + 1.96 * se)]


def _cluster_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    clusters, size, icc, sd = int(values["clusters_per_arm"]), int(values["cluster_size"]), float(values["icc"]), float(values["outcome_sd"])
    means, preview = [], []
    for arm, shift in ((0, 0.0), (1, effect)):
        intercepts = rng.normal(0, sd * sqrt(icc), clusters)
        residuals = rng.normal(0, sd * sqrt(1 - icc), (clusters, size))
        outcomes = shift + intercepts[:, None] + residuals
        means.append(outcomes.mean(axis=1))
        if not preview:
            preview = [{"arm": arm, "cluster": int(cluster), "outcome": float(value)} for cluster, row in enumerate(outcomes[:2]) for value in row[:3]]
    return float(ttest_ind(means[1], means[0], equal_var=False).pvalue), preview


def _change_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    n, correlation, sd = int(values["participants_per_arm"]), float(values["correlation"]), float(values["outcome_sd"])
    covariance = np.array([[sd**2, correlation * sd**2], [correlation * sd**2, sd**2]])
    changes, preview = [], []
    for arm, shift in ((0, 0.0), (1, effect)):
        pair = rng.multivariate_normal([0, shift], covariance, n)
        changes.append(pair[:, 1] - pair[:, 0])
        if not preview:
            preview = [{"arm": arm, "participant": int(i), "baseline": float(row[0]), "follow_up": float(row[1]), "change": float(row[1] - row[0])} for i, row in enumerate(pair[:6])]
    return float(ttest_ind(changes[1], changes[0], equal_var=False).pvalue), preview


def _ols_pvalue(y: np.ndarray, design: np.ndarray, column: int) -> float:
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coefficients
    degrees_of_freedom = len(y) - design.shape[1]
    if degrees_of_freedom <= 0:
        return 1.0
    covariance = (residuals @ residuals / degrees_of_freedom) * np.linalg.pinv(design.T @ design)
    standard_error = sqrt(max(0.0, float(covariance[column, column])))
    return 1.0 if standard_error == 0 else float(2 * t.sf(abs(coefficients[column] / standard_error), degrees_of_freedom))


def _factorial_once(rng: np.random.Generator, values: dict[str, float], interaction: float) -> tuple[float, list[dict[str, float]]]:
    n, sd = int(values["n_per_cell"]), float(values["outcome_sd"])
    a, b = np.repeat([0.0, 1.0], 2 * n), np.tile(np.repeat([0.0, 1.0], n), 2)
    y = float(values["effect_A"]) * a + float(values["effect_B"]) * b + interaction * a * b + rng.normal(0, sd, 4 * n)
    return _ols_pvalue(y, np.column_stack((np.ones(4 * n), a, b, a * b)), 3), [{"A": int(a[i]), "B": int(b[i]), "outcome": float(y[i])} for i in range(min(6, 4 * n))]


def _ancova_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    n, r, sd = int(values["n_per_arm"]), float(values["covariate_outcome_r"]), float(values["outcome_sd"])
    arm = np.repeat([0.0, 1.0], n)
    covariate = rng.normal(0, 1, 2 * n)
    outcome = effect * arm + sd * (r * covariate + sqrt(1 - r**2) * rng.normal(0, 1, 2 * n))
    return _ols_pvalue(outcome, np.column_stack((np.ones(2 * n), arm, covariate)), 1), [{"arm": int(arm[i]), "covariate": float(covariate[i]), "outcome": float(outcome[i])} for i in range(min(6, 2 * n))]


def _logistic_once(rng: np.random.Generator, values: dict[str, float], odds_ratio: float) -> tuple[float, list[dict[str, float]]]:
    n, control = int(values["n_per_arm"]), float(values["p_control"])
    treated = odds_ratio * control / (1 - control + odds_ratio * control)
    events = np.array([rng.binomial(n, control), rng.binomial(n, treated)], dtype=float)
    log_odds_ratio = np.log((events[1] + .5) * (n - events[0] + .5) / ((n - events[1] + .5) * (events[0] + .5)))
    se = sqrt(np.sum(1 / (np.repeat(n, 2) - events + .5) + 1 / (events + .5)))
    pvalue = float(2 * norm.sf(abs(log_odds_ratio / se)))
    rows = [{"arm": arm, "outcome": outcome} for arm, probability in ((0, control), (1, treated)) for outcome in rng.binomial(1, probability, min(3, n))]
    return pvalue, rows


def _mediation_once(rng: np.random.Generator, values: dict[str, float], multiplier: float) -> tuple[float, list[dict[str, float]]]:
    n, sd = int(values["n"]), float(values["residual_sd"])
    x = rng.normal(0, 1, n)
    mediator = float(values["a_path"]) * multiplier * x + rng.normal(0, sd, n)
    outcome = float(values["b_path"]) * multiplier * mediator + float(values["direct_cprime"]) * x + rng.normal(0, sd, n)
    p_a = _ols_pvalue(mediator, np.column_stack((np.ones(n), x)), 1)
    p_b = _ols_pvalue(outcome, np.column_stack((np.ones(n), x, mediator)), 2)
    return (max(p_a, p_b), [{"x": float(x[i]), "mediator": float(mediator[i]), "outcome": float(outcome[i])} for i in range(min(6, n))])


def _mixed_longitudinal_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    n, occasions, icc, sd = int(values["participants_per_arm"]), int(values["occasions"]), float(values["icc"]), float(values["outcome_sd"])
    occasions = max(2, occasions)
    person_means, preview = [], []
    for arm, shift in ((0, 0.0), (1, effect)):
        intercepts = rng.normal(0, sd * sqrt(icc), n)
        residuals = rng.normal(0, sd * sqrt(1 - icc), (n, occasions))
        treatment = np.zeros(occasions)
        treatment[1:] = shift  # treatment on post-baseline occasions only
        outcomes = intercepts[:, None] + treatment[None, :] + residuals
        person_means.append(outcomes[:, 1:].mean(axis=1))
        if not preview:
            preview = [{"arm": arm, "participant": int(i), "occasion": int(t), "outcome": float(outcomes[i, t])} for i in range(min(2, n)) for t in range(occasions)]
    return float(ttest_ind(person_means[1], person_means[0], equal_var=False).pvalue), preview


def _clustered_mar_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    clusters, size_min, size_max = int(values["clusters_per_arm"]), int(values["cluster_size_min"]), int(values["cluster_size_max"])
    icc, sd = float(values["icc"]), float(values["outcome_sd"])
    mar_intercept, mar_slope = float(values["mar_intercept"]), float(values["mar_slope"])
    size_lo, size_hi = min(size_min, size_max), max(size_min, size_max)
    means, preview = [], []
    for arm, shift in ((0, 0.0), (1, effect)):
        arm_means = []
        for cluster in range(clusters):
            size = int(rng.integers(size_lo, size_hi + 1))
            intercept = rng.normal(0, sd * sqrt(icc))
            outcomes = shift + intercept + rng.normal(0, sd * sqrt(1 - icc), size)
            dropout_logit = mar_intercept + mar_slope * outcomes
            observed = rng.random(size) >= 1 / (1 + np.exp(-dropout_logit))
            remaining = outcomes[observed]
            if remaining.size:
                arm_means.append(float(remaining.mean()))
            if arm == 0 and cluster < 2:
                for person, (outcome, keep) in enumerate(zip(outcomes[:3], observed[:3])):
                    preview.append({"arm": arm, "cluster": cluster, "person": person, "outcome": float(outcome), "observed": int(keep)})
        means.append(np.array(arm_means) if arm_means else np.array([0.0]))
    if len(means[0]) < 2 or len(means[1]) < 2:
        return 1.0, preview
    return float(ttest_ind(means[1], means[0], equal_var=False).pvalue), preview


def _mixed_random_slopes_once(rng: np.random.Generator, values: dict[str, float], effect: float) -> tuple[float, list[dict[str, float]]]:
    n = int(values["participants_per_arm"])
    occasions = max(2, int(values["occasions"]))
    intercept_sd, slope_sd, residual_sd = float(values["intercept_sd"]), float(values["slope_sd"]), float(values["residual_sd"])
    time = np.arange(occasions, dtype=float)
    time_design = np.column_stack((np.ones(occasions), time))
    slopes, preview = [], []
    for arm, treat_slope in ((0, 0.0), (1, effect)):
        intercepts = rng.normal(0, intercept_sd, n)
        person_slopes = rng.normal(treat_slope, slope_sd, n)
        arm_slopes = []
        for person in range(n):
            outcome = intercepts[person] + person_slopes[person] * time + rng.normal(0, residual_sd, occasions)
            coefficients, _, _, _ = np.linalg.lstsq(time_design, outcome, rcond=None)
            arm_slopes.append(float(coefficients[1]))
            if arm == 0 and person < 2:
                for occasion in range(occasions):
                    preview.append({
                        "arm": arm,
                        "participant": person,
                        "occasion": occasion,
                        "outcome": float(outcome[occasion]),
                        "person_slope": float(coefficients[1]),
                    })
        slopes.append(np.array(arm_slopes))
    return float(ttest_ind(slopes[1], slopes[0], equal_var=False).pvalue), preview


def _sem_two_mediators_once(rng: np.random.Generator, values: dict[str, float], multiplier: float) -> tuple[float, list[dict[str, float]]]:
    n, sd = int(values["n"]), float(values["residual_sd"])
    a1 = float(values["a1"]) * multiplier
    a2 = float(values["a2"]) * multiplier
    b = float(values["b"]) * multiplier
    direct = float(values["direct"])
    corr = float(np.clip(values.get("residual_corr", 0.0), -0.95, 0.95))
    x = rng.normal(0, 1, n)
    m1 = a1 * x + rng.normal(0, sd, n)
    residual_m2 = rng.normal(0, 1, n)
    residual_y = corr * residual_m2 + sqrt(max(0.0, 1 - corr**2)) * rng.normal(0, 1, n)
    m2 = a2 * m1 + sd * residual_m2
    outcome = b * m2 + direct * x + sd * residual_y
    p_a1 = _ols_pvalue(m1, np.column_stack((np.ones(n), x)), 1)
    p_a2 = _ols_pvalue(m2, np.column_stack((np.ones(n), m1)), 1)
    p_b = _ols_pvalue(outcome, np.column_stack((np.ones(n), x, m2)), 2)
    preview = [{"x": float(x[i]), "m1": float(m1[i]), "m2": float(m2[i]), "outcome": float(outcome[i])} for i in range(min(6, n))]
    return max(p_a1, p_a2, p_b), preview


def run(payload: dict[str, Any], progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    update = progress or (lambda _percent, _message: None)
    update(3, "Validating the study assumptions")
    template_id = str(payload.get("template_id", ""))
    if template_id not in TEMPLATES:
        raise ValueError("Choose a supported simulation-first exemplar.")
    template = TEMPLATES[template_id]
    values = {**template["defaults"], **{key: value for key, value in payload.items() if key != "template_id"}}
    positive_keys = {
        "clustered_continuous_two_arm": ("effect", "outcome_sd", "replications"),
        "repeated_change_two_arm": ("effect", "outcome_sd", "replications"),
        "factorial_2x2_continuous": ("n_per_cell", "outcome_sd", "replications"),
        "ancova_two_arm": ("n_per_arm", "effect", "outcome_sd", "replications"),
        "logistic_two_arm": ("n_per_arm", "odds_ratio", "replications"),
        "mediation_simple": ("n", "residual_sd", "replications"),
        "mixed_model_two_arm_longitudinal": ("participants_per_arm", "occasions", "effect", "outcome_sd", "replications"),
        "clustered_unequal_mar": ("clusters_per_arm", "cluster_size_min", "cluster_size_max", "effect", "outcome_sd", "replications"),
        "mixed_model_random_slopes": ("participants_per_arm", "occasions", "intercept_sd", "slope_sd", "effect", "residual_sd", "replications"),
        "sem_two_mediators": ("n", "residual_sd", "replications"),
    }
    for key in positive_keys[template_id]:
        if float(values[key]) <= 0:
            raise ValueError(f"{key.replace('_', ' ')} must be positive.")
    bounded_keys = {
        "icc": (0.0, 1.0),
        "correlation": (0.0, 1.0),
        "covariate_outcome_r": (-1.0, 1.0),
        "p_control": (0.0, 1.0),
        "residual_corr": (-1.0, 1.0),
    }
    for key, (lower, upper) in bounded_keys.items():
        if key in values and not lower <= float(values[key]) < upper:
            raise ValueError(f"{key.replace('_', ' ')} must lie in [{lower}, {upper}).")
    path_multiplier_templates = {"mediation_simple", "sem_two_mediators"}
    specifications = {
        "clustered_continuous_two_arm": (_cluster_once, "effect", "icc", 0.0),
        "repeated_change_two_arm": (_change_once, "effect", "correlation", 0.0),
        "factorial_2x2_continuous": (_factorial_once, "effect_AB", "outcome_sd", 0.0),
        "ancova_two_arm": (_ancova_once, "effect", "outcome_sd", 0.0),
        "logistic_two_arm": (_logistic_once, "odds_ratio", "p_control", 1.0),
        "mediation_simple": (_mediation_once, "mediation_multiplier", "residual_sd", 0.0),
        "mixed_model_two_arm_longitudinal": (_mixed_longitudinal_once, "effect", "icc", 0.0),
        "clustered_unequal_mar": (_clustered_mar_once, "effect", "icc", 0.0),
        "mixed_model_random_slopes": (_mixed_random_slopes_once, "effect", "residual_sd", 0.0),
        "sem_two_mediators": (_sem_two_mediators_once, "path_multiplier", "residual_sd", 0.0),
    }
    run_once, signal_key, sensitivity_key, null_signal = specifications[template_id]
    reps, alpha, rng = int(values["replications"]), float(values.get("alpha", .05)), np.random.default_rng(int(values["seed"]))
    if reps < 1:
        raise ValueError("replications must be at least one.")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1).")
    def estimate(effect: float, count: int, capture: bool = False) -> tuple[float, list[dict[str, float]]]:
        pvalues, preview = [], []
        for _ in range(count):
            pvalue, rows = run_once(rng, values, effect)
            pvalues.append(pvalue)
            if capture and not preview: preview = rows
        return float(np.mean(np.array(pvalues) < alpha)), preview
    update(12, "Generating studies under the planned effect")
    planned_signal = 1.0 if template_id in path_multiplier_templates else float(values[signal_key])
    power, preview = estimate(planned_signal, reps, True)
    update(48, "Checking false-positive behavior under no effect")
    type_i_error, _ = estimate(null_signal, reps)
    update(68, "Running the sensitivity grid")
    grid, grid_reps = [], min(300, reps)
    for effect_multiplier in (.75, 1.0, 1.25):
        for sensitivity_multiplier in (.75, 1.0, 1.25):
            changed = dict(values); changed[sensitivity_key] = float(values[sensitivity_key]) * sensitivity_multiplier
            if sensitivity_key in {"icc", "correlation", "covariate_outcome_r", "residual_corr"}:
                lower = -.95 if sensitivity_key in {"covariate_outcome_r", "residual_corr"} else 0
                changed[sensitivity_key] = float(np.clip(changed[sensitivity_key], lower, .95))
            elif sensitivity_key == "p_control":
                changed[sensitivity_key] = min(.999, changed[sensitivity_key])
            old_values = values; values = changed
            signal = effect_multiplier if template_id in path_multiplier_templates else float(changed[signal_key]) * effect_multiplier
            rate, _ = estimate(signal, grid_reps)
            values = old_values
            grid.append({"effect_multiplier": effect_multiplier, "noise_multiplier": sensitivity_multiplier, "power": rate})
            update(68 + int(27 * len(grid) / 9), f"Sensitivity scenario {len(grid)} of 9")
    by_effect = max(row["power"] for row in grid if row["noise_multiplier"] == 1) - min(row["power"] for row in grid if row["noise_multiplier"] == 1)
    by_noise = max(row["power"] for row in grid if row["effect_multiplier"] == 1) - min(row["power"] for row in grid if row["effect_multiplier"] == 1)
    driver = "effect size" if by_effect >= by_noise else sensitivity_key.replace("_", " ")
    update(98, "Preparing the explanation and results")
    return {"classification": "simulation_first_exemplar_not_universal_calculator", "template": {"id": template_id, "label": template["label"], "diagram": template["diagram"], "analysis_model": template["analysis_model"], "boundary": template["boundary"]}, "assumptions": values, "preview_dataset": preview, "power": power, "power_mc_ci95": _ci(power, reps), "type_i_error": type_i_error, "type_i_error_mc_ci95": _ci(type_i_error, reps), "replications": reps, "failures": 0, "sensitivity_grid": grid, "largest_observed_sensitivity_driver": driver}
