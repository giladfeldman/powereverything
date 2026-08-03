"""Specialist extras: ordinal, Bayes-factor t (JZS/BIC), group-sequential, random-effects meta, non-inferiority, log-rank, ROPE."""

from __future__ import annotations

from math import ceil, exp, log
from typing import Any

import numpy as np
from scipy.optimize import brentq
from scipy.stats import cauchy, multivariate_normal, nct, norm, t as student_t

from .schema import Scenario
from .references import required_n_two_sample_t, two_sample_t_power


def equally_spaced_latent_category_probs(categories: int) -> list[float]:
    """Control-arm category probabilities implied by equally spaced logistic thresholds.

    The independent simulator generates ordinal outcomes by cutting a standard logistic
    latent variable at `np.linspace(-1, 1, categories - 1)`. The analytic reference must
    describe that same data-generating process, so the default marginal distribution is
    derived from those cut points rather than assumed uniform.
    """
    if categories < 3:
        raise ValueError("ordinal_regression requires at least three ordered categories")
    cuts = [-1.0 + 2.0 * index / (categories - 2) for index in range(categories - 1)] if categories > 2 else []
    cumulative = [1.0 / (1.0 + exp(-cut)) for cut in cuts]
    probs, previous = [], 0.0
    for value in cumulative:
        probs.append(value - previous)
        previous = value
    probs.append(1.0 - previous)
    return probs


def ordinal_proportional_odds_power(
    n: int,
    odds_ratio: float,
    categories: int,
    alpha: float,
    alternative: str,
    allocation_ratio: float = 1.0,
    baseline_category_probs: list[float] | None = None,
) -> float:
    """Whitehead (1993) proportional-odds power for a binary predictor.

    Whitehead, J. (1993). Sample size calculations for ordered categorical data.
    Statistics in Medicine, 12(24), 2257-2271. The asymptotic variance of the log odds
    ratio is

        Var(beta) = 3 / (n * (1 - sum_j pbar_j^3) * P1 * P2)

    where `pbar_j` are the allocation-weighted marginal category probabilities and
    `P1`, `P2` are the arm allocation fractions.

    The `(1 - sum_j pbar_j^3)` term is what makes this a genuinely *ordinal* calculation:
    it shrinks toward zero as the outcome concentrates in one category, inflating the
    required sample size. An earlier implementation used a flat `Var = 4/n`, which is
    independent of the category distribution and under-powered ordinal designs roughly
    threefold (N = 191 where this formula gives ~614 for a four-category outcome).
    """
    beta = log(odds_ratio)
    p_control = list(baseline_category_probs) if baseline_category_probs else equally_spaced_latent_category_probs(categories)

    allocation_1 = 1.0 / (1.0 + allocation_ratio)
    allocation_2 = 1.0 - allocation_1

    # Treatment-arm probabilities under proportional odds: shift the cumulative logits by
    # beta, so the two arms share one odds ratio across every cut point.
    cumulative_control, running = [], 0.0
    for probability in p_control[:-1]:
        running += probability
        cumulative_control.append(min(max(running, 1e-12), 1 - 1e-12))
    cumulative_treated = [1.0 / (1.0 + exp(-(log(c / (1 - c)) + beta))) for c in cumulative_control]

    p_treated, previous = [], 0.0
    for value in cumulative_treated:
        p_treated.append(value - previous)
        previous = value
    p_treated.append(1.0 - previous)

    pooled = [allocation_1 * a + allocation_2 * b for a, b in zip(p_control, p_treated)]
    spread = 1.0 - sum(p**3 for p in pooled)
    if spread <= 0:
        raise ValueError("ordinal_regression category probabilities leave no residual variance")

    variance = 3.0 / (n * spread * allocation_1 * allocation_2)
    se = variance**0.5
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.cdf((-zcrit - beta / se)) + norm.sf(zcrit - beta / se))
    zcrit = norm.ppf(1 - alpha)
    return float(norm.sf(zcrit - beta / se) if alternative == "greater" else norm.cdf(-zcrit - beta / se))


def required_n_ordinal_regression(s: Scenario) -> dict[str, float | int | str]:
    odds_ratio = float(s.effect["odds_ratio"])
    categories = int(s.design["categories"])
    allocation_ratio = float(s.design.get("allocation_ratio", 1.0))
    baseline = s.effect.get("baseline_category_probs")
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative

    def power_at(n: int) -> float:
        return ordinal_proportional_odds_power(
            n, odds_ratio, categories, alpha, alternative, allocation_ratio, baseline
        )

    n = 20
    while power_at(n) < target:
        n += 1
        if n > 1_000_000:
            raise RuntimeError("Could not bracket ordinal sample size")
    return {
        "n_total": n,
        "power": power_at(n),
        "categories": categories,
        "method": "whitehead_proportional_odds",
    }


def bic_bf10_from_t(tstat: float, n_total: int) -> float:
    """BIC/unit-information style BF10 from a two-sample t statistic."""
    return float(exp(0.5 * (tstat**2 - log(n_total))))


def jzs_bf10_from_t(tstat: float, n1: int, n2: int, r_scale: float = 0.7071) -> float:
    """Rouder et al. (2009) JZS Bayes factor via Cauchy prior on δ (fixed-node quadrature)."""
    tstat = float(np.clip(tstat, -40.0, 40.0))
    nu = n1 + n2 - 2
    n_eff = n1 * n2 / (n1 + n2)
    m0 = float(student_t.pdf(tstat, nu))
    if m0 <= 0 or not np.isfinite(m0):
        return float("inf")
    # Equally spaced probability nodes under the Cauchy prior (fast, stable alternative to adaptive quad).
    probs = np.linspace(0.02, 0.98, 41)
    deltas = cauchy.ppf(probs, 0, r_scale)
    weights = np.full(deltas.shape, 1.0 / len(deltas))
    ncps = np.clip(deltas * (n_eff**0.5), -40.0, 40.0)
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            densities = nct.pdf(tstat, nu, ncps)
    except OverflowError:
        densities = np.zeros_like(ncps, dtype=float)
    densities = np.nan_to_num(densities, nan=0.0, posinf=0.0, neginf=0.0)
    m1 = float(np.sum(weights * densities))
    if m1 <= 0 or not np.isfinite(m1):
        return 0.0
    return float(m1 / m0)


_CRITICAL_T_CACHE: dict[tuple[int, int, float, str, float], float] = {}


def _critical_t_for_bf(n1: int, n2: int, bf_threshold: float, method: str, r_scale: float) -> float:
    """Smallest |t| such that BF10(t) >= threshold (two-sided symmetric)."""
    key = (n1, n2, float(bf_threshold), method, float(r_scale))
    if key in _CRITICAL_T_CACHE:
        return _CRITICAL_T_CACHE[key]
    n_total = n1 + n2

    def bf(tstat: float) -> float:
        if method == "jzs":
            return jzs_bf10_from_t(tstat, n1, n2, r_scale)
        return bic_bf10_from_t(tstat, n_total)

    if bf(0.0) >= bf_threshold:
        _CRITICAL_T_CACHE[key] = 0.0
        return 0.0
    # Warm-start from the closed-form BIC critical value when using JZS.
    hi = max(2.0, (2 * log(bf_threshold) + log(n_total)) ** 0.5 + 1.0)
    while bf(hi) < bf_threshold:
        hi *= 1.4
        if hi > 200:
            _CRITICAL_T_CACHE[key] = hi
            return hi
    value = float(brentq(lambda tstat: bf(tstat) - bf_threshold, 0.0, hi, xtol=1e-3, maxiter=40))
    _CRITICAL_T_CACHE[key] = value
    return value


def bayes_factor_t_power(
    n1: int,
    n2: int,
    cohens_d: float,
    bf_threshold: float,
    method: str = "jzs",
    r_scale: float = 0.7071,
) -> float:
    """Approximate P(BF10 >= threshold) under the alternative for a two-sample design."""
    df = n1 + n2 - 2
    ncp = cohens_d / (1 / n1 + 1 / n2) ** 0.5
    critical = _critical_t_for_bf(n1, n2, bf_threshold, method, r_scale)
    return float(nct.sf(critical, df, ncp) + nct.cdf(-critical, df, ncp))


def required_n_bayes_factor_t(s: Scenario) -> dict[str, float | int | str]:
    d = float(s.effect["cohens_d"])
    threshold = float(s.design.get("bf_threshold", 3))
    ratio = float(s.design.get("allocation_ratio", 1.0))
    method = str(s.design.get("bf_method", "jzs")).lower()
    r_scale = float(s.design.get("r_scale", 0.7071))
    target = float(s.target_power)
    # Binary search on n1; JZS critical-t evaluations are expensive.
    low, high = 10, 40
    while True:
        n2 = max(10, ceil(high * ratio))
        if bayes_factor_t_power(high, n2, d, threshold, method, r_scale) >= target:
            break
        low, high = high, high * 2
        if high > 1_000_000:
            raise RuntimeError("Could not bracket Bayes-factor sample size")
    while low + 1 < high:
        mid = (low + high) // 2
        n2 = max(10, ceil(mid * ratio))
        if bayes_factor_t_power(mid, n2, d, threshold, method, r_scale) >= target:
            high = mid
        else:
            low = mid
    n1 = high
    n2 = max(10, ceil(n1 * ratio))
    power = bayes_factor_t_power(n1, n2, d, threshold, method, r_scale)
    critical = _critical_t_for_bf(n1, n2, threshold, method, r_scale)
    label = "jzs_cauchy_prior_design_analysis" if method == "jzs" else "bic_approximated_bf10_design_analysis"
    return {
        "n1": n1,
        "n2": n2,
        "n_total": n1 + n2,
        "power": power,
        "bf_method": method,
        "r_scale": r_scale,
        "bf_threshold": threshold,
        "critical_t": float(critical),
        "degrees_freedom": int(n1 + n2 - 2),
        "method": label,
    }


def obrien_fleming_spending(information_fraction: float, alpha: float) -> float:
    """Lan-DeMets O'Brien-Fleming alpha-spending function.

    alpha*(t) = 2 * (1 - Phi(z_{alpha/2} / sqrt(t)))  for a two-sided test.
    """
    t_fraction = min(max(float(information_fraction), 1e-9), 1.0)
    return float(2.0 * norm.sf(norm.ppf(1 - alpha / 2) / t_fraction**0.5))


_BOUNDARY_CACHE: dict[tuple[int, float, str], list[float]] = {}


def group_sequential_boundaries(looks: int, alpha: float, alternative: str = "two.sided") -> list[float]:
    """Efficacy boundaries for equally spaced looks under Lan-DeMets OBF spending.

    Boundaries are solved sequentially so the cumulative type I error matches the spending
    function exactly at each look, and the total is exactly `alpha`. This replaces a
    hardcoded five-entry inflation table that was insensitive to alpha, target power and
    alternative, and raised `ValueError` beyond five looks.

    The naive `z_crit / sqrt(t)` shortcut used previously by the simulator is not a valid
    boundary: at two looks and alpha = 0.05 it spends about 0.052.
    """
    if looks < 1:
        raise ValueError("group_sequential_t requires at least one look")

    # Boundaries depend only on (looks, alpha, alternative) and each solve runs brentq
    # over multivariate-normal CDFs, so cache them: the required-N search calls this once
    # per candidate N, and the simulator once per plan.
    cache_key = (looks, float(alpha), alternative)
    if cache_key in _BOUNDARY_CACHE:
        return list(_BOUNDARY_CACHE[cache_key])

    two_sided = alternative == "two.sided"
    working_alpha = alpha if two_sided else 2.0 * alpha

    fractions = [(index + 1) / looks for index in range(looks)]
    # Cov(Z_i, Z_j) = sqrt(t_i / t_j) for i <= j.
    covariance = np.array([[(min(a, b) / max(a, b)) ** 0.5 for b in fractions] for a in fractions])

    boundaries: list[float] = []
    spent = 0.0
    for index, fraction in enumerate(fractions):
        target_cumulative = obrien_fleming_spending(fraction, working_alpha)
        increment = max(target_cumulative - spent, 1e-12)

        def exit_probability(bound: float, index=index) -> float:
            """P(continue through all earlier looks, then cross at this look) under H0."""
            if index == 0:
                return float(2.0 * norm.sf(bound))
            lower = [-b for b in boundaries[:index]]
            upper = list(boundaries[:index])
            block = covariance[: index + 1, : index + 1]
            # P(|Z_j| < b_j for j < index) minus P(|Z_j| < b_j for j <= index)
            continue_before = float(
                multivariate_normal.cdf(
                    np.array(upper), mean=np.zeros(index), cov=block[:index, :index], lower_limit=np.array(lower)
                )
            )
            continue_through = float(
                multivariate_normal.cdf(
                    np.array(upper + [bound]),
                    mean=np.zeros(index + 1),
                    cov=block,
                    lower_limit=np.array(lower + [-bound]),
                )
            )
            return continue_before - continue_through

        try:
            bound = float(brentq(lambda b: exit_probability(b) - increment, 0.5, 12.0, xtol=1e-6, maxiter=100))
        except ValueError:
            bound = float(norm.ppf(1 - increment / 2))
        boundaries.append(bound)
        spent = target_cumulative
    _BOUNDARY_CACHE[cache_key] = list(boundaries)
    return boundaries


def group_sequential_power(n_per_arm_final: int, cohens_d: float, looks: int, alpha: float, alternative: str) -> float:
    """Sequential power: probability of crossing an efficacy boundary at any look.

    Computed as 1 - P(no boundary crossed at any look) under the alternative, using the
    joint normal distribution of the sequence of test statistics with
    Cov(Z_i, Z_j) = sqrt(t_i / t_j).
    """
    boundaries = group_sequential_boundaries(looks, alpha, alternative)
    fractions = [(index + 1) / looks for index in range(looks)]
    covariance = np.array([[(min(a, b) / max(a, b)) ** 0.5 for b in fractions] for a in fractions])
    # Z_i has mean d * sqrt(n_i / 2) for a balanced two-arm comparison at look i.
    means = np.array([cohens_d * (n_per_arm_final * fraction / 2.0) ** 0.5 for fraction in fractions])

    if alternative == "two.sided":
        lower = np.array([-b for b in boundaries])
        upper = np.array(boundaries)
    elif alternative == "greater":
        lower = np.full(looks, -np.inf)
        upper = np.array(boundaries)
    else:
        lower = np.array([-b for b in boundaries])
        upper = np.full(looks, np.inf)

    continue_all = float(multivariate_normal.cdf(upper, mean=means, cov=covariance, lower_limit=lower))
    return float(min(1.0, max(0.0, 1.0 - continue_all)))


def required_n_group_sequential_t(s: Scenario) -> dict[str, float | int | str]:
    looks = int(s.design.get("looks", 2))
    d = float(s.effect["cohens_d"])
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    fixed = required_n_two_sample_t(s)

    # Search on the final per-arm sample size for the *sequential* operating
    # characteristic. An earlier implementation inflated the fixed-design N by a
    # hardcoded factor and then reported `two_sample_t_power` at that N -- the
    # fixed-design power of a single final test, which is not the power of a sequential
    # design and does not account for the interim looks at all.
    n_per_arm = max(2, ceil(int(fixed["n_total"]) / 2))
    while group_sequential_power(n_per_arm, d, looks, alpha, alternative) < target:
        n_per_arm += 1
        if n_per_arm > 1_000_000:
            raise RuntimeError("Could not bracket group-sequential sample size")

    n1 = n2 = n_per_arm
    boundaries = group_sequential_boundaries(looks, alpha, alternative)
    return {
        "n1": n1,
        "n2": n2,
        "n_total": n1 + n2,
        "power": group_sequential_power(n_per_arm, d, looks, alpha, alternative),
        "fixed_n_total": fixed["n_total"],
        "inflation_factor": float((n1 + n2) / int(fixed["n_total"])),
        "looks": looks,
        "efficacy_boundaries": [round(b, 6) for b in boundaries],
        "method": "lan_demets_obrien_fleming_sequential",
    }


def _meta_random_se(studies: int, n_per_group: int, cohens_d: float, tau: float) -> float:
    var_i = 2 / n_per_group + cohens_d**2 / (4 * n_per_group)
    weight = 1 / (var_i + tau**2)
    return (1 / (studies * weight)) ** 0.5


def _meta_hk_critical(studies: int, alpha: float, alternative: str) -> tuple[float, bool]:
    """Hartung-Knapp t critical with df = studies - 1 when studies > 2; otherwise z.

    Hartung & Knapp (2001), Statistics in Medicine 20(24), 3875-3889; IntHout, Ioannidis &
    Borm (2014), BMC Medical Research Methodology 14:25. The standard HK reference
    distribution is t with k - 1 degrees of freedom. An earlier implementation used k - 2,
    which is not the published convention and made the test slightly conservative.
    """
    use_hk = studies > 2
    if use_hk:
        df = studies - 1
        if alternative == "two.sided":
            return float(student_t.ppf(1 - alpha / 2, df)), True
        return float(student_t.ppf(1 - alpha, df)), True
    if alternative == "two.sided":
        return float(norm.ppf(1 - alpha / 2)), False
    return float(norm.ppf(1 - alpha)), False


def meta_analysis_random_power(
    studies: int,
    n_per_group: int,
    cohens_d: float,
    tau: float,
    alpha: float,
    alternative: str,
) -> float:
    """Random-effects meta-analysis power for a common mean SMD with between-study SD tau.

    Implements the Hartung-Knapp adjustment properly. HK rescales the summary variance by

        q = sum_i w_i (y_i - mu_hat)^2 / ((k - 1) * sum_i w_i)

    and refers `mu_hat / (sqrt(q) * sqrt(1 / sum_i w_i))` to a t distribution with k - 1
    degrees of freedom. Under the random-effects model `q` is distributed as
    chi-square_{k-1} / (k - 1), independent of `mu_hat`, so the test statistic is
    non-central t with noncentrality `d / se` and df `k - 1`. Power is therefore the
    non-central t tail, computed here in closed form.

    Two earlier defects are corrected here and must be fixed together, because they
    offset: the implementation took an HK *t* critical value but evaluated the rejection
    probability under a *normal* sampling distribution (a hybrid corresponding to no
    actual test), and omitted the `q` rescaling entirely. Correcting only one made the
    answer worse than correcting neither.
    """
    se = _meta_random_se(studies, n_per_group, cohens_d, tau)
    crit, use_hk = _meta_hk_critical(studies, alpha, alternative)
    noncentrality = cohens_d / se
    if not use_hk:
        # Too few studies for the HK variance estimate; fall back to the normal reference.
        if alternative == "two.sided":
            return float(norm.cdf(-crit - noncentrality) + norm.sf(crit - noncentrality))
        return float(norm.sf(crit - noncentrality) if alternative == "greater" else norm.cdf(-crit - noncentrality))

    df = studies - 1
    if alternative == "two.sided":
        return float(nct.sf(crit, df, noncentrality) + nct.cdf(-crit, df, noncentrality))
    if alternative == "greater":
        return float(nct.sf(crit, df, noncentrality))
    return float(nct.cdf(-crit, df, noncentrality))


def required_n_meta_analysis_random(s: Scenario) -> dict[str, Any]:
    studies, d = int(s.design["studies"]), float(s.effect["cohens_d"])
    tau = float(s.design.get("tau", 0.2))
    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    # As n→∞, se → tau/√k; if that asymptotic power is below target, no finite N exists.
    asymptotic = meta_analysis_random_power(studies, 10_000_000, d, tau, alpha, alternative)
    if asymptotic < target:
        raise ValueError(
            f"With tau={tau} and {studies} studies, asymptotic random-effects power is "
            f"{asymptotic:.3f}, below the target {target}. Reduce tau, add studies, or lower target power."
        )
    n = 4
    while meta_analysis_random_power(studies, n, d, tau, alpha, alternative) < target:
        n += 1
        if n > 1_000_000:
            raise RuntimeError("Could not bracket random-effects meta sample size")
    power = meta_analysis_random_power(studies, n, d, tau, alpha, alternative)
    se = _meta_random_se(studies, n, d, tau)
    _, use_hk = _meta_hk_critical(studies, alpha, alternative)
    # 95% prediction interval for a new study's true effect under the RE model.
    df_pi = max(studies - 2, 1)
    t_pi = float(student_t.ppf(0.975, df_pi)) if studies > 2 else float(norm.ppf(0.975))
    pi_half = t_pi * (se**2 + tau**2) ** 0.5
    return {
        "n_per_group_per_study": n,
        "n_total": 2 * n * studies,
        "studies": studies,
        "tau": tau,
        "power": power,
        "hartung_knapp": use_hk,
        "prediction_interval_95": [float(d - pi_half), float(d + pi_half)],
        "method": "random_effects_smd_meta_analysis_hartung_knapp_t",
    }


def noninferiority_t_power(
    n1: int,
    n2: int,
    true_difference: float,
    sd: float,
    margin: float,
    alpha: float,
) -> float:
    """One-sided non-inferiority power: reject H0: delta <= -margin when true delta = true_difference."""
    se = sd * (1 / n1 + 1 / n2) ** 0.5
    df = n1 + n2 - 2
    tcrit = student_t.ppf(1 - alpha, df)
    ncp = (true_difference + margin) / se
    return float(nct.sf(tcrit, df, ncp))


def required_n_noninferiority_t(s: Scenario) -> dict[str, Any]:
    margin = float(s.effect["margin"])
    true_diff = float(s.effect.get("true_difference", 0.0))
    sd = float(s.effect["sd"])
    ratio = float(s.design.get("allocation_ratio", 1.0))
    alpha, target = s.decision_rule.alpha, float(s.target_power)
    n1 = 4
    while True:
        n2 = max(4, ceil(n1 * ratio))
        power = noninferiority_t_power(n1, n2, true_diff, sd, margin, alpha)
        if power >= target:
            return {
                "n1": n1,
                "n2": n2,
                "n_total": n1 + n2,
                "power": power,
                "method": "one_sided_noninferiority_t_approximation",
            }
        n1 += 1
        if n1 > 1_000_000:
            raise RuntimeError("Could not bracket non-inferiority sample size")


def schoenfeld_events(hazard_ratio: float, alpha: float, power: float, allocation_ratio: float, alternative: str) -> float:
    """Schoenfeld required-events formula for a two-arm log-rank test."""
    ratio = float(allocation_ratio)
    p1, p2 = 1 / (1 + ratio), ratio / (1 + ratio)
    z_alpha = norm.ppf(1 - alpha / 2) if alternative == "two.sided" else norm.ppf(1 - alpha)
    z_power = norm.ppf(power)
    return float((z_alpha + z_power) ** 2 / (p1 * p2 * (log(hazard_ratio) ** 2)))


def expected_event_probability_exponential(
    hazard_rate: float,
    accrual_years: float,
    followup_years: float,
    dropout_hazard: float = 0.0,
) -> float:
    """Expected event probability with uniform accrual and administrative censoring."""
    lam = float(hazard_rate)
    mu = max(0.0, float(dropout_hazard))
    accrual = max(0.0, float(accrual_years))
    followup = max(0.0, float(followup_years))
    total_hazard = lam + mu
    if total_hazard <= 0:
        return 0.0
    if accrual <= 1e-12:
        return float((lam / total_hazard) * (1 - exp(-total_hazard * followup)))
    low = followup
    high = followup + accrual
    mean_survival = (exp(-total_hazard * low) - exp(-total_hazard * high)) / (total_hazard * accrual)
    return float((lam / total_hazard) * (1 - mean_survival))


def logrank_two_arm_power(
    n_total: int,
    hazard_ratio: float,
    p_event: float,
    alpha: float,
    alternative: str,
    allocation_ratio: float = 1.0,
) -> float:
    """Approximate log-rank power from Schoenfeld events under planned event probability."""
    ratio = float(allocation_ratio)
    p1, p2 = 1 / (1 + ratio), ratio / (1 + ratio)
    n_events = n_total * p_event
    if n_events <= 0:
        return 0.0
    se_log_hr = 1 / (n_events * p1 * p2) ** 0.5
    mean = abs(log(hazard_ratio)) / se_log_hr
    if alternative == "two.sided":
        zcrit = norm.ppf(1 - alpha / 2)
        return float(norm.sf(zcrit - mean) + norm.cdf(-zcrit - mean))
    zcrit = norm.ppf(1 - alpha)
    # One-sided direction follows the sign of log(HR).
    signed = log(hazard_ratio) / se_log_hr
    if alternative == "greater":
        return float(norm.sf(zcrit - signed))
    return float(norm.cdf(-zcrit - signed))


def derive_logrank_event_probability(
    hazard_ratio: float,
    control_hazard: float,
    accrual_years: float,
    followup_years: float,
    dropout_hazard: float,
    allocation_ratio: float,
) -> float:
    """Allocation-weighted event probability across both arms under uniform accrual.

    The two arms have different hazards (`control_hazard` and
    `control_hazard * hazard_ratio`), so each has its own event probability under the same
    accrual and censoring plan; the design-level probability is their allocation-weighted
    average.
    """
    allocation_control = 1.0 / (1.0 + allocation_ratio)
    allocation_treated = 1.0 - allocation_control
    p_control = expected_event_probability_exponential(
        control_hazard, accrual_years, followup_years, dropout_hazard
    )
    p_treated = expected_event_probability_exponential(
        control_hazard * hazard_ratio, accrual_years, followup_years, dropout_hazard
    )
    return float(allocation_control * p_control + allocation_treated * p_treated)


def required_n_logrank_two_arm(s: Scenario) -> dict[str, Any]:
    hr = float(s.effect["hazard_ratio"])
    ratio = float(s.design.get("allocation_ratio", 1.0))

    # Prefer deriving the event probability from the accrual/follow-up/dropout plan the
    # scenario already declares (and that `Scenario.validate` already checks). Falling
    # back to a hand-supplied `p_event` keeps older scenarios working, but a design that
    # states its follow-up should not also have to state the implied event probability --
    # `expected_event_probability_exponential` existed for exactly this and had no
    # call sites.
    control_hazard = s.design.get("control_hazard")
    accrual_years = s.design.get("accrual_years")
    followup_years = s.design.get("followup_years")
    if control_hazard is not None and followup_years is not None:
        p_event = derive_logrank_event_probability(
            hr,
            float(control_hazard),
            float(accrual_years or 0.0),
            float(followup_years),
            float(s.design.get("dropout_hazard", 0.0)),
            ratio,
        )
        p_event_source = "derived_from_accrual_followup_dropout"
    else:
        p_event = float(s.effect["p_event"])
        p_event_source = "supplied_in_scenario"
    if not 0 < p_event <= 1:
        raise ValueError(
            f"log-rank event probability must lie in (0, 1]; derived {p_event:.6f}. "
            "Check control_hazard, accrual_years, followup_years, and dropout_hazard."
        )

    alpha, target, alternative = s.decision_rule.alpha, float(s.target_power), s.decision_rule.alternative
    events = schoenfeld_events(hr, alpha, target, ratio, alternative)
    n_total = max(4, ceil(events / p_event))
    # Grow until the discrete N meets target (ceiling may undershoot slightly for one-sided edges).
    while logrank_two_arm_power(n_total, hr, p_event, alpha, alternative, ratio) < target:
        n_total += 1
        if n_total > 1_000_000:
            raise RuntimeError("Could not bracket log-rank sample size")
    n1 = max(2, int(round(n_total / (1 + ratio))))
    n2 = n_total - n1
    if n2 < 2:
        n2, n1 = 2, max(2, n_total - 2)
        n_total = n1 + n2
    return {
        "n1": n1,
        "n2": n2,
        "n_total": n_total,
        "n_events": float(n_total * p_event),
        "p_event": p_event,
        "p_event_source": p_event_source,
        "power": logrank_two_arm_power(n_total, hr, p_event, alpha, alternative, ratio),
        "method": "schoenfeld_logrank_events_then_n_over_p_event",
    }


def rope_posterior_prob(
    observed_diff: float,
    n1: int,
    n2: int,
    sd: float,
    lower: float,
    upper: float,
    prior_sd: float,
    prior_mean: float = 0.0,
) -> float:
    """Normal–normal posterior Prob(lower < delta < upper) for a two-sample mean difference."""
    se2 = sd**2 * (1 / n1 + 1 / n2)
    prior_prec = 1 / prior_sd**2
    like_prec = 1 / se2
    post_var = 1 / (prior_prec + like_prec)
    post_mean = post_var * (prior_prec * prior_mean + like_prec * observed_diff)
    post_sd = post_var**0.5
    return float(norm.cdf(upper, post_mean, post_sd) - norm.cdf(lower, post_mean, post_sd))


def rope_equivalence_t_power(
    n1: int,
    n2: int,
    true_difference: float,
    sd: float,
    lower: float,
    upper: float,
    prior_sd: float,
    threshold: float,
) -> float:
    """Approximate P(posterior ROPE mass >= threshold) under a normal sampling model for the mean difference."""
    se = sd * (1 / n1 + 1 / n2) ** 0.5
    # Integrate over the sampling distribution of the observed mean difference.
    nodes = np.linspace(true_difference - 6 * se, true_difference + 6 * se, 121)
    dens = norm.pdf(nodes, true_difference, se)
    dens = dens / dens.sum()
    probs = np.array([rope_posterior_prob(float(y), n1, n2, sd, lower, upper, prior_sd) for y in nodes])
    return float(np.sum(dens * (probs >= threshold)))


def required_n_rope_equivalence_t(s: Scenario) -> dict[str, Any]:
    lower, upper = float(s.effect["lower_bound"]), float(s.effect["upper_bound"])
    true_diff = float(s.effect.get("true_difference", 0.0))
    sd = float(s.effect["sd"])
    ratio = float(s.design.get("allocation_ratio", 1.0))
    prior_sd = float(s.design.get("prior_sd", 10.0))
    threshold = float(s.design.get("rope_threshold", 0.95))
    target = float(s.target_power)
    n1 = 4
    while True:
        n2 = max(4, ceil(n1 * ratio))
        power = rope_equivalence_t_power(n1, n2, true_diff, sd, lower, upper, prior_sd, threshold)
        if power >= target:
            return {
                "n1": n1,
                "n2": n2,
                "n_total": n1 + n2,
                "power": power,
                "rope_threshold": threshold,
                "prior_sd": prior_sd,
                "method": "bayesian_rope_normal_normal_posterior_probability",
            }
        n1 += 1
        if n1 > 1_000_000:
            raise RuntimeError("Could not bracket ROPE equivalence sample size")
