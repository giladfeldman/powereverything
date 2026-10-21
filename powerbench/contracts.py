# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Versioned JSON request normalization; no web framework dependency."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from math import isfinite
from typing import get_args

from .capabilities import DEFAULT_TARGET_POWER, FIXED_MODELS
from .schema import DecisionRule, Framework, Goal, Model, Scenario

SCHEMA_VERSION = "1.0"


def finite_tree(value):
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Nonfinite numbers are not valid inputs")
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def numeric_parameters(value, path="effect"):
    if isinstance(value, dict):
        for name, item in value.items():
            if name == "parameterization":
                continue
            numeric_parameters(item, f"{path}.{name}")
    elif isinstance(value, list):
        for item in value:
            numeric_parameters(item, path)
    elif isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{path} must contain finite numbers")


def normalize(request: dict) -> tuple[dict, Scenario]:
    if not isinstance(request, dict):
        raise ValueError("Request must be an object")
    raw = deepcopy(request)
    if set(raw) - {"schema_version", "operation", "scenario", "sample", "domain", "options"}:
        raise ValueError("Unrecognized request field")
    if raw.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("Unsupported schema_version")
    raw["schema_version"] = SCHEMA_VERSION
    if raw.get("operation", "plan") not in {"plan", "power", "detectable_effect"}:
        raise ValueError("Unsupported operation")
    raw.setdefault("operation", "plan")
    value = raw.get("scenario")
    if not isinstance(value, dict):
        raise ValueError("scenario must be an object")
    if set(value) - {f.name for f in fields(Scenario)}:
        raise ValueError("Unrecognized scenario field")
    goal = {"plan": "required_sample_size", "power": "achieved_power", "detectable_effect": "sensitivity"}[raw["operation"]]
    if value.get("goal", goal) != goal:
        raise ValueError("operation and scenario.goal conflict")
    value["goal"] = goal
    value.setdefault("id", "portable-analysis")
    value.setdefault("title", "Study analysis under stated assumptions")
    value.setdefault("framework", "frequentist")
    value.setdefault("target_power", None if goal == "achieved_power" else DEFAULT_TARGET_POWER)
    value.setdefault("design", {})
    value.setdefault("effect", {})
    value.setdefault("decision_rule", {})
    if value.get("model") not in get_args(Model) or value["framework"] not in get_args(Framework) or goal not in get_args(Goal):
        raise ValueError("Unrecognized model, framework or goal")
    finite_tree(raw)
    if not isinstance(value["design"], dict) or not isinstance(value["effect"], dict) or not isinstance(value["decision_rule"], dict):
        raise ValueError("design, effect and decision_rule must be objects")
    numeric_parameters(value["effect"])
    for name in ("groups", "predictors", "total_predictors", "tested_predictors", "categories", "rows", "cols", "levels_a", "levels_b", "studies", "looks"):
        if name in value["design"]:
            from .power import count
            count(value["design"][name], name, 1)
    rule_alpha = value["decision_rule"].get("alpha", .05)
    if isinstance(rule_alpha, bool) or not isinstance(rule_alpha, (int, float)):
        raise ValueError("alpha must be a number")
    target = value["target_power"]
    if target is not None and (isinstance(target, bool) or not isinstance(target, (int, float))):
        raise ValueError("target_power must be a number")
    rule = value["decision_rule"]
    if rule.get("multiplicity_method", "none") == "none" and value["design"].get("family_alpha") is not None and value["design"].get("primary_tests", 1) != 1:
        raise ValueError("A declared family with multiple tests requires an explicit multiplicity adjustment; unadjusted alpha does not control family error")
    if rule.get("multiplicity_method", "none") != "none":
        design = value["design"]
        if "family_alpha" not in design or "primary_tests" not in design:
            raise ValueError("Multiplicity requires explicit family_alpha and primary_tests; alpha is the per-test threshold")
        from .power import count
        tests = count(design["primary_tests"], "primary_tests", 1)
        family = design["family_alpha"]
        if isinstance(family, bool) or not isinstance(family, (int, float)) or not 0 < family < 1:
            raise ValueError("family_alpha must lie in (0,1)")
        if abs(rule_alpha - family / tests) > 1e-14:
            raise ValueError("Per-test alpha does not match the declared multiplicity planning adjustment")
    scenario = Scenario(**{**value, "decision_rule": DecisionRule(**value["decision_rule"])})
    scalar = FIXED_MODELS.get(scenario.model)
    if goal == "sensitivity" and scalar:
        # The parameter being solved is absent from canonical inputs. A small
        # internal value validates the remaining design without inventing evidence.
        scenario = replace(scenario, effect={**scenario.effect, scalar: 1e-6})
    validation = scenario
    if goal == "achieved_power" and scalar and scenario.effect.get(scalar) == 0:
        validation = replace(scenario, effect={**scenario.effect, scalar: 1e-6})
    validation.validate()
    if value["target_power"] is not None and not 0 < float(value["target_power"]) < 1:
        raise ValueError("target_power must lie strictly between 0 and 1")
    if goal == "sensitivity" and scalar:
        domain = raw.get("domain", {})
        if not isinstance(domain, dict):
            raise ValueError("domain must be an object")
        scale = max(float(scenario.effect["sd_group1"]), float(scenario.effect["sd_group2"])) if scenario.model == "welch_t" else 1.0
        raw["domain"] = {"parameter": scalar, "direction": "negative" if scenario.decision_rule.alternative == "less" else "positive", "lower": 1e-8 * scale, "upper": .999999 if scalar == "rho" else 10 * scale, **domain}
    raw["scenario"] = scenario.to_dict()
    if goal == "sensitivity" and scalar:
        raw["scenario"]["effect"].pop(scalar, None)
    if goal != "required_sample_size" and (not isinstance(raw.get("sample"), dict) or not raw["sample"]):
        raise ValueError("Fixed-sample operations require an explicit sample object")
    if goal == "required_sample_size" and raw.get("sample"):
        raise ValueError("Sample size is solved, not fixed, for the plan operation")
    if not isinstance(raw.get("sample", {}), dict):
        raise ValueError("sample must be an object")
    if set(raw.get("sample", {})) - {"n1", "n2", "n_total"}:
        raise ValueError("Unrecognized sample field")
    if raw.get("sample"):
        from .power import count
        raw["sample"] = {name: count(number, name) for name, number in raw["sample"].items()}
    if not isinstance(raw.get("options", {}), dict) or raw.get("options"):
        raise ValueError("No execution options are supported by this contract version yet")
    return raw, scenario
