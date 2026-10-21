"""Follow-up Sonnet 2026-10-21 hypotheses, reproduced before correction."""
import json
from pathlib import Path

import pytest

from powerbench.api import analyze
from powerbench.reproducibility import export_bundle
from powerbench.sharing import anonymous_snapshot


def scenario(model):
    for path in (Path(__file__).parents[1]/'powerbench/resources/scenarios').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['model']==model:return data
    raise AssertionError(model)

@pytest.mark.parametrize('model,key,value',[
 ('one_sample_proportion','p_alternative',.1),('two_sample_proportion','p_group2',.1),
 ('meta_analysis_fixed','cohens_d',-.3),('meta_analysis_random','cohens_d',-.3),
 ('logistic_regression','odds_ratio',.7),('poisson_regression','rate_ratio',.7),
 ('ordinal_regression','odds_ratio',.7),('logrank_two_arm','hazard_ratio',.7),('group_sequential_t','cohens_d',-.4)])
def test_wrong_sided_plans_rejected_before_search(monkeypatch,model,key,value):
    from powerbench import search
    moments=iter([0,31]);monkeypatch.setattr(search,'monotonic',lambda:next(moments))
    s=scenario(model);s['effect'][key]=value;s['decision_rule']['alternative']='greater'
    with pytest.raises(ValueError,match='direction'):
        analyze({'operation':'plan','scenario':s})

def test_conflicting_logrank_event_models_are_rejected():
    s=scenario('logrank_two_arm');s['effect']['p_event']=.3
    s['design'].update(control_hazard=.1,followup_years=2,accrual_years=0)
    with pytest.raises(ValueError,match='event'):
        analyze({'operation':'plan','scenario':s})

def test_ignored_hartung_knapp_switch_rejected():
    s=scenario('meta_analysis_random');s['design']['hartung_knapp']=False
    with pytest.raises(ValueError,match='Hartung|hartung'):
        analyze({'operation':'plan','scenario':s})

def test_pooled_t_cannot_claim_unequal_variance():
    s=scenario('two_sample_t');s['design']['equal_variance']=False
    with pytest.raises(ValueError,match='equal_variance|pooled'):
        analyze({'operation':'plan','scenario':s})

def test_unadjusted_family_is_not_reported_as_controlled():
    s=scenario('two_sample_t');s['decision_rule']['multiplicity_method']='none';s['design'].update(primary_tests=3,family_alpha=.05)
    with pytest.raises(ValueError,match='family|multiplicity'):
        analyze({'operation':'plan','scenario':s})

def test_three_look_power_is_reproducible():
    from powerbench.specialist_extras import group_sequential_power
    values=[group_sequential_power(150,.4,3,.05,'two.sided') for _ in range(3)]
    assert values[0]==values[1]==values[2]

def test_export_missing_method_provenance_is_rejected():
    r=analyze({'operation':'plan','scenario':scenario('two_sample_t')})
    del r['provenance']['method_id'];del r['provenance']['method_version']
    with pytest.raises(ValueError,match='provenance|method'):
        export_bundle(r)

def test_export_forged_result_is_rejected():
    r=analyze({'operation':'plan','scenario':scenario('two_sample_t')});r['result']['n_total']+=2
    with pytest.raises(ValueError,match='match|reproduc'):
        export_bundle(r)

@pytest.mark.parametrize('model',['noninferiority_t','logistic_regression'])
def test_snapshot_retains_required_scientific_fields(model):
    s=scenario(model)
    if model=='logistic_regression':s['design']['predictor_type']='continuous'
    r=analyze({'operation':'plan','scenario':s})
    assert anonymous_snapshot(r)['result']['n_total']==r['result']['n_total']

def test_fit_failures_cannot_receive_compatible_badge():
    from powerbench.planning import _reference_simulation_alignment
    r=_reference_simulation_alignment({'power':.8},{'power':.8,'mc_ci95':[.7,.9],'failures':1})
    assert r['status']!='compatible'

def test_wizard_rejects_invalid_attrition_before_running_simulation():
    from powerbench.planning import scenario_from_fields
    with pytest.raises(ValueError,match='attrition'):
        scenario_from_fields({'model':'two_sample_t','effect':.4,'attrition_rate':1,'alpha':.05,'allocation_ratio':1})


@pytest.mark.parametrize('result,rate,expected',[({'n_total':21,'power':.8},.3,30),({'n_total':200,'n1':100,'n2':100,'power':.8},.25,268)])
def test_decimal_attrition_and_arm_rounding_are_explicit(monkeypatch,result,rate,expected):
    monkeypatch.setattr('powerbench.api.analytic_reference',lambda s:result)
    s=scenario('two_sample_t');s['design']['attrition_rate']=rate
    r=analyze({'operation':'plan','scenario':s})
    assert r['reporting']['distinctions']['recruitment_n']==expected


def test_mediation_calibration_examines_single_path_nulls():
    from powerbench.simulation_lab import run
    result=run({'template_id':'mediation_simple','n':30,'replications':8,'seed':31})
    checks=result['null_calibration']['boundary_cases']
    assert {item['zero_path'] for item in checks}=={'a_path','b_path'}
    assert all('mc_ci95' in item for item in checks)
