# ruff: noqa: TRY004
# Invalid JSON field types are ValueError by the portable request/HTTP 400 contract.
"""Deterministic checks of explicitly confirmed scientific records."""
from __future__ import annotations

from math import isfinite

from ..api import analyze
from ..provenance import input_hash

REVIEW_POLICY_VERSION = "1.0"


def review(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Review record must be an object")
    source = record.get("source_text", "")
    if not isinstance(source, str) or not source.strip() or len(source) > 100_000:
        raise ValueError("A source section of up to 100,000 characters is required")
    if record.get("confirmed") is not True:
        return {"status": "incomplete", "classification": "incomplete_reporting", "reason": "Confirm the source match and all calculation inputs before checking arithmetic."}
    request = record.get("confirmed_request")
    if not isinstance(request, dict):
        raise ValueError("A confirmed portable calculation request is required")
    if request.get("operation", "plan") not in {"plan", "power", "detectable_effect"}:
        raise ValueError("Review requires a plan, fixed-sample power, or detectable-effect request")
    # A stated value is required; no .95/.05 or sample defaults are inferred from prose.
    scenario = request.get("scenario", {})
    rule = scenario.get("decision_rule", {})
    required = {"model": scenario.get("model"), "alpha": rule.get("alpha"), "alternative": rule.get("alternative")}
    if request.get("operation", "plan") != "power":
        required["target_power"] = scenario.get("target_power")
    missing = [name for name, value in required.items() if value is None or value == ""]
    if missing:
        return {"status": "incomplete", "classification": "incomplete_reporting", "reason": "Not explicitly supplied: " + ", ".join(missing)}
    result = analyze(request)
    if result["status"] != "complete":
        return {"status": "unsupported", "classification": "unsupported_method", "calculation": result}
    reported = record.get("reported_value")
    if isinstance(reported, bool) or not isinstance(reported, (int, float)) or not isfinite(reported):
        raise ValueError("An explicit numeric reported value is required")
    op = result["operation"]
    field = "n_total" if op == "plan" else "power" if op == "power" else "detectable_effect"
    expected = result["result"][field]
    # Reporting precision must be declared by the reviewer. No blanket 2% N rule.
    digits = record.get("reported_decimal_places", 0 if field == "n_total" else None)
    if isinstance(digits, bool) or not isinstance(digits, int) or not 0 <= digits <= 10:
        raise ValueError("Declare the reported decimal places (0–10)")
    tolerance = .5 * 10 ** (-digits) if field != "n_total" else 0
    consistent = abs(reported - expected) <= tolerance + 1e-12
    classification = "consistent_under_stated_assumptions" if consistent else "possible_discrepancy"
    text = (f"The reported {field} ({reported:g}) is " + ("consistent with" if consistent else "different from") + f" the matched calculation ({expected:.10g}). This checks the confirmed assumptions; it does not certify the study or establish an author error.")
    return {"schema_version": "1.0", "review_policy_version": REVIEW_POLICY_VERSION, "status": "complete", "classification": classification,
            "arithmetic": {"field": field, "reported": reported, "recomputed": expected, "difference": reported - expected, "tolerance": tolerance},
            "source_completeness": "user_confirmed_not_independently_certified", "design_match": "user_confirmed", "source_sha256": input_hash(source),
            "explanation": text, "calculation": result, "suggestions": ["Justify the effect using a smallest effect of interest or documented evidence.", "Inspect a plausible range of effect and design assumptions.", "Verify sample units, allocation, missingness, multiplicity and the final analysis model."],
            "execution": "The deterministic calculation ran; uploaded user code was not executed."}
