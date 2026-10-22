"""Executable scripts and inspectable bundles; stored answers are never executable code."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

from .capabilities import R_MODELS
from .provenance import canonical_json


def python_script(request: dict, entrypoint: str = "analyze") -> str:
    from . import __version__
    if entrypoint not in {"analyze", "make_plan", "simulation"}:
        raise ValueError("Unknown reproduction entrypoint")
    imports = {"analyze": "from powerbench.api import analyze as calculate", "make_plan": "from powerbench.planning import make_plan as calculate", "simulation": "from powerbench.simulation_lab import run as calculate"}
    literal = repr(canonical_json(request))
    return (f"# Python 3.11+; install: python -m pip install powerbench=={__version__}\n"
            f"import json\n{imports[entrypoint]}\n"
            f"request = json.loads({literal})\nresult = calculate(request)\n"
            "print(json.dumps(result, indent=2, allow_nan=False))\n")


def r_script(request: dict) -> str | None:
    s = request["scenario"]
    model = s["model"]
    if model not in R_MODELS:
        return None
    e, d, rule = s["effect"], s["design"], s["decision_rule"]
    alt, alpha = rule["alternative"], float(rule["alpha"])
    key = {"two_sample_t": "cohens_d", "welch_t": "mean_difference", "paired_t": "cohens_dz", "correlation": "rho", "one_way_anova": "cohens_f"}.get(model, "cohens_f2")
    # Only numeric literals and internally chosen operators enter the executable R body.
    header = f"# Base R independent implementation; matches the documented PowerBench parameterization.\nalpha <- {alpha!r}\n"
    target = s.get("target_power")
    header += f"target <- {float(target) if target is not None else .95!r}\neffect <- {float(e.get(key, 1e-6))!r}\n"
    if model in {"two_sample_t", "paired_t", "welch_t"}:
        if model == "two_sample_t":
            params = "df <- n1+n2-2; delta <- effect/sqrt(1/n1+1/n2)"
        elif model == "paired_t":
            params = "df <- n1-1; delta <- effect*sqrt(n1)"
        else:
            a, b = float(e["sd_group1"]), float(e["sd_group2"])
            params = f"v1 <- {a!r}^2/n1; v2 <- {b!r}^2/n2; df <- (v1+v2)^2/(v1^2/(n1-1)+v2^2/(n2-1)); delta <- effect/sqrt(v1+v2)"
        tail = "c <- qt(1-alpha/2,df); pt(-c,df,delta)+pt(c,df,delta,lower.tail=FALSE)" if alt == "two.sided" else ("pt(qt(1-alpha,df),df,delta,lower.tail=FALSE)" if alt == "greater" else "pt(-qt(1-alpha,df),df,delta)")
        expression = params + "; " + tail
    elif model == "correlation":
        tail = "pnorm(-qnorm(1-alpha/2)-mu)+pnorm(qnorm(1-alpha/2)-mu,lower.tail=FALSE)" if alt == "two.sided" else ("pnorm(qnorm(1-alpha)-mu,lower.tail=FALSE)" if alt == "greater" else "pnorm(-qnorm(1-alpha)-mu)")
        expression = "mu <- sqrt(n1-3)*atanh(effect); " + tail
    else:
        if model == "one_way_anova":
            groups = int(d["groups"])
            expression = f"df1 <- {groups}-1; df2 <- n1-{groups}; lambda <- n1*effect^2; "
        else:
            total = int(d["predictors"] if model == "linear_regression" else d["total_predictors"])
            tested = total if model == "linear_regression" else (1 if model == "moderation" else int(d["tested_predictors"]))
            expression = f"df1 <- {tested}; df2 <- n1-{total}-1; lambda <- (n1-{total}+{tested})*effect; "
        expression += "pf(qf(1-alpha,df1,df2),df1,df2,ncp=lambda,lower.tail=FALSE)"
    header += "power_at <- function(n1,n2,effect) { " + expression + " }\n"
    sample = request.get("sample", {})
    op = request["operation"]
    two = model in {"two_sample_t", "welch_t"}
    if op == "plan":
        if two:
            header += f"n1 <- 2L; ratio <- {float(d.get('allocation_ratio', 1))!r}\nn2 <- max(2L,ceiling(n1*ratio))\n"
        else:
            minimum = 4 if model == "correlation" else (int(d["groups"]) * 2 if model == "one_way_anova" else int(d.get("predictors", d.get("total_predictors", 0))) + 2)
            header += f"n1 <- {minimum}L; n2 <- 0L\n"
        step = int(d["groups"]) if model == "one_way_anova" else 1
        header += f"while(power_at(n1,n2,effect)<target) {{ n1 <- n1+{step}L; if(n1>1e7) stop('Search budget exhausted'); "
        header += "n2 <- max(2L,ceiling(n1*ratio))" if two else "n2 <- 0L"
        header += " }\n"
    else:
        header += f"n1 <- {int(sample['n1'] if two else sample['n_total'])}L; n2 <- {int(sample['n2']) if two else 0}L\n"
    if op == "detectable_effect":
        domain = request.get("domain", {})
        direction = domain.get("direction", "negative" if alt == "less" else "positive")
        sign = -1 if direction == "negative" else 1
        lower, upper = float(domain.get("lower", 1e-8)), float(domain.get("upper", .999999 if key == "rho" else 10))
        header += f"effect <- {sign}*uniroot(function(x) power_at(n1,n2,{sign}*x)-target,c({lower!r},{upper!r}),tol=1e-10)$root\n"
    header += "power <- power_at(n1,n2,effect)\nn_total <- n1+n2\n"
    header += "cat(sprintf('{\"n_total\":%d,\"n1\":%d,\"n2\":%d,\"power\":%.17g,\"effect\":%.17g}\\n',n_total,n1,n2,power,effect))\n"
    return header


def reproduction(request: dict) -> list[dict]:
    result = [{"language": "python", "kind": "exact_reproduction", "code": python_script(request), "runtime": "Python 3.11+"}]
    script = r_script(request)
    if script:
        result.append({"language": "r", "kind": "matched_independent_check", "code": script, "runtime": "base R", "browser_status": "available_unverified_request", "tested_runtime_examples": "WebR 0.6.0 representative matrix"})
    return result


def export_bundle(result: dict) -> bytes:
    """Export science only. Caller must sanitize any user-authored free text before sharing."""
    from . import __version__
    if result.get("provenance", {}).get("engine_version") != __version__:
        raise ValueError("Historical bundles must be exported using their original engine version")
    from .versioning import METHOD_VERSIONS
    stored = result.get("provenance", {})
    if stored.get("method_id") in METHOD_VERSIONS and stored.get("method_version") != METHOD_VERSIONS[stored["method_id"]]:
        raise ValueError("Historical method version requires its original implementation for bundle export")
    request = result.get("normalized_request", result.get("scenario", {}))
    from .provenance import input_hash
    if stored.get("input_sha256") != input_hash(request):
        raise ValueError("Stored scientific input hash does not match the export request")
    if not stored.get("method_id") or not stored.get("method_version"):
        raise ValueError("Complete method provenance is required")
    from .api import analyze
    replay = analyze(request)
    if replay.get("status") != "complete" or replay.get("provenance", {}).get("method_id") != stored["method_id"] or replay.get("provenance", {}).get("method_version") != stored["method_version"]:
        raise ValueError("Stored method provenance does not match this implementation")
    # Legacy wizard records use reference for their canonical numeric result.
    # A present result key must never fall back merely because it is falsey.
    legacy = "result" not in result and "reference" in result
    saved_result = result.get("reference") if legacy else result.get("result")
    if legacy and (request.get("operation") != "plan" or not isinstance(saved_result, dict)):
        raise ValueError("Legacy export requires a canonical plan request and reference result")
    if replay.get("result") != saved_result:
        raise ValueError("Stored result does not match its scientific reproduction")
    # Reconstruct every executable/reporting artifact from the validated request.
    # Stored prose, scripts, citations and dependency strings are untrusted, even
    # when their numeric result still matches. Do not mutate the saved record.
    result = replay
    result["provenance"].pop("execution", None)
    request = result["normalized_request"]
    legacy_note = ("Legacy wizard records are exported here as their canonical scientific calculation. "
                   "Legacy simulation diagnostics and assumption sweeps are not included in this calculation bundle; "
                   "their full make_plan reproduction remains available in the original planner result.\n\n") if legacy else ""
    entries = {
        "README.md": "# Reproduce this analysis\n\nThis bundle was recomputed from the normalized request using the stated engine and method. Stored prose, scripts, citations and dependency strings were regenerated; the saved original was not modified.\n\nCreate a fresh Python environment, install requirements.lock.txt, then run reproduce.py. R, when supplied, is an independent implementation under the stated assumptions. Numerical agreement does not certify the design.\n",
        "request.json": json.dumps(request, indent=2, allow_nan=False),
        "result.json": json.dumps(result, indent=2, allow_nan=False),
        "provenance.json": json.dumps(result.get("provenance", {}), indent=2),
        "report.md": "# Scientific calculation\n\n" + result.get("reporting", {}).get("apa", "") + "\n\nInputs, results and software provenance are in request.json, result.json and provenance.json. Run reproduce.py to recalculate this canonical result.\n",
        "reporting.txt": result.get("reporting", {}).get("apa", ""),
        "requirements.lock.txt": "\n".join([f"powerbench=={__version__}"] + [f"{k}=={v}" for k, v in result.get("provenance", {}).get("dependencies", {}).items()]) + "\n",
    }
    if legacy_note:
        entries["README.md"] += "\n" + legacy_note
    entries["references.txt"] = "\n\n".join(item.get("source", "Source not yet verified") for item in result.get("citations", []))
    for item in result.get("reproduction", []):
        extension = "py" if item["language"] == "python" else "R"
        entries[f"reproduce.{extension}"] = item["code"]
    entries["manifest.json"] = json.dumps({"schema_version": "1.0", "bundle_policy_version": "1.1", "content_source": "recomputed_from_normalized_request", "files": {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in entries.items()}}, indent=2)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content.encode("utf-8"))
    return out.getvalue()
