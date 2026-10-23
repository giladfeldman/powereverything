"""Browser JSON loses a float's redundant .0 spelling, not its scientific value."""
import json

from powerbench.api import analyze
from powerbench.provenance import canonical_json
from powerbench.sharing import anonymous_snapshot


def browser_number(literal):
    value=float(literal)
    return int(value) if value.is_integer() else value

def test_integer_float_spellings_share_a_scientific_input_identity():
    assert canonical_json({"ratio":1.0,"zero":-0.0})==canonical_json({"ratio":1,"zero":0})

def test_browser_json_roundtrip_preserves_snapshot_input_hash():
    result=analyze({"operation":"plan","scenario":{"model":"two_sample_t","effect":{"cohens_d":.4},"design":{"allocation_ratio":1.0,"attrition_rate":0.0}}})
    wire=json.loads(json.dumps(result),parse_float=browser_number)
    shared=anonymous_snapshot(wire)
    assert shared["result"]["n_total"]==result["result"]["n_total"]
