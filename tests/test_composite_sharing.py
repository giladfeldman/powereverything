"""Composite snapshots retain reproducible inputs, never document identity."""
from copy import deepcopy

import pytest

from powerbench.api import analyze
from powerbench.sharing import anonymous_snapshot, composite_numeric_claims


def comparison():
    fields={"model":"two_sample_t","effect":.4,"alpha":.05,"allocation_ratio":1}
    return analyze({"operation":"compare","execution":"analytic","planA":fields,"planB":{**fields,"attrition_rate":.2}})

def test_comparison_normalizes_both_portable_plans_and_replays():
    result=comparison()
    assert result["normalized_request"]["planA"]["scenario"]["design"]["attrition_rate"]==0
    assert analyze(result["normalized_request"])["deltas"]==result["deltas"]

def test_comparison_snapshot_strips_identity_and_preserves_numeric_claims():
    result=comparison();result["planA"]["reporting"]["apa"]="PRIVATE_MARKER"
    shared=anonymous_snapshot(result)
    assert "PRIVATE_MARKER" not in str(shared)
    assert shared["result"]==composite_numeric_claims(analyze(shared["normalized_request"]))
    altered=deepcopy(result);altered["deltas"]["n_total"]+=1
    with pytest.raises(ValueError,match="comparison deltas"):
        anonymous_snapshot(altered)

def test_simulation_snapshot_preserves_seed_and_replays_numeric_claims():
    result=analyze({"operation":"simulate","payload":{"template_id":"repeated_change_two_arm","replications":2,"participants_per_arm":4,"seed":42}})
    shared=anonymous_snapshot(result)
    assert shared["normalized_request"]["payload"]["seed"]==42
    assert shared["result"]==composite_numeric_claims(analyze(shared["normalized_request"]))
    altered=deepcopy(result);altered["power"]=-1
    with pytest.raises(ValueError,match="simulation"):
        anonymous_snapshot(altered)

def test_composite_snapshot_rejects_historical_provenance():
    result=comparison();result["provenance"]["method_version"]="0.0"
    with pytest.raises(ValueError,match="provenance"):
        anonymous_snapshot(result)
