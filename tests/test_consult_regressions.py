"""Sonnet consult 2026-10-21 hypotheses: regressions must fail before fixes."""
import json
import subprocess
import sys

import pytest

from powerbench.api import analyze
from powerbench.planning import scenario_from_fields
from powerbench.references import analytic_reference
from powerbench.resources import example
from powerbench.sharing import anonymous_snapshot


def test_f1_wizard_respects_explicit_event_probability():
    scenario,*_=scenario_from_fields({'model':'logrank_two_arm','effect':.7,'p_event':.3,'allocation_ratio':1,'alpha':.05,'attrition_rate':0})
    result=analytic_reference(scenario)
    assert result['p_event']==pytest.approx(.3)


def test_f2_snapshot_preserves_nondefault_ordinal_baseline():
    scenario=example('ordinal_or15_k4');scenario['effect']['baseline_category_probs']=[.1,.2,.3,.4]
    original=analyze({'operation':'plan','scenario':scenario})
    snapshot=anonymous_snapshot(original)
    replay=analyze(snapshot['normalized_request'])
    assert replay['result']['n_total']==original['result']['n_total']
    assert snapshot['normalized_request']['scenario']['effect']['baseline_category_probs']==[.1,.2,.3,.4]


def test_f2_snapshot_rejects_a_forged_numeric_result():
    original=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    original['result']['n_total']+=100
    with pytest.raises(ValueError,match='result|replay|reproduc'):
        anonymous_snapshot(original)


@pytest.mark.parametrize('payload',[
 {'operation':'plan','scenario':{'model':'correlation','effect':{'rho':-.3},'decision_rule':{'alternative':'greater'}}},
 {'legacy':True,'fields':{'analysis_family':'paired_t','alpha':.05,'target_power':.8,'planned_n':30,'effect':.5,'alternative':'two-sided'}},
])
def test_f3_impossible_or_invalid_plans_terminate(payload):
    code='''import json,sys
q=json.loads(sys.argv[1])
try:
 if q.get('legacy'):
  from powerbench.review.legacy import check
  r=check({'fields':q['fields']});assert r['verdict']=='incomplete'
 else:
  from powerbench.api import analyze
  try:analyze(q)
  except ValueError:pass
  else:raise AssertionError('direction was accepted')
except AssertionError:raise
'''
    try:result=subprocess.run([sys.executable,'-c',code,json.dumps(payload)],capture_output=True,text=True,timeout=3,check=False)
    except subprocess.TimeoutExpired:pytest.fail('Unbounded planning request did not terminate')
    assert result.returncode==0,result.stderr


def test_f5_portable_plan_reports_attrition_recruitment():
    scenario=example('two_sample_t_balanced');scenario['design']['attrition_rate']=.25
    result=analyze({'operation':'plan','scenario':scenario})
    assert result['reporting']['distinctions']['recruitment_n']>result['result']['n_total']


def test_f6_hartung_knapp_text_matches_implemented_df():
    import inspect

    import powerbench.planning
    assert 'df = studies − 2' not in inspect.getsource(powerbench.planning)


def test_f7_sequential_rejects_unimplemented_unequal_allocation():
    scenario=example('group_sequential_t_d040_looks2');scenario['design']['allocation_ratio']=2
    with pytest.raises(ValueError,match='balanced|allocation'):
        analyze({'operation':'plan','scenario':scenario})


def test_f8_degenerate_simulation_cannot_claim_zero_failures():
    from powerbench.simulation_lab import run
    try:
        result=run({'template_id':'clustered_unequal_mar','clusters_per_arm':2,'cluster_size_min':1,'cluster_size_max':1,'mar_intercept':3,'replications':10,'seed':1})
    except ValueError:return
    assert result['failures']>0


def test_f13_welch_default_domain_scales_with_measurement_units():
    scenario=example('welch_t_heteroscedastic');scenario['goal']='sensitivity';scenario['effect'].update(sd_group1=100,sd_group2=100);scenario['target_power']=.8
    result=analyze({'operation':'detectable_effect','scenario':scenario,'sample':{'n1':50,'n2':50}})
    assert result['status']=='complete'
    assert 30<result['result']['detectable_effect']<80


def test_f4_multiplicity_without_explicit_family_information_is_rejected():
    scenario=example('two_sample_t_balanced');scenario['decision_rule']['multiplicity_method']='bonferroni'
    with pytest.raises(ValueError,match='family|multiplicity|primary'):
        analyze({'operation':'plan','scenario':scenario})


def test_f9_monte_carlo_intervals_retain_uncertainty_at_boundaries():
    from powerbench.simulation import _ci95
    from powerbench.simulation_lab import _ci
    assert _ci95(1,100)[1]<1
    assert _ci95(0,100)[2]>0
    assert _ci(0,100)[1]>0
    assert _ci(1,100)[0]<1


def test_f11_noninferiority_paragraph_describes_the_actual_test():
    result=analyze({'operation':'plan','scenario':example('noninferiority_t_margin05')})
    assert 'alternative = two.sided' not in result['reporting']['apa']
    assert 'one-sided' in result['reporting']['apa']


def test_f12_paragraph_retains_welch_scale_parameters():
    scenario=example('welch_t_heteroscedastic');scenario['effect'].update(sd_group1=1.23456789,sd_group2=2.34567891)
    result=analyze({'operation':'plan','scenario':scenario})
    assert '1.23456789' in result['reporting']['apa']
    assert '2.34567891' in result['reporting']['apa']


def test_f14_bundle_rejects_pairing_old_results_with_current_code():
    from powerbench.reproducibility import export_bundle
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    result['provenance']['engine_version']='0.8.2'
    with pytest.raises(ValueError,match='Historical|historical|version'):
        export_bundle(result)


def test_f15_request_does_not_claim_that_arbitrary_parity_was_validated():
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    script=next(x for x in result['reproduction'] if x['language']=='r')
    assert script['browser_status']=='available_unverified_request'


def test_f16_conversion_overflow_is_a_validation_error():
    with pytest.raises(ValueError,match='range'):
        analyze({'operation':'convert_effect','conversion':4,'value':1000})


def test_f7_one_look_sequential_search_is_minimal_under_its_normal_model():
    scenario=example('group_sequential_t_d040_looks2');scenario['design']['looks']=1
    result=analyze({'operation':'plan','scenario':scenario})
    assert result['result']['n_total']==198


def test_f10_review_distinguishes_domain_unreachable_from_unsupported():
    from powerbench.review import review
    scenario=example('two_sample_t_balanced');scenario['goal']='sensitivity'
    result=review({'source_text':'Explicitly confirmed sensitivity example.','confirmed':True,'confirmed_request':{'operation':'detectable_effect','scenario':scenario,'sample':{'n1':100,'n2':100},'domain':{'lower':.001,'upper':.01}},'reported_value':.1,'reported_decimal_places':2})
    assert result['classification']=='unreachable_in_declared_domain'


def test_f10_review_does_not_supply_unreported_allocation():
    from powerbench.review import review
    scenario=example('two_sample_t_balanced');scenario['design'].pop('allocation_ratio',None)
    result=review({'source_text':'Allocation was not reported.','confirmed':True,'confirmed_request':{'operation':'plan','scenario':scenario},'reported_value':200})
    assert result['classification']=='incomplete_reporting'


def test_f11_incompatible_noninferiority_alternative_is_rejected():
    scenario=example('noninferiority_t_margin05');scenario['decision_rule']['alternative']='two.sided'
    with pytest.raises(ValueError,match='one-sided|alternative'):
        analyze({'operation':'plan','scenario':scenario})


def test_f16_stored_conversion_requests_have_stable_named_identity():
    result=analyze({'operation':'convert_effect','conversion':0,'value':.2})
    assert result['normalized_request']['conversion']=='r_squared_to_cohens_f2'
    assert analyze(result['normalized_request'])['result']==result['result']


def test_f16_extreme_d_does_not_silently_convert_to_zero_correlation():
    result=analyze({'operation':'convert_effect','conversion':3,'value':1e308})
    assert result['result']['value']>.99


def test_f11_fixed_meta_analysis_actually_supports_one_sided_tests():
    # Refutes this part of the review: the function has a real one-sided branch.
    from powerbench.references import meta_analysis_fixed_power
    assert meta_analysis_fixed_power(2,20,.3,.05,'greater')>meta_analysis_fixed_power(2,20,.3,.05,'two.sided')
    scenario=example('meta_analysis_fixed_d030_k6');scenario['decision_rule']['alternative']='greater'
    assert 'alternative = greater' in analyze({'operation':'plan','scenario':scenario})['reporting']['apa']


def test_f3_budget_exhaustion_is_distinct_from_a_design_result(monkeypatch):
    from powerbench import search
    moments=iter([0,31]);monkeypatch.setattr(search,'monotonic',lambda:next(moments))
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    assert result['status']=='budget_exhausted'
    assert 'n_total' not in result['result']


def test_snapshot_rejects_historical_method_even_when_package_version_matches():
    result=analyze({'operation':'plan','scenario':example('group_sequential_t_d040_looks2')})
    result['provenance']['method_version']='2.0.0'
    with pytest.raises(ValueError,match='method version'):
        anonymous_snapshot(result)


def test_bundle_rejects_historical_method_even_when_package_version_matches():
    from powerbench.reproducibility import export_bundle
    result=analyze({'operation':'plan','scenario':example('group_sequential_t_d040_looks2')})
    result['provenance']['method_version']='2.0.0'
    with pytest.raises(ValueError,match='method version'):
        export_bundle(result)
