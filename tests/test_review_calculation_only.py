"""Confirmed code/manual assumptions can be calculated without a made-up claim."""
from copy import deepcopy
import pytest
from powerbench.review.engine import review
from powerbench.schema import load_scenario

def record():
 return {'mode':'calculate','source_text':'','confirmed':True,'confirmed_request':{'operation':'plan','scenario':load_scenario('data/scenarios/two_sample_t_balanced.json').to_dict()}}

def test_calculation_only_does_not_invent_a_reported_value_or_comparison():
 result=review(record())
 assert result['status']=='complete'
 assert result['classification']=='calculation_only'
 assert 'arithmetic' not in result
 assert result['calculation']['status']=='complete'
 assert result['calculation']['reproduction']
 assert result['calculation']['reporting']['ready_to_insert'] is False

@pytest.mark.parametrize('path',[('target_power',),('decision_rule','alpha'),('decision_rule','alternative'),('decision_rule','multiplicity_method')])
def test_calculation_only_review_never_inserts_missing_reported_assumptions(path):
 payload=record();target=payload['confirmed_request']['scenario']
 for part in path[:-1]:target=target[part]
 target.pop(path[-1],None)
 result=review(payload)
 assert result['status']=='incomplete'
 assert 'calculation' not in result

def test_comparison_still_requires_source_and_a_reported_numeric_value():
 payload=record();payload['mode']='compare'
 with pytest.raises(ValueError,match='source'):review(payload)
 payload['source_text']='A source section was supplied.'
 with pytest.raises(ValueError,match='reported value'):review(payload)

def test_calculation_requires_explicit_confirmation_and_never_executes_source():
 payload=record();payload['confirmed']=False
 assert review(payload)['status']=='incomplete'
 payload['confirmed']=True;payload['source_text']='raise RuntimeError("Uploaded source must never execute")'
 assert 'not executed' in review(payload)['execution']


def test_wizard_fixed_power_does_not_invent_a_target():
 from powerbench.planning import analyze_fields
 payload={'goal':'achieved_power','model':'two_sample_t','effect':.4,'alpha':.05,'alternative':'two.sided','n1':100,'n2':100}
 result=analyze_fields(payload)
 assert result['normalized_request']['scenario']['target_power'] is None
 assert analyze_fields({**payload,'target_power':.8})['normalized_request']['scenario']['target_power']==.8
