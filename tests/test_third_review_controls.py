import pytest

from powerbench.api import analyze
from powerbench.planning import make_plan
from powerbench.provenance import input_hash
from powerbench.resources import example
from powerbench.sharing import anonymous_snapshot


@pytest.mark.parametrize('value',[[2],{'value':2}])
def test_allocation_requires_numeric_scalar(value):
    source=example('two_sample_t_balanced');source['design']['allocation_ratio']=value
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_zero_followup_with_positive_accrual_remains_supported():
    result=make_plan({'model':'logrank_two_arm','effect':.7,'allocation_ratio':1,
        'control_hazard':.3,'accrual_years':2,'followup_years':0,'alpha':.05,'attrition_rate':0})
    assert result['reference']['n_total']>0


@pytest.mark.parametrize('mutation',['scenario_type','operation_missing'])
def test_rehashed_malformed_snapshot_is_a_validation_error(mutation):
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    if mutation=='scenario_type':result['normalized_request']['scenario']='x'
    else:result['normalized_request'].pop('operation')
    result['provenance']['input_sha256']=input_hash(result['normalized_request'])
    with pytest.raises(ValueError):anonymous_snapshot(result)


def test_default_logistic_design_is_disclosed():
    result=analyze({'operation':'plan','scenario':{'model':'logistic_regression','effect':{'odds_ratio':2,'p_baseline':.2},'design':{}}})
    assert result['reporting']['defaults_applied']['design.predictor_type']=='binary'
    assert result['reporting']['defaults_applied']['design.allocation_ratio']==1
    assert 'Defaulted assumptions' in result['reporting']['apa']


def test_poisson_fixed_predictor_assumption_is_disclosed():
    source={'model':'poisson_regression','effect':{'rate_ratio':2},'design':{'baseline_rate':1}}
    result=analyze({'operation':'plan','scenario':source})
    assert result['reporting']['defaults_applied']['design.exposure']==1
    assert 'balanced binary predictor' in result['reporting']['apa']


def test_effect_scalar_cannot_be_an_array():
    source=example('two_sample_t_balanced');source['effect']['cohens_d']=[.4]
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_undeclared_tost_true_difference_uses_disclosed_zero():
    source=example('tost_equivalence_dbounds');source['effect'].pop('true_difference',None)
    result=analyze({'operation':'plan','scenario':source})
    assert result['reporting']['defaults_applied']['effect.true_difference']==0


def test_supported_binary_and_continuous_logistic_controls():
    base={'model':'logistic_regression','effect':{'odds_ratio':2,'p_baseline':.2}}
    for design in ({'predictor_type':'binary','allocation_ratio':2},{'predictor_type':'continuous'}):
        result=analyze({'operation':'plan','scenario':{**base,'design':design}})
        assert result['status']=='complete' and result['result']['n_total']>0


def test_review_binary_missing_allocation_and_continuous_positive_control():
    from powerbench.review.engine import review
    request={'operation':'plan','scenario':{'model':'logistic_regression','target_power':.8,'effect':{'odds_ratio':2,'p_baseline':.2},'design':{'predictor_type':'binary'},'decision_rule':{'alpha':.05,'alternative':'two.sided','multiplicity_method':'none'}}}
    record={'mode':'calculate','confirmed':True,'source_text':'functional source','confirmed_request':request}
    missing=review(record)
    assert missing['status']=='incomplete' and 'allocation_ratio' in missing['reason']
    request['scenario']['design']['predictor_type']='continuous'
    assert review(record)['classification']=='calculation_only'


def test_unrepresentable_reported_value_is_validation_error():
    from powerbench.review.engine import review
    source=example('two_sample_t_balanced')
    with pytest.raises(ValueError):
        review({'mode':'compare','source_text':'functional source','confirmed':True,
                'confirmed_request':{'operation':'plan','scenario':source},'reported_value':10**400})
