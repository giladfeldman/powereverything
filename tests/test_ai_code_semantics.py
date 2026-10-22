"""Quoted numbers must also match their code argument and sample unit."""
from copy import deepcopy
import pytest
from powerbench.review.assistant import validate_assistance

@pytest.mark.parametrize('source,field,value',[
 ('pwr::pwr.t.test(n=40,d=.4,sig.level=.05,type="paired")','n_per_group',40),
 ('TTestIndPower().power(nobs1=40,effect_size=.4,alpha=.05,ratio=2)','n_per_group',40),
 ('pwr::pwr.t.test(n=40,d=.4,sig.level=.05,type="two.sample")','effect',.05),
 ('pwr::pwr.t.test(n=40,d=.4,sig.level=.05,type="two.sample")','alpha',.4),
 ('pwr::pwr.t.test(n=40,d=.4,sig.level=.05,type="two.sample")','model','pwr.t.test'),
])
def test_matching_token_alone_is_insufficient(source,field,value):
 proposed={'fields':{field:value},'evidence':{field:{'quote':source}},'findings':[]}
 result=validate_assistance('code',source,proposed)
 assert result['fields'][field]['value'] is None
 assert result['fields'][field]['proposed_value']==value

@pytest.mark.parametrize('source',[
 'pwr::pwr.t.test(n=40,d=.4,sig.level=.05,type="two.sample")',
 'TTestIndPower().power(nobs1=40,effect_size=.4,alpha=.05,ratio=1)',
])
def test_balanced_code_retains_arguments_with_matching_units(source):
 fields={'model':'two_sample_t','n_per_group':40,'effect':.4,'alpha':.05,'goal':'achieved_power'}
 result=validate_assistance('code',source,{'fields':fields,'evidence':{field:{'quote':source} for field in fields},'findings':[]})
 assert {field:item['value'] for field,item in result['fields'].items()}==fields
