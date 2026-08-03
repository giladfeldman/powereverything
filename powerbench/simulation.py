"""Independent Monte Carlo estimators and uncertainty metadata."""

from __future__ import annotations

from math import exp, log, sqrt
import numpy as np
from scipy.stats import binomtest, chi2_contingency, chisquare, f as f_distribution, f_oneway, norm, pearsonr, ttest_1samp, ttest_ind

from .schema import Scenario


def _ci95(p: float, n: int) -> tuple[float, float, float]:
    se = sqrt(max(p * (1 - p), 0) / n)
    return se, max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)


def _proportional_odds_wald_z(y: np.ndarray, x: np.ndarray, categories: int) -> float | None:
    """Wald z for the slope of a proportional-odds (cumulative logit) model.

    Fitted by Fisher scoring on the multinomial log-likelihood with analytic derivatives.
    Parameters are the ordered cut points plus the slope; the step is damped and rejected
    if it breaks cut-point monotonicity, which keeps the fit inside the valid region
    without a constrained optimizer.

    Returns `None` when the fit fails to converge or the information matrix is singular,
    so the caller counts a failure rather than recording a spurious rejection.

    This mirrors `MASS::polr(method = "logistic")`. It is deliberately a real ordinal fit
    rather than a binary collapse: the simulator's job is to adjudicate the analytic
    reference, so it must not share the reference's simplifying assumptions.
    """
    n = len(x)
    n_cuts = categories - 1
    if n_cuts < 1:
        return None

    observed = np.asarray(y, dtype=int)
    if observed.min() < 0 or observed.max() > n_cuts:
        return None

    # Start from the empirical cumulative logits with a zero slope.
    counts = np.bincount(observed, minlength=categories).astype(float)
    cumulative_share = np.clip(np.cumsum(counts)[:-1] / n, 1e-6, 1 - 1e-6)
    cuts = np.log(cumulative_share / (1 - cumulative_share))
    beta = 0.0

    for _iteration in range(100):
        eta = cuts[:, None] - beta * x[None, :]              # (n_cuts, n)
        gamma = 1.0 / (1.0 + np.exp(-eta))                   # cumulative probabilities
        padded = np.vstack((np.zeros(n), gamma, np.ones(n)))
        probabilities = np.clip(padded[1:] - padded[:-1], 1e-12, None)
        chosen = probabilities[observed, np.arange(n)]

        # Score and exact observed information (negative Hessian) of the multinomial
        # log-likelihood, accumulated in one pass. An outer-product (BHHH) approximation
        # was measurably looser than MASS::polr here (z differed by up to 0.02), which is
        # too coarse when this simulator is the arbiter for the analytic reference.
        #
        # For observation i in category c the likelihood term is gamma_c - gamma_{c-1},
        # so only cut points c and c-1 contribute.
        # Build the per-observation first and second derivative arrays without a Python
        # loop: each observation touches at most two cut points, so the contributions can
        # be scattered with fancy indexing. (The loop version was ~107 ms per fit at
        # n = 614, which made the alignment gate take over an hour for this scenario
        # alone -- a gate too slow to run is a gate nobody runs.)
        rows = np.arange(n)
        upper_index = observed                     # contributes with sign +1
        lower_index = observed - 1                 # contributes with sign -1
        upper_valid = upper_index < n_cuts
        lower_valid = lower_index >= 0

        d1_upper = np.zeros(n)
        d2_upper = np.zeros(n)
        gu = gamma[np.clip(upper_index, 0, n_cuts - 1), rows]
        d1_upper[upper_valid] = (gu * (1.0 - gu))[upper_valid]
        d2_upper[upper_valid] = (d1_upper * (1.0 - 2.0 * gu))[upper_valid]

        d1_lower = np.zeros(n)
        d2_lower = np.zeros(n)
        gl = gamma[np.clip(lower_index, 0, n_cuts - 1), rows]
        d1_lower[lower_valid] = (gl * (1.0 - gl))[lower_valid]
        d2_lower[lower_valid] = (d1_lower * (1.0 - 2.0 * gl))[lower_valid]

        # first_derivative[i] as a dense (n, n_cuts + 1) array.
        first_derivative = np.zeros((n, n_cuts + 1))
        np.add.at(first_derivative, (rows[upper_valid], upper_index[upper_valid]), d1_upper[upper_valid])
        np.add.at(first_derivative, (rows[lower_valid], lower_index[lower_valid]), -d1_lower[lower_valid])
        first_derivative[:, -1] = -(d1_upper - d1_lower) * x

        inverse_p = 1.0 / chosen
        gradient = first_derivative.T @ inverse_p
        information = (first_derivative * inverse_p[:, None]).T @ (first_derivative * inverse_p[:, None])

        # Subtract the second-derivative term, which has the same two-cut sparsity.
        signed_d2 = d2_upper - d2_lower
        second = np.zeros((n_cuts + 1, n_cuts + 1))
        np.add.at(
            second,
            (upper_index[upper_valid], upper_index[upper_valid]),
            (d2_upper * inverse_p)[upper_valid],
        )
        np.add.at(
            second,
            (lower_index[lower_valid], lower_index[lower_valid]),
            (-d2_lower * inverse_p)[lower_valid],
        )
        cross = np.zeros(n_cuts + 1)
        np.add.at(cross, upper_index[upper_valid], (-d2_upper * x * inverse_p)[upper_valid])
        np.add.at(cross, lower_index[lower_valid], (d2_lower * x * inverse_p)[lower_valid])
        second[:, -1] += cross
        second[-1, :] += cross
        second[-1, -1] = np.sum(signed_d2 * x * x * inverse_p) + cross[-1]
        information -= second

        if not np.all(np.isfinite(information)) or not np.all(np.isfinite(gradient)):
            return None

        try:
            step = np.linalg.solve(information + 1e-10 * np.eye(n_cuts + 1), gradient)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(step)):
            return None

        # Damp the step until the cut points stay strictly increasing.
        scale = 1.0
        for _backtrack in range(30):
            candidate_cuts = cuts + scale * step[:-1]
            if n_cuts == 1 or np.all(np.diff(candidate_cuts) > 1e-9):
                break
            scale *= 0.5
        else:
            return None

        cuts = cuts + scale * step[:-1]
        beta = beta + scale * step[-1]
        if np.max(np.abs(scale * step)) < 1e-8:
            break
    else:
        return None

    try:
        covariance = np.linalg.inv(information + 1e-10 * np.eye(n_cuts + 1))
    except np.linalg.LinAlgError:
        return None
    variance = covariance[-1, -1]
    if not np.isfinite(variance) or variance <= 0:
        return None
    return float(beta / sqrt(variance))


def simulate(s: Scenario, n1: int | None = None, n2: int | None = None, n_total: int | None = None) -> dict:
    simulations, seed = int(s.simulation.get("replications", 10_000)), int(s.simulation.get("seed", 20260717))
    rng, alpha, alternative, rejected, failed = np.random.default_rng(seed), s.decision_rule.alpha, s.decision_rule.alternative, 0, 0
    scipy_alternative = "two-sided" if alternative == "two.sided" else alternative
    if s.model == "two_sample_t":
        d, equal_var = float(s.effect["cohens_d"]), bool(s.design.get("equal_variance", True))
        for _ in range(simulations):
            x, y = rng.normal(0, 1, int(n1)), rng.normal(d, 1, int(n2))
            result = ttest_ind(y, x, equal_var=equal_var, alternative=scipy_alternative)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "welch_t":
        difference = float(s.effect["mean_difference"])
        sd1, sd2 = float(s.effect["sd_group1"]), float(s.effect["sd_group2"])
        for _ in range(simulations):
            x = rng.normal(0, sd1, int(n1))
            y = rng.normal(difference, sd2, int(n2))
            result = ttest_ind(y, x, equal_var=False, alternative=scipy_alternative)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "paired_t":
        dz = float(s.effect["cohens_dz"])
        for _ in range(simulations):
            differences = rng.normal(dz, 1, int(n_total))
            result = ttest_1samp(differences, 0, alternative=scipy_alternative)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "one_sample_proportion":
        p0, p1 = float(s.effect["p_null"]), float(s.effect["p_alternative"])
        for _ in range(simulations):
            successes = rng.binomial(int(n_total), p1)
            result = binomtest(successes, int(n_total), p=p0, alternative=scipy_alternative)
            rejected += result.pvalue <= alpha
    elif s.model == "two_sample_proportion":
        p1, p2 = float(s.effect["p_group1"]), float(s.effect["p_group2"])
        for _ in range(simulations):
            x1, x2 = rng.binomial(int(n1), p1), rng.binomial(int(n2), p2)
            pooled = (x1 + x2) / (int(n1) + int(n2))
            se = (pooled * (1 - pooled) * (1 / int(n1) + 1 / int(n2))) ** 0.5
            if se == 0:
                failed += 1
                continue
            z = (x2 / int(n2) - x1 / int(n1)) / se
            if alternative == "two.sided":
                pvalue = 2 * norm.sf(abs(z))
            elif alternative == "greater":
                pvalue = norm.sf(z)
            else:
                pvalue = norm.cdf(z)
            rejected += pvalue < alpha
    elif s.model == "chi_square_gof":
        p_null = np.array(s.effect["p_null"], dtype=float)
        p_alternative = np.array(s.effect["p_alternative"], dtype=float)
        expected = int(n_total) * p_null
        expected *= int(n_total) / expected.sum()
        for _ in range(simulations):
            observed = rng.multinomial(int(n_total), p_alternative)
            result = chisquare(observed, f_exp=expected)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "one_way_anova":
        groups, effect = int(s.design["groups"]), float(s.effect["cohens_f"])
        base = np.linspace(-1, 1, groups)
        means = base * effect / np.sqrt(np.mean(base**2))
        n_each = int(n_total) // groups
        for _ in range(simulations):
            samples = [rng.normal(mean, 1, n_each) for mean in means]
            result = f_oneway(*samples)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "linear_regression":
        predictors, f2 = int(s.design["predictors"]), float(s.effect["cohens_f2"])
        beta = np.full(predictors, np.sqrt(f2 / predictors))
        for _ in range(simulations):
            x = rng.normal(size=(int(n_total), predictors))
            y = x @ beta + rng.normal(size=int(n_total))
            x_design = np.column_stack((np.ones(int(n_total)), x))
            fitted = x_design @ np.linalg.lstsq(x_design, y, rcond=None)[0]
            ssr, sst = float(np.sum((fitted - y.mean())**2)), float(np.sum((y - y.mean())**2))
            r2 = min(ssr / sst, 1 - 1e-15) if sst else 0.0
            statistic = (r2 / predictors) / ((1 - r2) / (int(n_total) - predictors - 1))
            pvalue = f_distribution.sf(statistic, predictors, int(n_total) - predictors - 1)
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "incremental_regression":
        total, tested, f2 = int(s.design["total_predictors"]), int(s.design["tested_predictors"]), float(s.effect["cohens_f2"])
        beta = np.zeros(total)
        beta[-tested:] = np.sqrt(f2 / tested)
        for _ in range(simulations):
            x = rng.normal(size=(int(n_total), total))
            y = x @ beta + rng.normal(size=int(n_total))
            reduced = np.column_stack((np.ones(int(n_total)), x[:, :-tested]))
            full = np.column_stack((np.ones(int(n_total)), x))
            sse_reduced = float(np.sum((y - reduced @ np.linalg.lstsq(reduced, y, rcond=None)[0])**2))
            sse_full = float(np.sum((y - full @ np.linalg.lstsq(full, y, rcond=None)[0])**2))
            statistic = ((sse_reduced - sse_full) / tested) / (sse_full / (int(n_total) - total - 1))
            pvalue = f_distribution.sf(statistic, tested, int(n_total) - total - 1)
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "correlation":
        rho, cov = float(s.effect["rho"]), None
        cov = np.array([[1, rho], [rho, 1]])
        for _ in range(simulations):
            xy = rng.multivariate_normal([0, 0], cov, size=int(n_total))
            result = pearsonr(xy[:, 0], xy[:, 1], alternative=scipy_alternative)
            if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
            else: failed += 1
    elif s.model == "chi_square_independence":
        joint = np.array(s.effect["joint_probabilities"], dtype=float)
        flat = joint.ravel()
        for _ in range(simulations):
            counts = rng.multinomial(int(n_total), flat).reshape(joint.shape)
            try:
                result = chi2_contingency(counts, correction=False)
                if np.isfinite(result.pvalue): rejected += result.pvalue < alpha
                else: failed += 1
            except ValueError:
                failed += 1
    elif s.model == "factorial_anova":
        levels_a, levels_b = int(s.design["levels_a"]), int(s.design["levels_b"])
        term, effect = str(s.design["tested_term"]), float(s.effect["cohens_f"])
        n_each = int(n_total) // (levels_a * levels_b)
        # Build cell means whose population SD equals Cohen's f for the tested term.
        cell_means = np.zeros((levels_a, levels_b))
        for a in range(levels_a):
            for b in range(levels_b):
                code_a = 1.0 if a >= levels_a / 2 else -1.0
                code_b = 1.0 if b >= levels_b / 2 else -1.0
                if term == "A":
                    cell_means[a, b] = effect * code_a
                elif term == "B":
                    cell_means[a, b] = effect * code_b
                else:
                    cell_means[a, b] = effect * code_a * code_b
        for _ in range(simulations):
            y, fa, fb = [], [], []
            for a in range(levels_a):
                for b in range(levels_b):
                    outcomes = rng.normal(cell_means[a, b], 1, n_each)
                    y.extend(outcomes.tolist())
                    fa.extend([a] * n_each)
                    fb.extend([b] * n_each)
            y, fa, fb = np.array(y), np.array(fa), np.array(fb)
            # Effect-coded 2×2 OLS; for larger factors use group-mean ANOVA on the tested margin.
            if levels_a == 2 and levels_b == 2:
                xa = np.where(fa == 1, 1.0, -1.0)
                xb = np.where(fb == 1, 1.0, -1.0)
                design = np.column_stack((np.ones(len(y)), xa, xb, xa * xb))
                coef_index = {"A": 1, "B": 2, "AB": 3}[term]
                beta = np.linalg.lstsq(design, y, rcond=None)[0]
                sse = float(np.sum((y - design @ beta) ** 2))
                restricted = design.copy(); restricted[:, coef_index] = 0
                sse_r = float(np.sum((y - restricted @ np.linalg.lstsq(restricted, y, rcond=None)[0]) ** 2))
                df_err = len(y) - 4
                statistic = ((sse_r - sse) / 1) / (sse / df_err)
                pvalue = f_distribution.sf(statistic, 1, df_err)
            else:
                # Fallback: one-way ANOVA on the collapsed tested factor coding.
                if term == "A":
                    groups = [y[fa == level] for level in range(levels_a)]
                elif term == "B":
                    groups = [y[fb == level] for level in range(levels_b)]
                else:
                    groups = [y[(fa == a) & (fb == b)] for a in range(levels_a) for b in range(levels_b)]
                pvalue = f_oneway(*groups).pvalue
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "ancova":
        groups, effect, r2 = int(s.design["groups"]), float(s.effect["cohens_f"]), float(s.design["covariate_r2"])
        n_each = int(n_total) // groups
        base = np.linspace(-1, 1, groups)
        means = base * effect / np.sqrt(np.mean(base**2))
        for _ in range(simulations):
            ys, xs, gs = [], [], []
            for g, mean in enumerate(means):
                covariate = rng.normal(size=n_each)
                residual = rng.normal(0, sqrt(1 - r2), n_each)
                outcome = mean + sqrt(r2) * covariate + residual
                ys.append(outcome); xs.append(covariate); gs.append(np.full(n_each, g))
            y, x, g = np.concatenate(ys), np.concatenate(xs), np.concatenate(gs)
            dummies = np.column_stack([(g == level).astype(float) for level in range(1, groups)])
            full = np.column_stack((np.ones(len(y)), x, dummies))
            reduced = np.column_stack((np.ones(len(y)), x))
            sse_full = float(np.sum((y - full @ np.linalg.lstsq(full, y, rcond=None)[0]) ** 2))
            sse_reduced = float(np.sum((y - reduced @ np.linalg.lstsq(reduced, y, rcond=None)[0]) ** 2))
            df1, df2 = groups - 1, len(y) - groups - 1
            statistic = ((sse_reduced - sse_full) / df1) / (sse_full / df2)
            pvalue = f_distribution.sf(statistic, df1, df2)
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "planned_contrast":
        groups, weights, effect = int(s.design["groups"]), np.array(s.design["contrast_weights"], dtype=float), float(s.effect["cohens_f"])
        n_each = int(n_total) // groups
        # Scale cell means so contrast effect matches Cohen's f approximately.
        means = weights / np.sqrt(np.mean(weights**2)) * effect
        for _ in range(simulations):
            samples = [rng.normal(mean, 1, n_each) for mean in means]
            contrast = sum(weight * sample.mean() for weight, sample in zip(weights, samples))
            se = sqrt(sum((weight**2) * sample.var(ddof=1) / n_each for weight, sample in zip(weights, samples)))
            if se == 0:
                failed += 1
                continue
            df = groups * (n_each - 1)
            statistic = contrast / se
            from scipy.stats import t as student_t
            pvalue = 2 * student_t.sf(abs(statistic), df)
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "moderation":
        total, f2 = int(s.design["total_predictors"]), float(s.effect["cohens_f2"])
        for _ in range(simulations):
            x = rng.normal(size=int(n_total))
            m = rng.normal(size=int(n_total))
            interaction = x * m
            extras = rng.normal(size=(int(n_total), max(0, total - 3)))
            beta_int = sqrt(f2)
            y = beta_int * interaction + rng.normal(size=int(n_total))
            full = np.column_stack((np.ones(int(n_total)), x, m, interaction, extras)) if extras.size else np.column_stack((np.ones(int(n_total)), x, m, interaction))
            reduced = np.column_stack((np.ones(int(n_total)), x, m, extras)) if extras.size else np.column_stack((np.ones(int(n_total)), x, m))
            sse_full = float(np.sum((y - full @ np.linalg.lstsq(full, y, rcond=None)[0]) ** 2))
            sse_reduced = float(np.sum((y - reduced @ np.linalg.lstsq(reduced, y, rcond=None)[0]) ** 2))
            df2 = int(n_total) - full.shape[1]
            statistic = ((sse_reduced - sse_full) / 1) / (sse_full / df2)
            pvalue = f_distribution.sf(statistic, 1, df2)
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "logistic_regression":
        odds_ratio, p0 = float(s.effect["odds_ratio"]), float(s.effect["p_baseline"])
        predictor_type = str(s.design.get("predictor_type", "binary"))
        intercept = log(p0 / (1 - p0))
        beta = log(odds_ratio)
        for _ in range(simulations):
            if predictor_type == "binary":
                x = rng.binomial(1, 0.5, int(n_total)).astype(float)
            else:
                x = rng.normal(size=int(n_total))
            p = 1 / (1 + np.exp(-(intercept + beta * x)))
            y = rng.binomial(1, p)
            # Score test / Wald via IRLS one-step approximation.
            design = np.column_stack((np.ones(int(n_total)), x))
            try:
                coef = np.zeros(2)
                for _iter in range(25):
                    eta = design @ coef
                    mu = 1 / (1 + np.exp(-eta))
                    weight = mu * (1 - mu)
                    weight = np.clip(weight, 1e-6, None)
                    z = eta + (y - mu) / weight
                    sw = np.sqrt(weight)
                    coef = np.linalg.lstsq(design * sw[:, None], z * sw, rcond=None)[0]
                mu = 1 / (1 + np.exp(-(design @ coef)))
                weight = np.clip(mu * (1 - mu), 1e-6, None)
                fisher = design.T @ (design * weight[:, None])
                se = sqrt(np.linalg.inv(fisher)[1, 1])
                z = coef[1] / se
                if alternative == "two.sided":
                    pvalue = 2 * norm.sf(abs(z))
                elif alternative == "greater":
                    pvalue = norm.sf(z)
                else:
                    pvalue = norm.cdf(z)
                if np.isfinite(pvalue): rejected += pvalue < alpha
                else: failed += 1
            except np.linalg.LinAlgError:
                failed += 1
    elif s.model == "poisson_regression":
        rate_ratio = float(s.effect["rate_ratio"])
        baseline_rate, exposure = float(s.design["baseline_rate"]), float(s.design.get("exposure", 1))
        beta = log(rate_ratio)
        for _ in range(simulations):
            x = rng.binomial(1, 0.5, int(n_total)).astype(float)
            lam = baseline_rate * exposure * np.exp(beta * x)
            y = rng.poisson(lam)
            design = np.column_stack((np.ones(int(n_total)), x))
            try:
                coef = np.array([log(max(baseline_rate * exposure, 1e-6)), 0.0])
                for _iter in range(25):
                    eta = design @ coef
                    mu = np.exp(eta)
                    z = eta + (y - mu) / np.clip(mu, 1e-6, None)
                    sw = np.sqrt(np.clip(mu, 1e-6, None))
                    coef = np.linalg.lstsq(design * sw[:, None], z * sw, rcond=None)[0]
                mu = np.exp(design @ coef)
                fisher = design.T @ (design * mu[:, None])
                se = sqrt(np.linalg.inv(fisher)[1, 1])
                z = coef[1] / se
                if alternative == "two.sided":
                    pvalue = 2 * norm.sf(abs(z))
                elif alternative == "greater":
                    pvalue = norm.sf(z)
                else:
                    pvalue = norm.cdf(z)
                if np.isfinite(pvalue): rejected += pvalue < alpha
                else: failed += 1
            except (np.linalg.LinAlgError, ValueError):
                failed += 1
    elif s.model == "tost_equivalence":
        lower, upper = float(s.effect["lower_bound"]), float(s.effect["upper_bound"])
        true_diff, sd = float(s.effect.get("true_difference", 0.0)), float(s.effect["sd"])
        from scipy.stats import t as student_t
        for _ in range(simulations):
            x = rng.normal(0, sd, int(n1))
            y = rng.normal(true_diff, sd, int(n2))
            diff = y.mean() - x.mean()
            se = sqrt(x.var(ddof=1) / int(n1) + y.var(ddof=1) / int(n2))
            df = int(n1) + int(n2) - 2
            tcrit = student_t.ppf(1 - alpha, df)
            if se == 0:
                failed += 1
                continue
            rejected += ((diff - lower) / se > tcrit) and ((upper - diff) / se > tcrit)
    elif s.model == "mediation_indirect":
        a_path, b_path = float(s.effect["a_path"]), float(s.effect["b_path"])
        c_prime = float(s.effect.get("direct_cprime", 0.0))
        sd_m = float(s.design.get("residual_sd_m", 1.0))
        sd_y = float(s.design.get("residual_sd_y", 1.0))
        for _ in range(simulations):
            x = rng.normal(size=int(n_total))
            m = a_path * x + rng.normal(0, sd_m, int(n_total))
            y = c_prime * x + b_path * m + rng.normal(0, sd_y, int(n_total))
            # OLS a path: M ~ X
            xa = np.column_stack((np.ones(int(n_total)), x))
            beta_a = np.linalg.lstsq(xa, m, rcond=None)[0]
            resid_a = m - xa @ beta_a
            se_a = sqrt(np.sum(resid_a**2) / (int(n_total) - 2) / np.sum((x - x.mean())**2))
            # OLS b path: Y ~ X + M
            xb = np.column_stack((np.ones(int(n_total)), x, m))
            beta_b = np.linalg.lstsq(xb, y, rcond=None)[0]
            resid_b = y - xb @ beta_b
            mse = np.sum(resid_b**2) / (int(n_total) - 3)
            cov = np.linalg.inv(xb.T @ xb) * mse
            se_b = sqrt(cov[2, 2])
            from scipy.stats import t as student_t
            p_a = 2 * student_t.sf(abs(beta_a[1] / se_a), int(n_total) - 2)
            p_b = 2 * student_t.sf(abs(beta_b[2] / se_b), int(n_total) - 3)
            rejected += (p_a < alpha) and (p_b < alpha)
    elif s.model == "meta_analysis_fixed":
        studies, d = int(s.design["studies"]), float(s.effect["cohens_d"])
        n_per = int(n_total) // (2 * studies)
        for _ in range(simulations):
            effects, weights = [], []
            for _study in range(studies):
                control = rng.normal(0, 1, n_per)
                treat = rng.normal(d, 1, n_per)
                pooled = sqrt(((n_per - 1) * control.var(ddof=1) + (n_per - 1) * treat.var(ddof=1)) / (2 * n_per - 2))
                est = (treat.mean() - control.mean()) / pooled if pooled else 0.0
                var = 2 / n_per + est**2 / (4 * n_per)
                effects.append(est); weights.append(1 / var)
            effects, weights = np.array(effects), np.array(weights)
            summary = np.sum(weights * effects) / np.sum(weights)
            se = 1 / sqrt(np.sum(weights))
            z = summary / se
            if alternative == "two.sided":
                pvalue = 2 * norm.sf(abs(z))
            elif alternative == "greater":
                pvalue = norm.sf(z)
            else:
                pvalue = norm.cdf(z)
            rejected += pvalue < alpha
    elif s.model == "meta_analysis_random":
        studies, d = int(s.design["studies"]), float(s.effect["cohens_d"])
        tau = float(s.design.get("tau", 0.2))
        n_per = int(n_total) // (2 * studies)
        from scipy.stats import t as student_t
        # Hartung-Knapp reference distribution: t with k - 1 df (Hartung & Knapp 2001).
        use_hk = studies > 2
        if use_hk:
            df = studies - 1
            crit = float(student_t.ppf(1 - alpha / 2, df)) if alternative == "two.sided" else float(student_t.ppf(1 - alpha, df))
        else:
            crit = float(norm.ppf(1 - alpha / 2)) if alternative == "two.sided" else float(norm.ppf(1 - alpha))
        for _ in range(simulations):
            effects, weights = [], []
            study_truths = rng.normal(d, tau, studies)
            for truth in study_truths:
                control = rng.normal(0, 1, n_per)
                treat = rng.normal(truth, 1, n_per)
                pooled = sqrt(((n_per - 1) * control.var(ddof=1) + (n_per - 1) * treat.var(ddof=1)) / (2 * n_per - 2))
                est = (treat.mean() - control.mean()) / pooled if pooled else 0.0
                var = 2 / n_per + est**2 / (4 * n_per)
                effects.append(est)
                weights.append(1 / (var + tau**2))
            effects, weights = np.array(effects), np.array(weights)
            summary = np.sum(weights * effects) / np.sum(weights)
            if use_hk:
                # Hartung-Knapp variance rescaling: q = sum_i w_i (y_i - mu)^2 / (k - 1),
                # then SE = sqrt(q / sum_i w_i). Under the model E[q] = 1 and q follows
                # chi-square_{k-1}/(k-1), which is what makes the summary statistic
                # non-central t. Omitting q entirely (as an earlier version did) left the
                # simulator computing an inverse-variance z while comparing it to a t
                # critical value -- a hybrid matching no actual test.
                q = np.sum(weights * (effects - summary) ** 2) / (studies - 1)
                se = sqrt(max(q, 1e-12) / np.sum(weights))
            else:
                se = 1 / sqrt(np.sum(weights))
            stat = summary / se
            if alternative == "two.sided":
                rejected += abs(stat) > crit
            elif alternative == "greater":
                rejected += stat > crit
            else:
                rejected += stat < -crit
    elif s.model == "noninferiority_t":
        margin = float(s.effect["margin"])
        true_diff = float(s.effect.get("true_difference", 0.0))
        sd = float(s.effect["sd"])
        for _ in range(simulations):
            x = rng.normal(0, sd, int(n1))
            y = rng.normal(true_diff, sd, int(n2))
            pooled = sqrt(((int(n1) - 1) * x.var(ddof=1) + (int(n2) - 1) * y.var(ddof=1)) / (int(n1) + int(n2) - 2))
            se = pooled * (1 / int(n1) + 1 / int(n2)) ** 0.5 if pooled else 0.0
            if se == 0:
                failed += 1
                continue
            tstat = (y.mean() - x.mean() + margin) / se
            from scipy.stats import t as student_t
            pvalue = float(student_t.sf(tstat, int(n1) + int(n2) - 2))
            rejected += pvalue < alpha
    elif s.model == "ordinal_regression":
        odds_ratio = float(s.effect["odds_ratio"])
        categories = int(s.design["categories"])
        # Equal-spaced latent thresholds for the control arm on a standard logistic.
        cuts = np.linspace(-1, 1, categories - 1)
        beta = log(odds_ratio)
        for _ in range(simulations):
            x = rng.binomial(1, 0.5, int(n_total)).astype(float)
            latent = beta * x + rng.logistic(size=int(n_total))
            y = np.digitize(latent, cuts)
            # Fit the actual proportional-odds model. An earlier version collapsed the
            # outcome to binary around the median cut, which discards the ordinal
            # information the design is built on and understates achievable power.
            outcome = _proportional_odds_wald_z(y, x, categories)
            if outcome is None:
                failed += 1
                continue
            z = outcome
            pvalue = 2 * norm.sf(abs(z)) if alternative == "two.sided" else (norm.sf(z) if alternative == "greater" else norm.cdf(z))
            if np.isfinite(pvalue): rejected += pvalue < alpha
            else: failed += 1
    elif s.model == "bayes_factor_t":
        from powerbench.specialist_extras import _critical_t_for_bf, bic_bf10_from_t, jzs_bf10_from_t

        d = float(s.effect["cohens_d"])
        threshold = float(s.design.get("bf_threshold", 3))
        method = str(s.design.get("bf_method", "jzs")).lower()
        r_scale = float(s.design.get("r_scale", 0.7071))
        critical = _critical_t_for_bf(int(n1), int(n2), threshold, method, r_scale)
        bf_values: list[float] = []
        for _ in range(simulations):
            x = rng.normal(0, 1, int(n1))
            y = rng.normal(d, 1, int(n2))
            pooled = sqrt(((int(n1) - 1) * x.var(ddof=1) + (int(n2) - 1) * y.var(ddof=1)) / (int(n1) + int(n2) - 2))
            tstat = (y.mean() - x.mean()) / (pooled * (1 / int(n1) + 1 / int(n2)) ** 0.5) if pooled else 0.0
            rejected += abs(tstat) >= critical
            bf10 = jzs_bf10_from_t(tstat, int(n1), int(n2), r_scale) if method == "jzs" else bic_bf10_from_t(tstat, int(n1) + int(n2))
            if np.isfinite(bf10) and bf10 > 0:
                bf_values.append(float(bf10))
    elif s.model == "group_sequential_t":
        d = float(s.effect["cohens_d"])
        looks = int(s.design.get("looks", 2))
        # Explicit interim-look simulation using the same Lan-DeMets O'Brien-Fleming
        # boundaries the analytic reference solves for, so both sides describe one design.
        # The previous `z_crit / sqrt(t)` shortcut is not a valid boundary set: at two
        # looks and alpha = 0.05 it spends 0.05216, so the simulator was silently running
        # a slightly liberal test while the reference reported fixed-design power.
        from powerbench.specialist_extras import group_sequential_boundaries

        equal_var = bool(s.design.get("equal_variance", True))
        info_fractions = np.linspace(1 / looks, 1.0, looks)
        boundaries = group_sequential_boundaries(looks, alpha, alternative)
        for _ in range(simulations):
            x_full, y_full = rng.normal(0, 1, int(n1)), rng.normal(d, 1, int(n2))
            crossed = False
            valid = True
            for fraction, boundary in zip(info_fractions, boundaries):
                k1 = max(2, int(round(int(n1) * fraction)))
                k2 = max(2, int(round(int(n2) * fraction)))
                result = ttest_ind(y_full[:k2], x_full[:k1], equal_var=equal_var)
                if not np.isfinite(result.statistic):
                    valid = False
                    break
                stat = float(result.statistic)
                if alternative == "two.sided":
                    crossed = abs(stat) >= boundary
                elif alternative == "greater":
                    crossed = stat >= boundary
                else:
                    crossed = stat <= -boundary
                if crossed:
                    break
            if not valid:
                failed += 1
                continue
            rejected += crossed
    elif s.model == "logrank_two_arm":
        hr = float(s.effect["hazard_ratio"])
        p_event = float(s.effect["p_event"])
        control_hazard = float(s.design.get("control_hazard", 1.0))
        lam0, lam1 = control_hazard, control_hazard * hr
        accrual_years = float(s.design.get("accrual_years", 0.0))
        followup_years = float(s.design.get("followup_years", 1.0))
        dropout_hazard = float(s.design.get("dropout_hazard", 0.0))
        ratio = float(s.design.get("allocation_ratio", 1.0))
        if n1 is None or n2 is None:
            n1 = max(2, int(round(int(n_total) / (1 + ratio))))
            n2 = int(n_total) - int(n1)
        p1 = int(n1) / (int(n1) + int(n2))

        def event_prob(window: float) -> float:
            e0 = (1 - exp(-lam0 * window))
            e1 = (1 - exp(-lam1 * window))
            if dropout_hazard > 0:
                e0 *= lam0 / (lam0 + dropout_hazard)
                e1 *= lam1 / (lam1 + dropout_hazard)
            return p1 * e0 + (1 - p1) * e1

        lo, hi = 1e-4, max(0.5, followup_years + max(accrual_years, 0.5))
        if event_prob(hi) < p_event and accrual_years <= 0:
            censor_time = hi
        else:
            while event_prob(lo) > p_event and lo > 1e-8:
                lo *= 0.5
            for _ in range(60):
                mid = (lo + hi) / 2
                if event_prob(mid) < p_event:
                    lo = mid
                else:
                    hi = mid
            censor_time = hi

        def logrank_pvalue(time0: np.ndarray, event0: np.ndarray, time1: np.ndarray, event1: np.ndarray) -> float:
            times = np.concatenate([time0, time1])
            events = np.concatenate([event0.astype(bool), event1.astype(bool)])
            groups = np.concatenate([np.zeros(len(time0), dtype=int), np.ones(len(time1), dtype=int)])
            order = np.argsort(times, kind="mergesort")
            times, events, groups = times[order], events[order], groups[order]
            at_risk0, at_risk1 = float(len(time0)), float(len(time1))
            o_minus_e, variance = 0.0, 0.0
            i, n_obs = 0, len(times)
            while i < n_obs:
                t = times[i]
                d0 = d1 = c0 = c1 = 0
                while i < n_obs and times[i] == t:
                    if events[i]:
                        if groups[i] == 0:
                            d0 += 1
                        else:
                            d1 += 1
                    else:
                        if groups[i] == 0:
                            c0 += 1
                        else:
                            c1 += 1
                    i += 1
                d = d0 + d1
                r = at_risk0 + at_risk1
                if d > 0 and r > 1:
                    e1 = d * (at_risk1 / r)
                    o_minus_e += d1 - e1
                    variance += d * (at_risk0 / r) * (at_risk1 / r) * (r - d) / (r - 1)
                at_risk0 -= d0 + c0
                at_risk1 -= d1 + c1
            if variance <= 0:
                return 1.0
            z = o_minus_e / sqrt(variance)
            if alternative == "two.sided":
                return float(2 * norm.sf(abs(z)))
            if alternative == "greater":
                return float(norm.sf(z))
            return float(norm.cdf(z))

        for _ in range(simulations):
            entry0 = rng.uniform(0.0, accrual_years, int(n1)) if accrual_years > 0 else np.zeros(int(n1))
            entry1 = rng.uniform(0.0, accrual_years, int(n2)) if accrual_years > 0 else np.zeros(int(n2))
            admin0 = np.full(int(n1), censor_time) if accrual_years <= 0 else (accrual_years + followup_years - entry0)
            admin1 = np.full(int(n2), censor_time) if accrual_years <= 0 else (accrual_years + followup_years - entry1)
            time0 = rng.exponential(1 / lam0, int(n1))
            time1 = rng.exponential(1 / lam1, int(n2))
            if dropout_hazard > 0:
                drop0 = rng.exponential(1 / dropout_hazard, int(n1))
                drop1 = rng.exponential(1 / dropout_hazard, int(n2))
                censor0 = np.minimum(admin0, drop0)
                censor1 = np.minimum(admin1, drop1)
            else:
                censor0 = admin0
                censor1 = admin1
            event0 = time0 <= censor0
            event1 = time1 <= censor1
            obs0 = np.minimum(time0, censor0)
            obs1 = np.minimum(time1, censor1)
            pvalue = logrank_pvalue(obs0, event0, obs1, event1)
            if np.isfinite(pvalue):
                rejected += pvalue < alpha
            else:
                failed += 1
    elif s.model == "rope_equivalence_t":
        lower, upper = float(s.effect["lower_bound"]), float(s.effect["upper_bound"])
        true_diff, sd = float(s.effect.get("true_difference", 0.0)), float(s.effect["sd"])
        prior_sd = float(s.design.get("prior_sd", 10.0))
        threshold = float(s.design.get("rope_threshold", 0.95))
        from powerbench.specialist_extras import rope_posterior_prob
        for _ in range(simulations):
            x = rng.normal(0, sd, int(n1))
            y = rng.normal(true_diff, sd, int(n2))
            observed = y.mean() - x.mean()
            # Conjugate update using known-sd planning model (matches analytic reference).
            prob = rope_posterior_prob(observed, int(n1), int(n2), sd, lower, upper, prior_sd)
            rejected += prob >= threshold
    else:
        raise NotImplementedError(f"No simulator for {s.model}")
    completed, power = simulations - failed, rejected / max(simulations - failed, 1)
    se, low, high = _ci95(power, max(completed, 1))
    result = {"replications_requested": simulations, "replications_completed": completed, "seed": seed, "power": power, "mc_standard_error": se, "mc_ci95": [low, high], "failures": failed, "engine": "independent_numpy_scipy_simulation"}
    if s.model == "bayes_factor_t":
        logs = np.log(np.asarray(bf_values)) if bf_values else np.asarray([])
        result["bayes_diagnostics"] = {
            "mean_bf10": float(np.mean(bf_values)) if bf_values else 0.0,
            "median_bf10": float(np.median(bf_values)) if bf_values else 0.0,
            "mean_log_bf10": float(np.mean(logs)) if logs.size else float("-inf"),
        }
    return result
