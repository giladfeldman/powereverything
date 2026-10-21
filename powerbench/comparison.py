# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Compare explicit plans without creating a preferred-method ranking."""
from .planning import make_plan
from .provenance import provenance
from .reproducibility import python_script


def compare_fields(request: dict) -> dict:
    if set(request) - {"operation", "planA", "planB"}:
        raise ValueError("Unrecognized comparison field")
    if not isinstance(request.get("planA"), dict) or not isinstance(request.get("planB"), dict):
        raise ValueError("Two explicit plans are required")
    a, b = make_plan(request["planA"]), make_plan(request["planB"])
    normalized = {"operation": "compare", "planA": request["planA"], "planB": request["planB"]}
    return {"schema_version": "1.0", "status": "complete", "operation": "compare", "planA": a, "planB": b,
            "deltas": {"n_total": b["reference"]["n_total"] - a["reference"]["n_total"], "analytic_power": b["reference"]["power"] - a["reference"]["power"], "simulation_power": b["simulation"]["power"] - a["simulation"]["power"]},
            "normalized_request": normalized, "provenance": provenance("plan_comparison", normalized, "1.0"),
            "reproduction": [{"language": "python", "kind": "exact_reproduction", "code": python_script(normalized)}]}
