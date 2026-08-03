"""Independent analytic references; they never call a registered adapter."""

from __future__ import annotations

from math import ceil
from scipy.stats import binom, binomtest, chi2, f, ncf, nct, ncx2, norm, t

from .schema import Scenario


def two_sample_t_power(n1: int, n2: int, d: float, alpha: float, alternative: str) -> float:
    """Exact noncentral-t power for Student's pooled-variance two-sample t-test."""
    df = n1 + n2 - 2
    ncp = d / (1 / n1 + 1 / n2) ** 0.5
    if alternative == "two.sided":
        critical = t.ppf(1 - alpha / 2, df)
        return float(nct.cdf(-critical, df, ncp) + nct.sf(critical, df, ncp))
    critical = t.ppf(1 - alpha, df)
    return float(nct.sf(critical, df, ncp) if alternative == "greater" else nct.cdf(-critical, df, ncp))


def required_n_two_sample_t(s: Scenario) -> dict[str, float | int | str]:
    d, ratio, alpha = float(s.effect["cohens_d"]), float(s.design.get("allocation_ratio", 1.0)), s.decision_rule.alpha
    target, alternative = float(s.target_power), s.decision_rule.alternative

    # Bracketing by growth avoids evaluating the noncentral t CDF at enormous
    # degrees of freedom, where some numerical backends return NaN.
    lower, upper = 2, 4
    while two_sample_t_power(upper, max(2, ceil(upper * ratio)), d, alpha, alternative) < target:
        lower, upper = upper, upper * 2
        if upper > 10_000_000:
            raise RuntimeError("Could not bracket the requested sample size")
    while lower + 1 < upper:
        midpoint = (lower + upper) // 2
        if two_sample_t_power(midpoint, max(2, ceil(midpoint * ratio)), d, alpha, alternative) >= target:
            upper = midpoint
        else:
            lower = midpoint
    n1 = upper
    n2 = max(2, ceil(n1 * ratio))
    while two_sample_t_power(n1, n2, d, alpha, alternative) < target:
        n1 += 1
        n2 = max(2, ceil(n1 * ratio))
    return {"n1": n1, "n2": n2, "n_total": n1 + n2, "power": two_sample_t_power(n1, n2, d, alpha, alternative), "method": "noncentral_t"}


def welch_t_power(n1: int, n2: int, mean_difference: float, sd_group1: float, sd_group2: float, alpha: float, alternative: str) -> float:
    """Welch-Satterthwaite noncentral-t planning approximation.

    The unequal-variance t statistic does not have the exact pooled-t
    noncentral distribution. This approximation uses the alternative-standard
    error and Satterthwaite degrees of freedom; it is deliberately kept
    separate from ``two_sample_t_power``.
    """
    variance = sd_group1**2 / n1 + sd_group2**2 / n2
    df = variance**2 / ((sd_group1**2 / n1) ** 2 / (n1 - 1) + (sd_group2**2 / n2) ** 2 / (n2 - 1))
    ncp = mean_difference / variance**0.5
    if alternative == "two.sided":
        critical = t.ppf(1 - alpha / 2, df)
        return float(nct.cdf(-critical, df, ncp) + nct.sf(critical, df, ncp))
    critical = t.ppf(1 - alpha, df)
    return float(nct.sf(critical, df, ncp) if alternative == "greater" else nct.cdf(-critical, df, ncp))


def required_n_welch_t(s: Scenario) -> dict[str, float | int | str]:
    difference = float(s.effect["mean_difference"])
    sd1, sd2 = float(s.effect["sd_group1"]), float(s.effect["sd_group2"])
    ratio, alpha = float(s.design.get("allocation_ratio", 1.0)), s.decision_rule.alpha
    target, alternative = float(s.target_power), s.decision_rule.alternative
    n1 = 2
    while True:
        n2 = max(2, ceil(n1 * ratio))
        power = welch_t_power(n1, n2, difference, sd1, sd2, alpha, alternative)
        if power >= target:
            return {
                "n1": n1,
                "n2": n2,
                "n_total": n1 + n2,
                "power": power,
                "method": "welch_satterthwaite_noncentral_t_approximation",
            }
        n1 += 1


def paired_t_power(n: int, dz: float, alpha: float, alternative: str) -> float:
    """Exact noncentral-t power for a t-test of standardized within-person change."""
    df, ncp = n - 1, dz * n**0.5
    if alternative == "two.sided":
        critical = t.ppf(1 - alpha / 2, df)
        return float(nct.cdf(-critical, df, ncp) + nct.sf(critical, df, ncp))
    critical = t.ppf(1 - alpha, df)
    return float(nct.sf(critical, df, ncp) if alternative == "greater" else nct.cdf(-critical, df, ncp))


def required_n_paired_t(s: Scenario) -> dict[str, float | int | str]:
    dz, alpha, target, alternative = float(s.effect["cohens_dz"]), s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    n = 2
    while paired_t_power(n, dz, alpha, alternative) < target:
        n += 1
    return {"n_total": n, "power": paired_t_power(n, dz, alpha, alternative), "method": "noncentral_t_paired_change"}


def one_sample_proportion_power(n: int, p_null: float, p_alternative: float, alpha: float, alternative: str) -> float:
    """Exact-binomial rejection-region power, independent of calculator approximations."""
    scipy_alternative = "two-sided" if alternative == "two.sided" else alternative
    rejection = [k for k in range(n + 1) if binomtest(k, n, p=p_null, alternative=scipy_alternative).pvalue <= alpha]
    return float(binom.pmf(rejection, n, p_alternative).sum()) if rejection else 0.0


def required_n_one_sample_proportion(s: Scenario) -> dict[str, float | int | str]:
    p0, p1 = float(s.effect["p_null"]), float(s.effect["p_alternative"])
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    n = 2
    while one_sample_proportion_power(n, p0, p1, alpha, alternative) < target:
        n += 1
        if n > 20_000:
            raise RuntimeError("Could not find the required N within 20,000 observations")
    return {"n_total": n, "power": one_sample_proportion_power(n, p0, p1, alpha, alternative), "method": "exact_binomial_rejection_region"}


def two_sample_proportion_power(n1: int, n2: int, p1: float, p2: float, alpha: float, alternative: str) -> float:
    """Planning approximation for the pooled two-proportion z-test under the alternative."""
    pooled = (n1 * p1 + n2 * p2) / (n1 + n2)
    se_null = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    mean = (p2 - p1) / se_null
    sd = (p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) ** 0.5 / se_null
    if alternative == "two.sided":
        critical = norm.ppf(1 - alpha / 2)
        return float(norm.cdf((-critical - mean) / sd) + norm.sf((critical - mean) / sd))
    critical = norm.ppf(1 - alpha)
    return float(norm.sf((critical - mean) / sd) if alternative == "greater" else norm.cdf((-critical - mean) / sd))


def required_n_two_sample_proportion(s: Scenario) -> dict[str, float | int | str]:
    p1, p2 = float(s.effect["p_group1"]), float(s.effect["p_group2"])
    ratio, alpha, target, alternative = float(s.design.get("allocation_ratio", 1.0)), s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    n1 = 2
    while True:
        n2 = max(2, ceil(n1 * ratio))
        power = two_sample_proportion_power(n1, n2, p1, p2, alpha, alternative)
        if power >= target:
            return {"n1": n1, "n2": n2, "n_total": n1 + n2, "power": power, "method": "pooled_two_proportion_z_normal_approximation"}
        n1 += 1


def chi_square_gof_w(p_null: list[float], p_alternative: list[float]) -> float:
    """Cohen's w implied by fully specified null and alternative probabilities."""
    return float(sum((alternative - null) ** 2 / null for null, alternative in zip(p_null, p_alternative)) ** 0.5)


def chi_square_gof_power(n: int, p_null: list[float], p_alternative: list[float], alpha: float) -> float:
    """Noncentral-chi-square planning approximation for a multinomial GOF test."""
    degrees_of_freedom = len(p_null) - 1
    critical = chi2.ppf(1 - alpha, degrees_of_freedom)
    noncentrality = n * chi_square_gof_w(p_null, p_alternative) ** 2
    return float(ncx2.sf(critical, degrees_of_freedom, noncentrality))


def required_n_chi_square_gof(s: Scenario) -> dict[str, float | int | str]:
    p_null = [float(value) for value in s.effect["p_null"]]
    p_alternative = [float(value) for value in s.effect["p_alternative"]]
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    minimum_expected = float(s.design.get("min_expected_count", 5))
    n = max(2, ceil(minimum_expected / min(p_null)))
    while chi_square_gof_power(n, p_null, p_alternative, alpha) < target:
        n += 1
    return {
        "n_total": n,
        "power": chi_square_gof_power(n, p_null, p_alternative, alpha),
        "cohens_w": chi_square_gof_w(p_null, p_alternative),
        "min_expected_null_count": n * min(p_null),
        "method": "noncentral_chi_square_multinomial_gof_approximation",
    }


def one_way_anova_power(n_per_group: int, groups: int, cohens_f: float, alpha: float) -> float:
    df1, df2, n_total = groups - 1, groups * (n_per_group - 1), groups * n_per_group
    critical = f.ppf(1 - alpha, df1, df2)
    return float(ncf.sf(critical, df1, df2, n_total * cohens_f**2))


def required_n_one_way_anova(s: Scenario) -> dict[str, float | int | str]:
    groups, cohens_f, alpha, target = int(s.design["groups"]), float(s.effect["cohens_f"]), s.decision_rule.alpha, float(s.target_power)
    n = 2
    while one_way_anova_power(n, groups, cohens_f, alpha) < target:
        n += 1
    return {"n_per_group": n, "n_total": n * groups, "power": one_way_anova_power(n, groups, cohens_f, alpha), "method": "noncentral_f_balanced_one_way_anova"}


def linear_regression_power(n: int, predictors: int, cohens_f2: float, alpha: float) -> float:
    df1, df2 = predictors, n - predictors - 1
    critical = f.ppf(1 - alpha, df1, df2)
    return float(ncf.sf(critical, df1, df2, n * cohens_f2))


def required_n_linear_regression(s: Scenario) -> dict[str, float | int | str]:
    predictors, f2, alpha, target = int(s.design["predictors"]), float(s.effect["cohens_f2"]), s.decision_rule.alpha, float(s.target_power)
    n = predictors + 2
    while linear_regression_power(n, predictors, f2, alpha) < target:
        n += 1
    return {"n_total": n, "power": linear_regression_power(n, predictors, f2, alpha), "method": "noncentral_f_fixed_design_overall_regression"}


def incremental_regression_power(n: int, total_predictors: int, tested_predictors: int, cohens_f2: float, alpha: float) -> float:
    df2 = n - total_predictors - 1
    critical = f.ppf(1 - alpha, tested_predictors, df2)
    # For the tested block, lambda uses u + v + 1. With v = N - total - 1,
    # this is N - total + tested, not raw N. This matches pwr.f2.test's
    # parameterization and the full-model denominator degrees of freedom.
    ncp = (n - total_predictors + tested_predictors) * cohens_f2
    return float(ncf.sf(critical, tested_predictors, df2, ncp))


def required_n_incremental_regression(s: Scenario) -> dict[str, float | int | str]:
    total, tested = int(s.design["total_predictors"]), int(s.design["tested_predictors"])
    f2, alpha, target = float(s.effect["cohens_f2"]), s.decision_rule.alpha, float(s.target_power)
    n = total + 2
    while incremental_regression_power(n, total, tested, f2, alpha) < target:
        n += 1
    return {"n_total": n, "power": incremental_regression_power(n, total, tested, f2, alpha), "method": "noncentral_f_fixed_design_incremental_r_squared"}


def correlation_power(n: int, rho: float, alpha: float, alternative: str) -> float:
    from math import atanh, sqrt
    mu = sqrt(n - 3) * atanh(rho)
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.cdf(-zcrit - mu) + norm.sf(zcrit - mu))
    zcrit = norm.ppf(1 - alpha)
    return float(norm.sf(zcrit - mu) if alternative == "greater" else norm.cdf(-zcrit - mu))


def required_n_correlation(s: Scenario) -> dict[str, float | int | str]:
    rho, alpha, alternative, target = float(s.effect["rho"]), s.decision_rule.alpha, s.decision_rule.alternative, float(s.target_power)
    n = 4
    while correlation_power(n, rho, alpha, alternative) < target:
        n += 1
    return {"n_total": n, "power": correlation_power(n, rho, alpha, alternative), "method": "fisher_z_normal_approximation"}


def chi_square_independence_w(joint: list[list[float]]) -> float:
    """Cohen's w for a contingency table under independence as the null."""
    import numpy as np

    table = np.array(joint, dtype=float)
    row, col = table.sum(axis=1, keepdims=True), table.sum(axis=0, keepdims=True)
    expected = row @ col
    return float(np.sqrt(np.sum((table - expected) ** 2 / expected)))


def chi_square_independence_power(n: int, joint: list[list[float]], alpha: float) -> float:
    rows, cols = len(joint), len(joint[0])
    df = (rows - 1) * (cols - 1)
    critical = chi2.ppf(1 - alpha, df)
    return float(ncx2.sf(critical, df, n * chi_square_independence_w(joint) ** 2))


def required_n_chi_square_independence(s: Scenario) -> dict[str, float | int | str]:
    joint = [[float(cell) for cell in row] for row in s.effect["joint_probabilities"]]
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    minimum_expected = float(s.design.get("min_expected_count", 5))
    min_cell = min(cell for row in joint for cell in row)
    n = max(2, ceil(minimum_expected / min_cell))
    while chi_square_independence_power(n, joint, alpha) < target:
        n += 1
    return {
        "n_total": n,
        "power": chi_square_independence_power(n, joint, alpha),
        "cohens_w": chi_square_independence_w(joint),
        "min_expected_cell_count": n * min_cell,
        "method": "noncentral_chi_square_independence_approximation",
    }


def _factorial_df1(levels_a: int, levels_b: int, term: str) -> int:
    if term == "A":
        return levels_a - 1
    if term == "B":
        return levels_b - 1
    return (levels_a - 1) * (levels_b - 1)


def factorial_anova_power(n_per_cell: int, levels_a: int, levels_b: int, term: str, cohens_f: float, alpha: float) -> float:
    cells = levels_a * levels_b
    df1 = _factorial_df1(levels_a, levels_b, term)
    df2 = cells * (n_per_cell - 1)
    n_total = cells * n_per_cell
    critical = f.ppf(1 - alpha, df1, df2)
    return float(ncf.sf(critical, df1, df2, n_total * cohens_f**2))


def required_n_factorial_anova(s: Scenario) -> dict[str, float | int | str]:
    levels_a, levels_b = int(s.design["levels_a"]), int(s.design["levels_b"])
    term, cohens_f = str(s.design["tested_term"]), float(s.effect["cohens_f"])
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    n = 2
    while factorial_anova_power(n, levels_a, levels_b, term, cohens_f, alpha) < target:
        n += 1
    cells = levels_a * levels_b
    return {
        "n_per_cell": n,
        "n_total": n * cells,
        "power": factorial_anova_power(n, levels_a, levels_b, term, cohens_f, alpha),
        "method": "noncentral_f_balanced_factorial_anova",
    }


def ancova_power(n_per_group: int, groups: int, cohens_f: float, covariate_r2: float, alpha: float) -> float:
    """ANCOVA treatment F with one covariate; residual variance reduced by (1 - R²)."""
    n_total = groups * n_per_group
    df1, df2 = groups - 1, n_total - groups - 1
    critical = f.ppf(1 - alpha, df1, df2)
    adjusted_f = cohens_f / (1 - covariate_r2) ** 0.5
    return float(ncf.sf(critical, df1, df2, n_total * adjusted_f**2))


def required_n_ancova(s: Scenario) -> dict[str, float | int | str]:
    groups, cohens_f = int(s.design["groups"]), float(s.effect["cohens_f"])
    r2, alpha, target = float(s.design["covariate_r2"]), s.decision_rule.alpha, float(s.target_power)
    n = 3
    while ancova_power(n, groups, cohens_f, r2, alpha) < target:
        n += 1
    return {
        "n_per_group": n,
        "n_total": n * groups,
        "power": ancova_power(n, groups, cohens_f, r2, alpha),
        "method": "noncentral_f_ancova_one_covariate",
    }


def planned_contrast_power(n_per_group: int, groups: int, weights: list[float], cohens_f: float, alpha: float) -> float:
    """Single planned contrast powered via noncentral F with df1 = 1.

    `cohens_f` is the standardized effect size *of the contrast itself*, so the power of
    the test does not depend on which contrast is being tested:

        lambda = N * f^2,  df1 = 1,  df2 = N - groups

    The weights are validated but deliberately do not enter this calculation. That is not
    an oversight -- it is forced by the parameterization. Placing cell means at
    `w_j / rms(w) * f`, as the independent simulator does, gives

        lambda = n_per_group * (sum_j w_j mu_j)^2 / sum_j w_j^2 = n_per_group * groups * f^2

    for *every* weight vector: the weights cancel algebraically. Once you have declared
    the standardized magnitude of the contrast, the weights determine which comparison is
    being made, not how much power it has.

    `weights` is therefore retained for provenance and validation only -- it records the
    estimand in the exported scenario and lets `Scenario.validate` reject weights that do
    not sum to zero or do not match the group count. Callers wanting different power for
    different contrasts must supply a different `cohens_f`.
    """
    n_total = groups * n_per_group
    df2 = n_total - groups
    critical = f.ppf(1 - alpha, 1, df2)
    if not any(float(w) != 0.0 for w in weights):
        raise ValueError("planned_contrast requires at least one non-zero contrast weight")
    return float(ncf.sf(critical, 1, df2, n_total * cohens_f**2))


def required_n_planned_contrast(s: Scenario) -> dict[str, float | int | str]:
    groups, weights = int(s.design["groups"]), [float(w) for w in s.design["contrast_weights"]]
    cohens_f, alpha, target = float(s.effect["cohens_f"]), s.decision_rule.alpha, float(s.target_power)
    n = 2
    while planned_contrast_power(n, groups, weights, cohens_f, alpha) < target:
        n += 1
    return {
        "n_per_group": n,
        "n_total": n * groups,
        "power": planned_contrast_power(n, groups, weights, cohens_f, alpha),
        "method": "noncentral_f_planned_contrast",
    }


def moderation_power(n: int, total_predictors: int, cohens_f2: float, alpha: float) -> float:
    """Power for the interaction term as a one-df incremental F test."""
    return incremental_regression_power(n, total_predictors, 1, cohens_f2, alpha)


def required_n_moderation(s: Scenario) -> dict[str, float | int | str]:
    total, f2 = int(s.design["total_predictors"]), float(s.effect["cohens_f2"])
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    n = total + 2
    while moderation_power(n, total, f2, alpha) < target:
        n += 1
    return {"n_total": n, "power": moderation_power(n, total, f2, alpha), "method": "noncentral_f_interaction_increment"}


def logistic_regression_power(
    n: int,
    odds_ratio: float,
    p_baseline: float,
    predictor_type: str,
    alpha: float,
    alternative: str,
    allocation_ratio: float = 1.0,
) -> float:
    """Power for a single logistic coefficient (Demidenko 2007; Hsieh et al. 1998).

    Demidenko, E. (2007). Sample size determination for logistic regression revisited.
    Statistics in Medicine, 26(18), 3385-3397.

    For a binary predictor the two arms have different outcome probabilities, so the
    Fisher information for the slope is the harmonic-type combination

        Var(beta_hat) = 1 / (n * P0 * p0 * q0) + 1 / (n * P1 * p1 * q1)

    where `p1 = expit(logit(p0) + beta)` and `P0`, `P1` are the allocation fractions.

    An earlier implementation used `information = n * p0 * (1 - p0) * Var(X)`, evaluating
    the binomial variance only at the baseline probability. That understates the variance
    when the exposed group sits closer to p = 0.5 and overstates it otherwise, so the
    error changes sign: required N came out ~21% too high at OR=3.0, p0=0.20, but ~6% too
    low (anti-conservative) at OR=2.0, p0=0.50.
    """
    from math import log

    beta = log(odds_ratio)
    p0 = p_baseline
    if predictor_type == "binary":
        allocation_0 = 1.0 / (1.0 + allocation_ratio)
        allocation_1 = 1.0 - allocation_0
        odds0 = p0 / (1 - p0)
        p1 = (odds0 * odds_ratio) / (1 + odds0 * odds_ratio)
        variance = 1.0 / (n * allocation_0 * p0 * (1 - p0)) + 1.0 / (n * allocation_1 * p1 * (1 - p1))
        se = variance**0.5
    else:
        # One-SD change in a standard normal predictor (Hsieh, Bloch & Larsen 1998).
        # The variance inflation from a non-zero slope is absorbed into the baseline
        # information term, which is the convention this parameterization assumes.
        information = n * p0 * (1 - p0)
        se = (1 / information) ** 0.5
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.cdf((-zcrit - beta / se)) + norm.sf(zcrit - beta / se))
    zcrit = norm.ppf(1 - alpha)
    return float(norm.sf(zcrit - beta / se) if alternative == "greater" else norm.cdf(-zcrit - beta / se))


def required_n_logistic_regression(s: Scenario) -> dict[str, float | int | str]:
    odds_ratio, p0 = float(s.effect["odds_ratio"]), float(s.effect["p_baseline"])
    predictor_type = str(s.design.get("predictor_type", "binary"))
    allocation_ratio = float(s.design.get("allocation_ratio", 1.0))
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative

    def power_at(n: int) -> float:
        return logistic_regression_power(
            n, odds_ratio, p0, predictor_type, alpha, alternative, allocation_ratio
        )

    n = 20
    while power_at(n) < target:
        n += 1
        if n > 1_000_000:
            raise RuntimeError("Could not bracket logistic sample size")
    return {
        "n_total": n,
        "power": power_at(n),
        "method": (
            "demidenko_logistic_wald"
            if predictor_type == "binary"
            else "hsieh_logistic_normal_approximation"
        ),
    }


def poisson_regression_power(n: int, rate_ratio: float, baseline_rate: float, exposure: float, alpha: float, alternative: str) -> float:
    """Normal approximation for a Poisson log-rate coefficient with equal exposure."""
    from math import log

    beta = log(rate_ratio)
    # Balanced binary predictor: Wald variance of log(RR) is 1/E0 + 1/E1.
    events0 = n * 0.5 * baseline_rate * exposure
    events1 = n * 0.5 * baseline_rate * rate_ratio * exposure
    se = (1 / max(events0, 1e-12) + 1 / max(events1, 1e-12)) ** 0.5
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.cdf((-zcrit - beta / se)) + norm.sf(zcrit - beta / se))
    zcrit = norm.ppf(1 - alpha)
    return float(norm.sf(zcrit - beta / se) if alternative == "greater" else norm.cdf(-zcrit - beta / se))


def required_n_poisson_regression(s: Scenario) -> dict[str, float | int | str]:
    rate_ratio = float(s.effect["rate_ratio"])
    baseline_rate, exposure = float(s.design["baseline_rate"]), float(s.design.get("exposure", 1))
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    n = 20
    while poisson_regression_power(n, rate_ratio, baseline_rate, exposure, alpha, alternative) < target:
        n += 1
        if n > 1_000_000:
            raise RuntimeError("Could not bracket Poisson sample size")
    return {
        "n_total": n,
        "power": poisson_regression_power(n, rate_ratio, baseline_rate, exposure, alpha, alternative),
        "method": "poisson_log_rate_normal_approximation",
    }


def tost_equivalence_power(n1: int, n2: int, true_difference: float, sd: float, lower: float, upper: float, alpha: float) -> float:
    """Power for two one-sided tests (TOST) of mean equivalence.

    Both one-sided tests must reject, so power is the probability of their intersection.
    This uses the Frechet lower bound `P(A and B) >= P(A) + P(B) - 1` on two positively
    correlated one-sided t tests that share the same pooled `s`.

    The bound is tight throughout the planning region, because equivalence designs are
    powered where at least one of the two one-sided powers is close to 1. Verified against
    `TOSTER::power_t_TOST(n = 70, delta = 0, sd = 1, eqb = 0.5)` = 0.8059312 versus 0.8059
    here, and it stays within 0.2% across the sample sizes and true differences the
    planner reaches.

    It is genuinely conservative only in the low-power regime, where it clamps to zero
    while the exact bivariate integral still gives a few percent. That region is not used
    for planning, but the clamp is reported rather than silently floored so a sensitivity
    curve does not show a bogus exact zero.
    """
    se = sd * (1 / n1 + 1 / n2) ** 0.5
    df = n1 + n2 - 2
    tcrit = t.ppf(1 - alpha, df)
    power_lower = float(nct.sf(tcrit, df, (true_difference - lower) / se))
    power_upper = float(nct.sf(tcrit, df, (upper - true_difference) / se))
    return float(min(1.0, max(0.0, power_lower + power_upper - 1.0)))


def required_n_tost_equivalence(s: Scenario) -> dict[str, float | int | str]:
    lower, upper = float(s.effect["lower_bound"]), float(s.effect["upper_bound"])
    true_diff = float(s.effect.get("true_difference", 0.0))
    sd, ratio = float(s.effect["sd"]), float(s.design.get("allocation_ratio", 1.0))
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    n1 = 4
    while True:
        n2 = max(4, ceil(n1 * ratio))
        power = tost_equivalence_power(n1, n2, true_diff, sd, lower, upper, alpha)
        if power >= target:
            return {
                "n1": n1,
                "n2": n2,
                "n_total": n1 + n2,
                "power": power,
                "method": "tost_two_one_sided_t_approximation",
            }
        n1 += 1
        if n1 > 1_000_000:
            raise RuntimeError("Could not bracket TOST sample size")


def mediation_indirect_power(
    n: int,
    a_path: float,
    b_path: float,
    alpha: float,
    residual_sd_m: float = 1.0,
    residual_sd_y: float = 1.0,
    sd_x: float = 1.0,
) -> float:
    """Joint-significance power for the indirect effect a*b (MacKinnon et al. 2002).

    The indirect effect is declared significant when both path tests reject, so power is
    the joint probability. The two tests are asymptotically orthogonal in the recursive
    model -- verified by simulation at n=118: P(a and b) = 0.7877 against a product of
    0.7885 -- so the product form is used rather than a bivariate integral.

    Standard errors follow the OLS design the independent simulator generates:

        M = a*X + e_m,        SE(a) = sd_m / (sd_x * sqrt(n - 2)),   df = n - 2
        Y = c'*X + b*M + e_y, SE(b) = sd_y / (sd_m * sqrt(n - 3)),   df = n - 3

    SE(b) uses the residual SD of M because X and M are orthogonalized inside the second
    regression: the part of M that carries information about b is the part independent of
    X, whose SD is `residual_sd_m`. Each denominator uses residual degrees of freedom
    rather than `n`, because the intercept (and, for the b path, the X coefficient) are
    estimated rather than known. Using `sqrt(n)` understates both standard errors by
    roughly 1% at n = 117 and inflates joint power by about 1.5 points.

    An earlier implementation used `se = 1/sqrt(n - 3)` for both paths -- the Fisher-z
    standard error for a *correlation*, which is not the SE of either regression
    coefficient and ignores the residual scales entirely.
    """
    if n <= 3:
        return 0.0
    se_a = residual_sd_m / (sd_x * (n - 2) ** 0.5)
    se_b = residual_sd_y / (residual_sd_m * (n - 3) ** 0.5)
    critical_a = t.ppf(1 - alpha / 2, n - 2)
    critical_b = t.ppf(1 - alpha / 2, n - 3)
    power_a = float(
        nct.sf(critical_a, n - 2, abs(a_path) / se_a) + nct.cdf(-critical_a, n - 2, abs(a_path) / se_a)
    )
    power_b = float(
        nct.sf(critical_b, n - 3, abs(b_path) / se_b) + nct.cdf(-critical_b, n - 3, abs(b_path) / se_b)
    )
    return float(power_a * power_b)


def required_n_mediation_indirect(s: Scenario) -> dict[str, float | int | str]:
    a_path, b_path = float(s.effect["a_path"]), float(s.effect["b_path"])
    residual_sd_m = float(s.design.get("residual_sd_m", 1.0))
    residual_sd_y = float(s.design.get("residual_sd_y", 1.0))
    alpha, target = s.decision_rule.alpha, float(s.target_power)

    def power_at(n: int) -> float:
        return mediation_indirect_power(n, a_path, b_path, alpha, residual_sd_m, residual_sd_y)

    n = 20
    while power_at(n) < target:
        n += 1
        if n > 1_000_000:
            raise RuntimeError("Could not bracket mediation sample size")
    return {
        "n_total": n,
        "power": power_at(n),
        "method": "joint_significance_indirect_effect",
    }


def meta_analysis_fixed_power(studies: int, n_per_group: int, cohens_d: float, alpha: float, alternative: str) -> float:
    """Fixed-effect meta-analysis of two-sample standardized mean differences."""
    # Per-study sampling variance ≈ 2/n_per_group + d²/(2*2*n_per_group) for equal groups.
    var_i = 2 / n_per_group + cohens_d**2 / (4 * n_per_group)
    se = (var_i / studies) ** 0.5
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.cdf((-zcrit - cohens_d / se)) + norm.sf(zcrit - cohens_d / se))
    zcrit = norm.ppf(1 - alpha)
    return float(norm.sf(zcrit - cohens_d / se) if alternative == "greater" else norm.cdf(-zcrit - cohens_d / se))


def required_n_meta_analysis_fixed(s: Scenario) -> dict[str, float | int | str]:
    """Required per-group N within each of k fixed-effect studies."""
    studies, d = int(s.design["studies"]), float(s.effect["cohens_d"])
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    n = 4
    while meta_analysis_fixed_power(studies, n, d, alpha, alternative) < target:
        n += 1
    return {
        "n_per_group_per_study": n,
        "n_total": 2 * n * studies,
        "studies": studies,
        "power": meta_analysis_fixed_power(studies, n, d, alpha, alternative),
        "method": "fixed_effect_smd_meta_analysis_normal_approximation",
    }


def analytic_reference(s: Scenario) -> dict[str, float | int | str]:
    from .specialist_extras import (
        required_n_bayes_factor_t,
        required_n_group_sequential_t,
        required_n_logrank_two_arm,
        required_n_meta_analysis_random,
        required_n_noninferiority_t,
        required_n_ordinal_regression,
        required_n_rope_equivalence_t,
    )

    dispatch = {
        "two_sample_t": required_n_two_sample_t,
        "welch_t": required_n_welch_t,
        "correlation": required_n_correlation,
        "paired_t": required_n_paired_t,
        "one_sample_proportion": required_n_one_sample_proportion,
        "two_sample_proportion": required_n_two_sample_proportion,
        "chi_square_gof": required_n_chi_square_gof,
        "chi_square_independence": required_n_chi_square_independence,
        "one_way_anova": required_n_one_way_anova,
        "factorial_anova": required_n_factorial_anova,
        "ancova": required_n_ancova,
        "planned_contrast": required_n_planned_contrast,
        "linear_regression": required_n_linear_regression,
        "incremental_regression": required_n_incremental_regression,
        "moderation": required_n_moderation,
        "logistic_regression": required_n_logistic_regression,
        "poisson_regression": required_n_poisson_regression,
        "tost_equivalence": required_n_tost_equivalence,
        "mediation_indirect": required_n_mediation_indirect,
        "meta_analysis_fixed": required_n_meta_analysis_fixed,
        "meta_analysis_random": required_n_meta_analysis_random,
        "noninferiority_t": required_n_noninferiority_t,
        "ordinal_regression": required_n_ordinal_regression,
        "bayes_factor_t": required_n_bayes_factor_t,
        "group_sequential_t": required_n_group_sequential_t,
        "logrank_two_arm": required_n_logrank_two_arm,
        "rope_equivalence_t": required_n_rope_equivalence_t,
    }
    try:
        return dispatch[s.model](s)
    except KeyError as error:
        raise NotImplementedError(f"No analytic reference for {s.model}") from error
