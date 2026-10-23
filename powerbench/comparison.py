# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Compare explicit plans without creating a preferred-method ranking."""
from scipy.stats import binomtest

from .planning import make_plan
from .provenance import provenance
from .reproducibility import python_script


def compare_fields(request: dict) -> dict:
    if not isinstance(request,dict) or request.get("operation","compare") != "compare":
        raise ValueError("A comparison request object is required")
    if set(request) - {"operation", "planA", "planB", "execution"}:
        raise ValueError("Unrecognized comparison field")
    if not isinstance(request.get("planA"), dict) or not isinstance(request.get("planB"), dict):
        raise ValueError("Two explicit plans are required")
    execution=request.get("execution", "simulation_checks")
    if not isinstance(execution,str) or execution not in {"simulation_checks", "analytic"}:
        raise ValueError("Comparison execution must be analytic or simulation_checks")
    if execution == "analytic":
        return _analytic_comparison(request)
    a, b = make_plan(request["planA"]), make_plan(request["planB"])
    # Clopper-Pearson marginal intervals plus Bonferroni give at least 95%
    # simultaneous coverage when replications within each plan are iid Bernoulli.
    # Dependence between the two plans is allowed. Fit failures invalidate a
    # claim about unconditional power; this interval does not resolve them.
    if any(plan["simulation"]["replications_completed"] <= 0 for plan in (a,b)):
        raise ValueError("Comparison needs successful simulation replications in both plans; all fits failed or no replications completed")
    intervals = [binomtest(round(plan["simulation"]["power"] * plan["simulation"]["replications_completed"]), plan["simulation"]["replications_completed"]).proportion_ci(confidence_level=.975, method="exact") for plan in (a, b)]
    interval = [float(intervals[1].low - intervals[0].high), float(intervals[1].high - intervals[0].low)]
    normalized = {"operation": "compare", "planA": request["planA"], "planB": request["planB"]}
    return {"schema_version": "1.0", "status": "complete", "operation": "compare", "planA": a, "planB": b,
            "comparison_policy_version": "1.1",
            "mc_difference_interval": {"method": "Bonferroni difference of 97.5% Clopper-Pearson binomial intervals", "confidence_level": .95, "assumptions": "Independent identically distributed Bernoulli replications within each plan; fit failures make estimates conditional on successful fits. No independence between plans is required."},
            "comparison_boundary": "Descriptive changes between the two declared designs; not a causal attribution or a ranking of methods.",
            "deltas": {"simulation_power_mc_ci95_conservative": interval, "recruitment_total": (b.get("recruitment_total") or b["reference"]["n_total"]) - (a.get("recruitment_total") or a["reference"]["n_total"]), "n_total": b["reference"]["n_total"] - a["reference"]["n_total"], "analytic_power": b["reference"]["power"] - a["reference"]["power"], "simulation_power": b["simulation"]["power"] - a["simulation"]["power"]},
            "normalized_request": normalized, "provenance": provenance("plan_comparison", normalized, "1.1"),
            "reproduction": [{"language": "python", "kind": "exact_reproduction", "code": python_script(normalized)}]}


def _analytic_comparison(request: dict) -> dict:
    """Portable analytic comparison; no simulation or external process is run."""
    from .api import analyze
    from .planning import scenario_from_fields
    plans=[]
    for key in ("planA", "planB"):
        fields=request[key]
        if fields.get("goal", "required_sample_size") != "required_sample_size" or any(fields.get(name) not in (None, "") for name in ("n1", "n2", "n_total")):
            raise ValueError("Analytic comparison currently requires two required-sample-size plans")
        if "scenario" in fields or "operation" in fields:
            if fields.get("operation") != "plan":
                raise ValueError("Portable comparison plans require operation=plan")
            plan=analyze(fields)
        else:
            scenario,*_=scenario_from_fields(fields)
            plan=analyze({"operation":"plan","scenario":scenario.to_dict()})
        if plan["status"] != "complete":
            raise ValueError("Both comparison plans must complete within the analytic search budget")
        plans.append(plan)
    a,b=plans
    normalized={"operation":"compare","execution":"analytic","planA":a["normalized_request"],"planB":b["normalized_request"]}
    return {"schema_version":"1.0","status":"complete","operation":"compare","comparison_policy_version":"1.4", "execution":"analytic",
            "planA":a,"planB":b,"deltas":{"recruitment_total":b["recruitment_counts"]["n_total"]-a["recruitment_counts"]["n_total"],"n_total":b["result"]["n_total"]-a["result"]["n_total"],"analytic_power":b["result"]["power"]-a["result"]["power"]},
            "comparison_boundary":"Descriptive analytic comparison of the declared designs. No Monte Carlo or external R checks were run. Differences are not causal attributions or method rankings.",
            "normalized_request":normalized,"provenance":provenance("plan_comparison",normalized,"1.4"),
            "reproduction":[{"language":"python","kind":"exact_reproduction","code":python_script(normalized)}]}
