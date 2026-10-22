"""Sonnet 2026-10-22 findings, reproduced before correction."""
import math

import pytest

from powerbench.references import paired_t_power, welch_t_power
from powerbench.review.assistant import validate_assistance
from powerbench.review.prompts import validate_extraction


@pytest.mark.parametrize('source,field,value',[
 ('pwr.t.test(n=20*2,d=.5,sig.level=.05/3,type="two.sample")','n_per_group',20),
 ('pwr.t.test(n=20:30,d=.5,sig.level=.05,type="two.sample")','n_per_group',20),
 ('pwr.t.test(n=20,d=.5,sig.level=.05/3,type="two.sample")','alpha',.05),
 ('TTestIndPower().power(nobs1=20,effect_size=.5,alpha=.05,ratio=1/2)','n_per_group',20),
 ('pwr.t.test(n=30,d=.5,type="paired");pwr.t.test(n=20,d=.5,type="two.sample")','n_per_group',30),
 ('pwr.t.test(n=20,d=.5,type="one.sample") # type="two.sample"','n_per_group',20),
 ('geom_point(alpha=.3)','alpha',.3),
 ('pwr.t.test(d=.5,power=.8,sig.level=.05) # n=20','goal','achieved_power'),
])
def test_code_requires_a_single_literal_supported_call(source,field,value):
 result=validate_assistance('code',source,{'fields':{field:value},'evidence':{field:{'quote':source}},'findings':[]})
 assert result['fields'][field]['value'] is None

@pytest.mark.parametrize('text,field,value',[
 ('alpha = .05, power = .80, d = 0.5','effect',.8),
 ("Cronbach's alpha was .87.",'alpha',.87),
 ('Observed power was .35.','target_power',.35),
 ('alpha = .05/3','alpha',.05),
 ('The statistic was F = 4.5.','effect_metric','cohens_f'),
 ('We used a two-sample Welch t-test.','model','two_sample_t'),
 ('Welch was not used.','model','welch_t'),
])
def test_extraction_requires_the_correct_label_and_meaning(text,field,value):
 result=validate_extraction(text,{'has_power_analysis':True,'analyses':[{'fields':{field:{'value':value,'quote':text,'start':0,'end':len(text),'status':'reported'}}}]})
 assert result['analyses'][0]['fields'][field]['value'] is None

@pytest.mark.parametrize('paragraph',[
 'Sample sizes of 20-300 were considered. [effect rationale needed]',
 'The effect range was 0.2–0.8. [effect rationale needed]',
 'The sample was 1,200. [effect rationale needed]',
 'The effect d was 20. [effect rationale needed]',
 'The sample was 2000. [effect rationale needed]',
 'The sample was determined in advance. [effect rationale needed]',
])
def test_rewrite_does_not_hide_numbers_or_invent_chronology(paragraph):
 confirmed={'n':20,'effect':.2,'chronology':'unknown','effect_rationale':None}
 with pytest.raises(ValueError):validate_assistance('rewrite','A draft.',{'paragraph':paragraph,'confirmed':confirmed},confirmed)

@pytest.mark.parametrize('code,quote',[
 ('missing_alpha','alpha = .05'),('observed_effect_posthoc','the')
])
def test_finding_quote_cannot_contradict_its_code(code,quote):
 text='In the analysis, alpha = .05. This describes the design.'
 result=validate_assistance('audit',text,{'findings':[{'code':code,'quote':quote,'suggestion':'Unsupported claim.'}]})
 assert result['findings']==[]

@pytest.mark.parametrize('n,effect',[(2,6),(4,6),(10,4)])
def test_paired_t_rejects_neither_finite_tail_nor_its_reflection(n,effect):
 positive=paired_t_power(n,effect,.05,'two.sided')
 assert math.isfinite(positive)
 assert positive==pytest.approx(paired_t_power(n,-effect,.05,'two.sided'),abs=1e-12)

@pytest.mark.parametrize('n,effect',[(3,10),(4,8),(10,4)])
def test_welch_t_uses_finite_reflected_tails(n,effect):
 positive=welch_t_power(n,n,effect,1,1,.05,'two.sided')
 assert math.isfinite(positive)
 assert positive==pytest.approx(welch_t_power(n,n,-effect,1,1,.05,'two.sided'),abs=1e-12)

def test_snapshot_versions_describe_its_replay_environment():
 from powerbench.api import analyze
 from powerbench.schema import load_scenario
 from powerbench.sharing import anonymous_snapshot
 result=analyze({'operation':'plan','scenario':load_scenario('data/scenarios/two_sample_t_balanced.json').to_dict()})
 real=result['provenance']['dependencies']['scipy'];result['provenance']['dependencies']['scipy']='1.0.0'
 assert anonymous_snapshot(result)['provenance']['dependencies']['scipy']==real

def test_snapshot_cannot_smuggle_domain_free_text_into_a_plan():
 from powerbench.api import analyze
 from powerbench.schema import load_scenario
 from powerbench.sharing import anonymous_snapshot
 result=analyze({'operation':'plan','scenario':load_scenario('data/scenarios/two_sample_t_balanced.json').to_dict()})
 result['normalized_request']['domain']={'parameter':'PRIVATE_IDENTITY_MARKER'}
 try:snapshot=anonymous_snapshot(result)
 except ValueError:return
 import json
 assert 'PRIVATE_IDENTITY_MARKER' not in json.dumps(snapshot)


@pytest.mark.parametrize('n,effect',[(4,6),(10,4),(50,2)])
def test_mediation_joint_significance_uses_finite_path_tails(n,effect):
 from powerbench.references import mediation_indirect_power
 assert math.isfinite(mediation_indirect_power(n,effect,effect,.05))

@pytest.mark.parametrize('n,effect',[(4,6),(10,2),(50,4)])
def test_hk_meta_analysis_uses_finite_noncentral_tails(n,effect):
 from powerbench.specialist_extras import meta_analysis_random_power
 assert math.isfinite(meta_analysis_random_power(6,n,effect,.2,.05,'two.sided'))


def test_rewrite_cannot_hide_an_invented_quantity_in_number_words():
 confirmed={'reported_n':64,'chronology':'unknown','effect_rationale':None}
 with pytest.raises(ValueError):validate_assistance('rewrite','A draft.',{'confirmed':confirmed,'paragraph':'We enrolled sixty-five participants. [effect rationale needed]'},confirmed)

def test_sensitivity_rejects_injected_nonfinite_power_before_root_search(monkeypatch):
 import json
 from pathlib import Path

 from powerbench.api import analyze
 source=next(json.loads(path.read_text()) for path in (Path(__file__).parents[1]/'powerbench/resources/scenarios').glob('*.json') if json.loads(path.read_text())['model']=='paired_t')
 source['goal']='sensitivity';source['effect'].pop('cohens_dz')
 monkeypatch.setattr('powerbench.references.paired_t_power',lambda *args:float('nan'))
 with pytest.raises(ValueError,match='Numerical power'):analyze({'operation':'detectable_effect','scenario':source,'sample':{'n_total':20}})


def test_logrank_minimum_is_global_within_the_declared_discrete_rule():
 import json
 from pathlib import Path

 from powerbench.api import analyze
 from powerbench.specialist_extras import derive_logrank_event_probability
 source=next(json.loads(path.read_text()) for path in (Path(__file__).parents[1]/'powerbench/resources/scenarios').glob('*.json') if json.loads(path.read_text())['model']=='logrank_two_arm')
 source['target_power']=.06627943457127596
 source['effect']={'hazard_ratio':10,'p_event':derive_logrank_event_probability(10,.01,0,.5,0,.01)}
 source['design']={'allocation_ratio':.01,'control_hazard':.01,'followup_years':.5,'accrual_years':0,'dropout_hazard':0}
 result=analyze({'operation':'plan','scenario':source})
 assert result['result']['n_total']==4
 assert result['result']['power']>=source['target_power']
 assert 'approximation' in result['reporting']['apa'].lower()
