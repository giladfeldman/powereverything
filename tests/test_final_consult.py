"""Sonnet 2026-10-21 final consult: hypotheses reproduced before changes."""
import json
from pathlib import Path

import pytest

from powerbench.review.prompts import validate_extraction


@pytest.mark.parametrize('field,text,value',[
 ('alpha','power of 0.80',.8),('alpha','alpha = 0.05 with 95% confidence',.95),
 ('alternative','two-sided','greater'),('kind','After data collection using the observed effect','apriori')])
def test_extraction_quote_does_not_support_a_different_field(field,text,value):
 r=validate_extraction(text,{'has_power_analysis':True,'analyses':[{'fields':{field:{'value':value,'quote':text,'start':0,'end':len(text),'status':'reported'}}}]})
 assert r['analyses'][0]['fields'][field]['value'] is None

@pytest.mark.parametrize('tstat,expected',[(0,.21080814656165783),(3,10.383633506540969),(5,6033.227688169811)])
def test_jzs_matches_independent_adaptive_integral_and_r_bayesfactor(tstat,expected):
 from powerbench.specialist_extras import jzs_bf10_from_t
 assert jzs_bf10_from_t(tstat,50,50)==pytest.approx(expected,rel=1e-6)

def test_fractional_recruitment_count_is_rejected():
 from powerbench.recruitment import recruitment_counts
 with pytest.raises(ValueError,match='integer'):
  recruitment_counts({'n_total':12.9},.2)

def scenario(model):
 for p in (Path(__file__).parents[1]/'powerbench/resources/scenarios').glob('*.json'):
  value=json.loads(p.read_text(encoding='utf-8'))
  if value['model']==model:return value
 raise AssertionError(model)

def test_bayes_factor_search_evaluates_its_minimum():
 from powerbench.api import analyze
 s=scenario('bayes_factor_t');s['effect']['cohens_d']=5;s['design']['bf_method']='bic'
 assert analyze({'operation':'plan','scenario':s})['result']['n1']==10

def test_logrank_power_uses_reported_discrete_allocation():
 from powerbench.api import analyze
 from powerbench.specialist_extras import logrank_two_arm_power
 s=scenario('logrank_two_arm');s['effect'].update(hazard_ratio=5,p_event=1)
 r=analyze({'operation':'plan','scenario':s})['result']
 actual=logrank_two_arm_power(r['n_total'],5,1,.05,s['decision_rule']['alternative'],r['n2']/r['n1'])
 assert r['power']==pytest.approx(actual,abs=1e-12)
 assert r['power']>=s['target_power']


@pytest.mark.parametrize('model',['ordinal_regression','bayes_factor_t','meta_analysis_random','noninferiority_t'])
def test_search_floors_are_exposed_in_result_warnings_and_manuscript_draft(model):
 from powerbench.api import analyze
 r=analyze({'operation':'plan','scenario':scenario(model)})
 assert r['result']['search_domain']
 assert any('search domain' in warning for warning in r['warnings'])
 assert 'Search constraints:' in r['reporting']['apa']
