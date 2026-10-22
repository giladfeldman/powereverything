"""Evaluate a fixed, explicit sample design using existing reference primitives."""
from __future__ import annotations

from math import isfinite

from . import references as ref
from .capabilities import FIXED_MODELS
from .schema import Scenario


def count(value: float | str | None, name: str, minimum: int = 2) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be an integer >= {minimum}") from exc
    if not isfinite(number) or not number.is_integer() or number < minimum or number > 10_000_000:
        raise ValueError(f"{name} must be an integer from {minimum} to 10,000,000")
    return int(number)


def sample_design(model: str, sample: dict) -> dict[str, int]:
    """Validate sample units and derive the total from explicit independent arms."""
    if not isinstance(sample, dict):
        raise TypeError("sample must be an object")
    if model in {"two_sample_t", "welch_t"}:
        if set(sample) - {"n1", "n2", "n_total"}:
            raise ValueError("Unrecognized sample field")
        n1, n2 = count(sample.get("n1"), "n1"), count(sample.get("n2"), "n2")
        total = count(n1 + n2, "n_total")
        if "n_total" in sample and count(sample["n_total"], "n_total") != total:
            raise ValueError("n_total conflicts with n1 + n2")
        return {"n1": n1, "n2": n2, "n_total": total}
    if set(sample) != {"n_total"}:
        raise ValueError("This model requires only n_total in its declared sample units; independent-arm counts are not supported")
    return {"n_total": count(sample["n_total"], "n_total")}


def fixed_power(s: Scenario, sample: dict) -> dict:
    if s.model not in FIXED_MODELS:
        raise NotImplementedError(f"Fixed-sample power is not yet validated for {s.model}")
    sample = sample_design(s.model, sample)
    alpha, alt, e, d = s.decision_rule.alpha, s.decision_rule.alternative, s.effect, s.design
    model = s.model
    if model in {"two_sample_t", "welch_t"}:
        n1, n2 = count(sample.get("n1"), "n1"), count(sample.get("n2"), "n2")
        n = n1 + n2
        if "n_total" in sample and count(sample["n_total"], "n_total") != n:
            raise ValueError("n_total conflicts with n1 + n2")
        if model == "two_sample_t":
            power = ref.two_sample_t_power(n1, n2, float(e["cohens_d"]), alpha, alt)
        else:
            power = ref.welch_t_power(n1, n2, float(e["mean_difference"]), float(e["sd_group1"]), float(e["sd_group2"]), alpha, alt)
        shape = {"n1": n1, "n2": n2, "n_total": n}
    else:
        n = count(sample.get("n_total"), "n_total")
        shape = {"n_total": n}
        if model == "paired_t":
            power = ref.paired_t_power(n, float(e["cohens_dz"]), alpha, alt)
        elif model == "correlation":
            if n < 4:
                raise ValueError("Correlation requires at least 4 observations")
            power = ref.correlation_power(n, float(e["rho"]), alpha, alt)
        elif model in {"one_way_anova", "factorial_anova", "ancova", "planned_contrast"}:
            groups = count(d.get("groups"), "groups") if model != "factorial_anova" else count(d.get("levels_a"), "levels_a") * count(d.get("levels_b"), "levels_b")
            if n % groups or n < groups * 2:
                raise ValueError("Balanced designs require an integer sample per group/cell, at least 2")
            per = n // groups
            if model == "one_way_anova":
                power = ref.one_way_anova_power(per, groups, float(e["cohens_f"]), alpha)
            elif model == "factorial_anova":
                power = ref.factorial_anova_power(per, int(d["levels_a"]), int(d["levels_b"]), d["tested_term"], float(e["cohens_f"]), alpha)
            elif model == "ancova":
                power = ref.ancova_power(per, groups, float(e["cohens_f"]), float(d["covariate_r2"]), alpha)
            else:
                power = ref.planned_contrast_power(per, groups, d["contrast_weights"], float(e["cohens_f"]), alpha)
        else:
            total = count(d.get("predictors") if model == "linear_regression" else d.get("total_predictors"), "predictors", 1)
            if n <= total + 1:
                raise ValueError("Residual degrees of freedom must be positive")
            if model == "linear_regression":
                power = ref.linear_regression_power(n, total, float(e["cohens_f2"]), alpha)
            else:
                tested = 1 if model == "moderation" else count(d.get("tested_predictors"), "tested_predictors", 1)
                power = ref.incremental_regression_power(n, total, tested, float(e["cohens_f2"]), alpha)
    # At the central null these continuous reference tests reject at alpha.
    # scipy's noncentral-F sf at ncp=0 can return a negative value; use the
    # central-null identity here, never a clamp for nonzero effects.
    if float(e[FIXED_MODELS[model]]) == 0:
        power = alpha
    if not isfinite(power) or not 0 <= power <= 1:
        raise ValueError("Numerical power evaluation failed; no result was substituted")
    return {**shape, "power": float(power), "method": model, "goal": "achieved_power"}
