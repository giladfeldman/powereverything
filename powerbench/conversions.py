"""Named effect conversions with explicit, non-interchangeable assumptions."""
from math import exp, isfinite, log, pi, sqrt

from .provenance import provenance
from .reproducibility import python_script

CONVERSIONS = [
    {"from": "r_squared", "to": "cohens_f2", "formula": "f² = R² / (1 − R²)", "caveat": "Overall model R² only. An incremental block needs (R²full − R²reduced)/(1 − R²full)."},
    {"from": "cohens_f2", "to": "r_squared", "formula": "R² = f² / (1 + f²)", "caveat": "Overall model effect; not an incremental block's R²."},
    {"from": "r", "to": "cohens_d", "formula": "d = 2r / √(1 − r²)", "caveat": "Point-biserial relationship for two equally sized groups; not a general conversion for arbitrary continuous-variable correlations."},
    {"from": "cohens_d", "to": "r", "formula": "r = d / √(d² + 4)", "caveat": "Point-biserial relationship for two equally sized groups."},
    {"from": "cohens_d", "to": "odds_ratio", "formula": "OR = exp(d × π / √3)", "caveat": "Logistic latent-variable approximation, not an exact universal identity."},
    {"from": "odds_ratio", "to": "cohens_d", "formula": "d = ln(OR) × √3 / π", "caveat": "Reverse logistic latent-variable approximation."},
    {"from": "cohens_f", "to": "eta_squared", "formula": "η²p = f² / (1 + f²)", "caveat": "Partial eta squared for the tested term under matching definitions."},
    {"from": "eta_squared", "to": "cohens_f", "formula": "f = √(η²p / (1 − η²p))", "caveat": "Partial eta squared for the same tested term."},
]


def convert_effect(request: dict) -> dict:
    if set(request) - {"operation", "conversion", "value"}:
        raise ValueError("Unrecognized conversion field")
    index, value = request.get("conversion"), request.get("value")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(CONVERSIONS):
        raise ValueError("Choose a supported conversion")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Conversion requires a finite number")
    if index in {0, 7} and not 0 <= value < 1 or index in {1, 6} and value < 0 or index == 2 and not -1 < value < 1 or index == 5 and value <= 0:
        raise ValueError("Value is outside this conversion's domain")
    functions = [lambda x: x/(1-x), lambda x: x/(1+x), lambda x: 2*x/sqrt(1-x*x), lambda x: x/sqrt(x*x+4), lambda x: exp(x*pi/sqrt(3)), lambda x: log(x)*sqrt(3)/pi, lambda x: x*x/(1+x*x), lambda x: sqrt(x/(1-x))]
    converted = functions[index](value)
    if not isfinite(converted):
        raise ValueError("Conversion is outside the numeric range")
    normalized = {"operation": "convert_effect", "conversion": index, "value": value}
    return {"schema_version": "1.0", "status": "complete", "operation": "convert_effect", "normalized_request": normalized, "result": {**CONVERSIONS[index], "input": value, "value": converted}, "provenance": provenance("effect_conversion", normalized, "1.0"), "reproduction": [{"language": "python", "kind": "exact_reproduction", "code": python_script(normalized)}]}
