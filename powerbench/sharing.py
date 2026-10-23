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

SNAPSHOT_NUMERIC_FIELDS = frozenset({"n1", "n2", "n_total", "n_per_group", "n_per_cell", "power", "target_power", "detectable_effect", "cohens_w", "n_events"})

_EFFECT = {"margin", "baseline_category_probs", "p_baseline", "p_event", "cohens_d", "cohens_dz", "rho", "cohens_f", "cohens_f2", "mean_difference", "sd_group1", "sd_group2", "p_null", "p_alternative", "p_group1", "p_group2", "joint_probabilities", "odds_ratio", "rate_ratio", "hazard_ratio", "true_difference", "sd", "lower_bound", "upper_bound", "a_path", "b_path"}
_DESIGN = {"allocation_numerator", "allocation_denominator","family_alpha", "primary_tests", "allocation_ratio", "equal_variance", "attrition_rate", "groups", "predictors", "total_predictors", "tested_predictors", "categories", "rows", "cols", "min_expected_count", "levels_a", "levels_b", "covariate_r2", "contrast_weights", "studies", "tau", "hartung_knapp", "looks", "bf_threshold", "r_scale", "prior_sd", "rope_threshold", "p_event", "control_hazard", "accrual_years", "followup_years", "dropout_hazard", "baseline_rate", "exposure", "baseline_probability", "predictor_r2", "x_variance", "x_probability", "x_mean", "x_sd", "residual_sd", "residual_sd_y", "residual_sd_m"}


def _numeric(value):
    if isinstance(value, (int, float, bool)) and not isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_numeric(item) for item in value]
    raise ValueError("Only numeric scientific parameters are included automatically; remove or review free text")


def anonymous_snapshot(result: dict) -> dict:
    if not isinstance(result, dict):
        raise ValueError("A scientific result object is required")
    request = deepcopy(result.get("normalized_request"))
    if not isinstance(request, dict):
        raise ValueError("An immutable portable analysis result is required")
    provenance = result.get("provenance", {})
    if not isinstance(provenance, dict) or provenance.get("input_sha256") != input_hash(request):
        raise ValueError("Stored scientific input hash does not match the original request")
    if request.get("operation") in {"compare","simulate"}:
        return _anonymous_composite(result)
    source = request.get("scenario", {})
    if not isinstance(source, dict) or request.get("operation") not in {"plan", "power", "detectable_effect"}:
        raise ValueError("A portable scientific scenario and operation are required")
    if any(not isinstance(source.get(key, {}), dict) for key in ("effect", "design", "decision_rule")):
        raise ValueError("Scientific effect, design and decision rule must be objects")
    if provenance.get("method_id") != source.get("model"):
        raise ValueError("Stored method identity does not match the scientific request")
    scenario = {"id": "anonymous-analysis", "title": "Study analysis", "model": source.get("model"), "framework": source.get("framework"), "goal": source.get("goal"), "target_power": source.get("target_power"),
                "effect": {k: _numeric(v) for k, v in source.get("effect", {}).items() if k in _EFFECT},
                "design": {k: _numeric(v) for k, v in source.get("design", {}).items() if k in _DESIGN},
                "decision_rule": source.get("decision_rule", {}), "assumptions": [], "simulation": {}, "status": "draft"}
    # A small set of categorical scientific values is enumerated explicitly.
    for key, choices in {"predictor_type": {"binary", "continuous"}, "tested_term": {"A", "B", "AB"}, "bf_method": {"jzs", "bic"}, "predictor_distribution": {"binary", "normal"}}.items():
        value = source.get("design", {}).get(key)
        if key == "bf_method" and isinstance(value, str):
            value = value.lower()
        if value in choices:
            scenario["design"][key] = value
    sanitized = {"schema_version": "1.0", "operation": request["operation"], "scenario": scenario}
    if request.get("sample"):
        sanitized["sample"] = {k: _numeric(v) for k, v in request["sample"].items() if k in {"n1", "n2", "n_total"}}
    if request.get("domain") and request.get("operation") == "detectable_effect":
        sanitized["domain"] = {k: v for k, v in request["domain"].items() if k in {"lower", "upper", "direction", "parameter"}}
    normalized, _ = normalize(sanitized)
    original = result.get("result", result.get("reference", {}))
    if not isinstance(original, dict) or not original:
        raise ValueError("A complete numeric result is required for sharing")
    values = {k: _numeric(v) for k, v in original.items() if k in SNAPSHOT_NUMERIC_FIELDS}
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
    expected_fields = set(replay["result"]) & SNAPSHOT_NUMERIC_FIELDS
    if set(values) != expected_fields:
        raise ValueError("Stored result is missing required scientific quantities")
    for key, value in values.items():
        expected = replay["result"].get(key)
        if expected is None or not isclose(value, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Stored result does not match the sanitized reproduction")
    scripts = reproduction(normalized)
    from . import __version__
    for script in scripts:
        if script["language"] == "python":
            script["code"] = script["code"].replace(f"powerbench=={__version__}", f"powerbench=={version}")
    # Preserve only neutral version pins. OS/build/host details and timestamps
    # can identify an author and are deliberately excluded from reviewer exports.
    shared_provenance = {"engine_version": version, "method_id": scenario["model"], "method_version": provenance.get("method_version"), "input_sha256": input_hash(normalized)}
    version_pattern = r"\d+\.\d+\.\d+(?:(?:a|b|rc|\.post|\.dev)\d+)?"
    verified_provenance = replay["provenance"]
    dependencies = {name: value for name, value in verified_provenance.get("dependencies", {}).items()
                    if name in {"numpy", "scipy"} and isinstance(value, str) and re.fullmatch(version_pattern, value)}
    if dependencies:
        shared_provenance["dependencies"] = dependencies
    python_version = verified_provenance.get("runtime", {}).get("python")
    if isinstance(python_version, str) and re.fullmatch(version_pattern, python_version):
        shared_provenance["runtime"] = {"python": python_version}
    return {"schema_version": "1.0", "anonymization_version": "1.2", "status": "complete", "operation": normalized["operation"], "normalized_request": normalized, "result": values,
            "warnings": ["Identity metadata and source documents are excluded. Scientific details may still reveal identity; review this exact snapshot before sharing."],
            "provenance": shared_provenance, "reproduction": scripts, "reporting": replay.get("reporting", {}), "citations": replay.get("citations", [])}


def _anonymous_composite(result: dict) -> dict:
    """Regenerate composite science; never copy caller-authored prose or scripts."""
    from . import __version__
    from .api import analyze
    from .simulation_lab import normalize_simulation
    stored=result.get("provenance",{})
    request=result["normalized_request"]
    if stored.get("engine_version") != __version__:
        raise ValueError("Historical composites require their original engine; recalculate before sharing")
    replay=analyze(request)
    if replay.get("status") != "complete" or stored.get("method_id") != replay["provenance"]["method_id"] or stored.get("method_version") != replay["provenance"]["method_version"]:
        raise ValueError("Composite method provenance does not match this implementation")
    if request["operation"] == "compare":
        if request.get("execution") != "analytic":
            raise ValueError("Only portable analytic comparisons currently support anonymous sharing")
        if result.get("deltas") != replay["deltas"]:
            raise ValueError("Stored comparison deltas do not match reproduction")
        clean_plans={}
        for key in ("planA","planB"):
            original=result.get(key,{})
            if not isinstance(original,dict):
                raise ValueError("Stored comparison plans must be scientific objects")
            if original.get("result") != replay[key]["result"]:
                raise ValueError("Stored comparison plan does not match reproduction")
            clean_plans[key]=anonymous_snapshot(replay[key])["normalized_request"]
        sanitized={"operation":"compare","execution":"analytic",**clean_plans}
    else:
        excluded={"provenance","reproduction","browser_execution","record_verification"}
        if {k:v for k,v in result.items() if k not in excluded} != {k:v for k,v in replay.items() if k not in excluded}:
            raise ValueError("Stored simulation does not match reproduction")
        sanitized={"operation":"simulate","payload":normalize_simulation(request["payload"])}
    fresh=replay if sanitized == replay["normalized_request"] else analyze(sanitized)
    values=composite_numeric_claims(fresh)
    return {"schema_version":"1.0","anonymization_version":"1.3","status":"complete","operation":sanitized["operation"],
            "normalized_request":fresh["normalized_request"],"result":values,
            "provenance":{"engine_version":__version__,"method_id":fresh["provenance"]["method_id"],"method_version":fresh["provenance"]["method_version"],"input_sha256":input_hash(fresh["normalized_request"])},
            "warnings":["Identity, free text and source documents are excluded. Scientific details may reveal identity. Replay before interpretation."],
            "reproduction":fresh.get("reproduction",[])}


def composite_numeric_claims(result: dict) -> dict:
    """Small comparison/simulation display protocol; full checks remain in replay."""
    if result.get("operation") == "compare":
        a,b=result["planA"]["result"],result["planB"]["result"]
        return {"n_total_a":a["n_total"],"n_total_b":b["n_total"],"power_a":a["power"],"power_b":b["power"],
                "delta_n_total":result["deltas"]["n_total"],"delta_recruitment_total":result["deltas"]["recruitment_total"],"delta_analytic_power":result["deltas"]["analytic_power"]}
    if result.get("operation") == "simulate":
        return {key:result[key] for key in ("power","type_i_error","replications","failures")}
    raise ValueError("A composite scientific result is required")
