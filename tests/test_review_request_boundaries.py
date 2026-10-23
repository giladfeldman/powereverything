"""Controls for strict planner fields, execution disclosure, and untrusted exports."""
from copy import deepcopy

import pytest

from powerbench.api import analyze
from powerbench.comparison import compare_fields
from powerbench.planning import make_plan, scenario_from_fields
from powerbench.reproducibility import export_bundle


def fields(**changes):
    return {"model":"two_sample_t","effect":.4,"alpha":.05,"allocation_ratio":1,**changes}

def test_default_attrition_and_target_are_explicit():
    scenario,*_=scenario_from_fields(fields())
    assert scenario.design["attrition_rate"]==0
    assert scenario.target_power==.95

@pytest.mark.parametrize("unknown",["dropout_hazrd","typo","p_baseline"])
def test_unknown_and_irrelevant_fields_fail_closed(unknown):
    with pytest.raises(ValueError,match="Unrecognized planner field"):
        scenario_from_fields(fields(**{unknown:.2}))

def test_make_plan_never_silently_ignores_fixed_goal():
    with pytest.raises(ValueError,match="required-sample-size"):
        make_plan(fields(goal="achieved_power",n1=20,n2=20))

def test_analytic_comparison_reports_recruitment_delta():
    result=compare_fields({"execution":"analytic","planA":fields(),"planB":fields(attrition_rate=.2)})
    assert result["deltas"]["n_total"]==0
    assert result["deltas"]["recruitment_total"]==82
    assert result["planA"]["execution_checks"]["monte_carlo"]=="not_run"
    assert result["comparison_policy_version"]=="1.4"

def test_no_successful_simulation_fits_is_an_explicit_error(monkeypatch):
    import powerbench.comparison as module
    monkeypatch.setattr(module,"make_plan",lambda _: {"simulation":{"power":0,"replications_completed":0}})
    with pytest.raises(ValueError,match="successful simulation replications"):
        compare_fields({"planA":{},"planB":{}})

def test_simulation_zip_rejects_modified_scientific_body():
    original=analyze({"operation":"simulate","payload":{"template_id":"repeated_change_two_arm","replications":2,"participants_per_arm":4}})
    assert export_bundle(original)
    for key in ("power","preview_dataset","null_calibration"):
        changed=deepcopy(original);changed[key]=None
        with pytest.raises(ValueError,match="Stored simulation"):
            export_bundle(changed)
