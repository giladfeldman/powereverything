"""Second focused Sonnet consult 2026-10-21; regression hypotheses exercised first."""
import pytest
from test_final_consult import scenario

from powerbench.review.assistant import validate_assistance
from powerbench.review.prompts import validate_extraction


def extract(name,value,text):
 return validate_extraction(text,{'has_power_analysis':True,'analyses':[{'fields':{name:{'value':value,'quote':text,'start':0,'end':len(text),'status':'reported'}}}]})['analyses'][0]['fields'][name]

def test_unicode_negative_effect_is_never_promoted_as_positive():
 assert extract('effect',.35,'r = −0.35')['value'] is None
 assert extract('effect',-.35,'r = −0.35')['value']==-.35

@pytest.mark.parametrize('name,value,text',[
 ('alternative','less','regardless'),('target_power',.8,'empower 0.8'),
 ('multiplicity_method','none','Participants were recruited online.'),
 ('model','paired_t','Participants were recruited online.'),
 ('effect_metric','cohens_d','Participants were recruited online.'),
 ('software','R','Participants were recruited online.'),
 ('n_unit','per_group','Participants were recruited online.')])
def test_categorical_and_keyword_grounding_needs_its_own_lexical_evidence(name,value,text):
 assert extract(name,value,text)['value'] is None

@pytest.mark.parametrize('chronology',['posthoc',None,'','unknown'])
@pytest.mark.parametrize('phrase',['a priori','prior to data collection','preregistered'])
def test_rewrite_cannot_introduce_unconfirmed_chronology(chronology,phrase):
 confirmed={'chronology':chronology,'effect_rationale':'x','alpha':.05}
 with pytest.raises(ValueError):validate_assistance('rewrite','A draft.',{'confirmed':confirmed,'paragraph':f'A {phrase} analysis used alpha .05.'},confirmed)

@pytest.mark.parametrize('name,value',[('model',77),('goal','made-up'),('model',None),('model','paired_t')])
def test_code_categories_are_typed_nonnull_and_matched(name,value):
 text='result <- pwr::pwr.t.test(n=100,d=.4,sig.level=.05,type="two.sample")'
 out=validate_assistance('code',text,{'fields':{name:value},'evidence':{name:{'quote':text}},'findings':[]})
 assert out['fields'][name]['value'] is None
 assert out['fields'][name]['status']=='ambiguous'

def test_derived_logrank_event_probability_uses_the_realized_arm_weights():
 from powerbench.api import analyze
 from powerbench.specialist_extras import (
  derive_logrank_event_probability,
  logrank_two_arm_power,
 )
 s=scenario('logrank_two_arm');s['effect']['hazard_ratio']=5
 s['design'].update(control_hazard=1,accrual_years=0,followup_years=.5,dropout_hazard=0)
 s['effect']['p_event']=derive_logrank_event_probability(5,1,0,.5,0,1)
 r=analyze({'operation':'plan','scenario':s})['result']
 actual=derive_logrank_event_probability(5,1,0,.5,0,r['n2']/r['n1'])
 assert r['p_event']==pytest.approx(actual,abs=1e-12)
 assert r['n_events']==pytest.approx(r['n_total']*actual)
 assert r['power']==pytest.approx(logrank_two_arm_power(r['n_total'],5,actual,.05,'two.sided',r['n2']/r['n1']))

def test_below_one_bayes_threshold_is_rejected_at_the_public_boundary():
 from powerbench.api import analyze
 s=scenario('bayes_factor_t');s['design'].update(bf_threshold=.09,r_scale=2)
 with pytest.raises(ValueError,match='threshold'):analyze({'operation':'plan','scenario':s})


@pytest.mark.parametrize('value',['false',0,1])
def test_variance_declaration_must_be_boolean(value):
 from powerbench.api import analyze
 s=scenario('two_sample_t');s['design']['equal_variance']=value
 with pytest.raises(ValueError,match='boolean'):analyze({'operation':'plan','scenario':s})

@pytest.mark.parametrize('value',[True,float('nan'),float('inf')])
def test_legacy_wizard_does_not_coerce_boolean_or_nonfinite_effects(value):
 from powerbench.planning import scenario_from_fields
 with pytest.raises(ValueError):scenario_from_fields({'model':'two_sample_t','effect':value,'target_power':.8,'alpha':.05,'allocation_ratio':1,'attrition_rate':0})
