"""Bounded inversion along an explicitly declared scalar-effect trajectory."""
from __future__ import annotations

from dataclasses import replace
from itertools import pairwise
from math import isfinite

import numpy as np
from scipy.optimize import brentq

from .capabilities import FIXED_MODELS
from .power import fixed_power
from .schema import Scenario


def detectable_effect(s: Scenario, sample: dict, domain: dict | None = None) -> dict:
    if s.model not in FIXED_MODELS:
        raise NotImplementedError(f"Fixed-N sensitivity is not yet validated for {s.model}")
    key = FIXED_MODELS[s.model]
    domain = dict(domain or {})
    if set(domain) - {"lower", "upper", "direction", "parameter"}:
        raise ValueError("Unrecognized effect-domain option")
    if domain.get("parameter", key) != key:
        raise ValueError(f"This model's supported scalar parameter is {key}")
    default_direction = "negative" if s.decision_rule.alternative == "less" else "positive"
    direction = domain.get("direction", default_direction)
    if direction not in {"positive", "negative"}:
        raise ValueError("direction must be positive or negative")
    signed = key in {"cohens_d", "cohens_dz", "rho", "mean_difference"}
    if direction == "negative" and not signed:
        raise ValueError("This effect metric is nonnegative")
    if s.decision_rule.alternative != "two.sided" and direction != default_direction:
        raise ValueError("Effect direction conflicts with the one-sided test")
    lower, upper = float(domain.get("lower", 1e-8)), float(domain.get("upper", .999999 if key == "rho" else 10))
    if not all(map(isfinite, (lower, upper))) or not 0 < lower < upper or upper > 10000 or (key == "rho" and upper >= 1):
        raise ValueError("Specify finite positive magnitude bounds; correlations must remain below 1")
    target = s.target_power
    if target is None or not 0 < target < 1:
        raise ValueError("Sensitivity requires target_power in (0, 1)")
    sign = -1 if direction == "negative" else 1

    def evaluate(magnitude):
        scenario = replace(s, effect={**s.effect, key: sign * float(magnitude)})
        return fixed_power(scenario, sample)["power"]

    # Stop once the target is bracketed. Evaluating an unnecessarily enormous
    # noncentrality can fail in distribution backends even when the root is small.
    grid, values = [], []
    for point in np.geomspace(lower, upper, 65):
        grid.append(float(point))
        values.append(evaluate(point))
        if values[-1] >= target:
            break
    if any(b + 1e-10 < a for a, b in pairwise(values)):
        raise ValueError("Power is not monotone on the requested domain; a single threshold would be misleading")
    diagnostics = {"parameter": key, "magnitude_bounds": [lower, upper], "evaluated_magnitude_bounds": [grid[0], grid[-1]], "direction": direction, "grid_points": len(grid), "solver": "brentq", "absolute_effect_tolerance": 1e-10}
    if values[0] >= target:
        return {"status": "unreachable", "reason": "threshold_below_domain", "diagnostics": diagnostics}
    if values[-1] < target:
        return {"status": "unreachable", "reason": "target_above_domain_power", "diagnostics": diagnostics}
    root = float(brentq(lambda x: evaluate(x) - target, grid[-2], grid[-1], xtol=1e-10))
    effect = sign * root
    power = evaluate(root)
    return {"status": "complete", **sample, "effect_parameter": key, "detectable_effect": effect, "target_power": target, "power": power, "goal": "sensitivity", "method": s.model, "diagnostics": diagnostics,
            "curve": [{"effect": sign * float(x), "power": float(p), "status": "complete"} for x, p in zip(grid, values)]}
