import pytest

from powerbench.api import analyze
from powerbench.planning import analyze_fields
from powerbench.resources import example
from powerbench.review.assistant import validate_assistance
from powerbench.review.engine import review
from powerbench.sharing import anonymous_snapshot


def logistic(design):
    return {'operation':'plan','scenario':{'model':'logistic_regression','target_power':.8,
        'effect':{'odds_ratio':2,'p_baseline':.2},'design':design,
        'decision_rule':{'alpha':.05,'alternative':'two.sided','multiplicity_method':'none'}}}


@pytest.mark.parametrize('ratio',[-.9,-1,0,'2'])
def test_logistic_allocation_is_positive_numeric(ratio):
    with pytest.raises(ValueError):analyze(logistic({'allocation_ratio':ratio}))


def test_unused_continuous_predictor_allocation_rejected():
    with pytest.raises(ValueError):analyze(logistic({'predictor_type':'continuous','allocation_ratio':3}))


@pytest.mark.parametrize('design',[{'control_hazard':.3},{'dropout_hazard':.1},{'accrual_years':2},{'followup_years':3}])
def test_partial_event_design_cannot_be_described_as_used(design):
    source=example('logrank_hr15_pevent06');source['design']=design
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_numeric_design_strings_are_validation_errors():
    source=example('two_sample_t_balanced');source['design']['allocation_ratio']='2'
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_bic_case_survives_anonymous_snapshot():
    source=example('bayes_factor_t_d040_bf3');source['design']['bf_method']='BIC'
    result=analyze({'operation':'plan','scenario':source})
    shared=anonymous_snapshot(result)
    assert shared['normalized_request']['scenario']['design']['bf_method']=='bic'
    assert 'BIC-style approximate' in shared['reporting']['apa']


@pytest.mark.parametrize('mutation',['hash','method'])
def test_snapshot_binds_original_input_and_method(mutation):
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    if mutation=='hash':result['normalized_request']['scenario']['design']['attrition_rate']=.2
    else:result['provenance']['method_id']='paired_t'
    with pytest.raises(ValueError):anonymous_snapshot(result)


def test_sample_fields_need_explicit_fixed_goal():
    with pytest.raises(ValueError):
        analyze_fields({'model':'two_sample_t','effect':.4,'alpha':.05,'target_power':.8,
                        'allocation_ratio':1,'attrition_rate':0,'n1':30,'n2':60})


@pytest.mark.parametrize('mutation',['analysable','recruitment','sidedness','alternative'])
def test_rewrite_cannot_swap_count_roles_or_sidedness(mutation):
    source=example('two_sample_t_balanced');source['design']['attrition_rate']=.1
    result=analyze({'operation':'plan','scenario':source})
    record={'canonical_request':result['normalized_request'],'canonical_result':result['result'],
            'canonical_paragraph':result['reporting']['apa'],'chronology':'unknown','effect_rationale':None}
    text=record['canonical_paragraph'];n=result['result']['n_total'];r=result['reporting']['distinctions']['recruitment_n']
    # Pair every mutation with acceptance of its exact unmutated source.
    baseline=validate_assistance('rewrite','source',{'paragraph':text+' [effect rationale needed]','confirmed':record},record)
    assert baseline['status']=='proposal_requires_confirmation'
    if mutation=='analysable':text=text.replace(f'analysable sample of {n}',f'analysable sample of {r}')
    if mutation=='recruitment':text=text.replace(f'recruitment target was {r}',f'recruitment target was {n}')
    if mutation=='sidedness':text+=' Tests were one-sided.'
    if mutation=='alternative':text=text.replace('alternative = two.sided','alternative = greater')
    assert text!=record['canonical_paragraph']
    with pytest.raises(ValueError):validate_assistance('rewrite','source',{'paragraph':text+' [effect rationale needed]','confirmed':record},record)


def test_review_does_not_infer_logistic_predictor_or_allocation():
    request=logistic({})
    result=review({'mode':'calculate','confirmed':True,'source_text':'source','confirmed_request':request})
    assert result['status']=='incomplete'
    assert 'predictor_type' in result['reason']


@pytest.mark.parametrize('name,key,phrase',[
    ('bayes_factor_t_d040_bf3','r_scale','Cauchy prior scale'),
    ('rope_equivalence_t_dbounds','prior_sd','normal prior SD')])
def test_used_default_prior_is_disclosed(name,key,phrase):
    source=example(name);source['design'].pop(key,None)
    result=analyze({'operation':'plan','scenario':source})
    assert phrase in result['reporting']['apa']
