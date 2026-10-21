# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Allowlisted scientific snapshots. Identity stripping is never a rendering toggle."""
from __future__ import annotations

import re
from copy import deepcopy
from math import isclose

from .contracts import normalize
from .provenance import input_hash
from .reproducibility import reproduction

_EFFECT = {"margin", "baseline_category_probs", "p_baseline", "p_event", "cohens_d", "cohens_dz", "rho", "cohens_f", "cohens_f2", "mean_difference", "sd_group1", "sd_group2", "p_null", "p_alternative", "p_group1", "p_group2", "joint_probabilities", "odds_ratio", "rate_ratio", "hazard_ratio", "true_difference", "sd", "lower_bound", "upper_bound", "a_path", "b_path"}
_DESIGN = {"family_alpha", "primary_tests", "allocation_ratio", "equal_variance", "attrition_rate", "groups", "predictors", "total_predictors", "tested_predictors", "categories", "rows", "cols", "min_expected_count", "levels_a", "levels_b", "covariate_r2", "contrast_weights", "studies", "tau", "hartung_knapp", "looks", "bf_threshold", "r_scale", "prior_sd", "rope_threshold", "p_event", "control_hazard", "accrual_years", "followup_years", "dropout_hazard", "baseline_rate", "exposure", "baseline_probability", "predictor_r2", "x_variance", "x_probability", "x_mean", "x_sd", "residual_sd", "residual_sd_y", "residual_sd_m"}


def _numeric(value):
    if isinstance(value, (int, float, bool)) and not isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_numeric(item) for item in value]
    raise ValueError("Only numeric scientific parameters are included automatically; remove or review free text")


def anonymous_snapshot(result: dict) -> dict:
    request = deepcopy(result.get("normalized_request"))
    if not isinstance(request, dict):
        raise ValueError("An immutable portable analysis result is required")
    source = request.get("scenario", {})
    scenario = {"id": "anonymous-analysis", "title": "Study analysis", "model": source.get("model"), "framework": source.get("framework"), "goal": source.get("goal"), "target_power": source.get("target_power"),
                "effect": {k: _numeric(v) for k, v in source.get("effect", {}).items() if k in _EFFECT},
                "design": {k: _numeric(v) for k, v in source.get("design", {}).items() if k in _DESIGN},
                "decision_rule": source.get("decision_rule", {}), "assumptions": [], "simulation": {}, "status": "draft"}
    # A small set of categorical scientific values is enumerated explicitly.
    for key, choices in {"predictor_type": {"binary", "continuous"}, "tested_term": {"A", "B", "AB"}, "bf_method": {"jzs", "bic"}, "predictor_distribution": {"binary", "normal"}}.items():
        value = source.get("design", {}).get(key)
        if value in choices:
            scenario["design"][key] = value
    sanitized = {"schema_version": "1.0", "operation": request["operation"], "scenario": scenario}
    if request.get("sample"):
        sanitized["sample"] = {k: _numeric(v) for k, v in request["sample"].items() if k in {"n1", "n2", "n_total"}}
    if request.get("domain"):
        sanitized["domain"] = {k: v for k, v in request["domain"].items() if k in {"lower", "upper", "direction", "parameter"}}
    normalized, _ = normalize(sanitized)
    original = result.get("result", result.get("reference", {}))
    values = {k: _numeric(v) for k, v in original.items() if k in {"n1", "n2", "n_total", "n_per_group", "n_per_cell", "power", "target_power", "detectable_effect", "cohens_w", "n_events"}}
    if result.get("status", "complete") != "complete":
        raise ValueError("Only completed results may be shared")
    provenance = result.get("provenance", {})
    version = provenance.get("engine_version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Missing release version")
    from . import __version__
    if version != __version__:
        raise ValueError("Historical snapshots require their original engine release; recompute as a new version before sharing")
    from . import method_version
    if provenance.get("method_version") != method_version(scenario["model"]):
        raise ValueError("Historical method version requires its original implementation; recompute before sharing")
    from .api import analyze
    replay = analyze(normalized)
    if replay.get("status") != "complete":
        raise ValueError("Sanitized request did not reproduce a complete result")
    for key, value in values.items():
        expected = replay["result"].get(key)
        if expected is None or not isclose(value, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Stored result does not match the sanitized reproduction")
    scripts = reproduction(normalized)
    from . import __version__
    for script in scripts:
        if script["language"] == "python":
            script["code"] = script["code"].replace(f"powerbench=={__version__}", f"powerbench=={version}")
    return {"schema_version": "1.0", "anonymization_version": "1.0", "status": "complete", "operation": normalized["operation"], "normalized_request": normalized, "result": values,
            "warnings": ["Identity metadata and source documents are excluded. Scientific details may still reveal identity; review this exact snapshot before sharing."],
            "provenance": {"engine_version": version, "method_id": scenario["model"], "method_version": provenance.get("method_version"), "input_sha256": input_hash(normalized)}, "reproduction": scripts, "reporting": replay.get("reporting", {}), "citations": replay.get("citations", [])}
