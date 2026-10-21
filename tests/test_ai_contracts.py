"""AI proposals must not become verified scientific facts by parsing JSON."""
import pytest

from powerbench.review.prompts import validate_extraction


def test_numeric_value_not_supported_by_its_quote_is_not_promoted():
    text='The target power was 0.80.'
    result=validate_extraction(text,{'has_power_analysis':True,'analyses':[{'fields':{'target_power':{'value':.95,'quote':text,'start':0,'end':len(text),'status':'reported'}}}]})
    field=result['analyses'][0]['fields']['target_power']
    assert field['status']=='ambiguous'
    assert field['value'] is None
    assert field['proposed_value']==.95

def test_no_analysis_and_populated_analyses_are_inconsistent():
    with pytest.raises(ValueError,match='inconsistent|no.analysis'):
        validate_extraction('No power calculation.',{'has_power_analysis':False,'analyses':[{'fields':{}}]})


def test_code_without_matching_numeric_evidence_is_not_promoted():
    from powerbench.review.assistant import validate_assistance
    result=validate_assistance('code','pwr::pwr.t.test(n=100)',{'fields':{'n_per_group':200},'evidence':{'n_per_group':{'quote':'pwr::pwr.t.test(n=100)'}},'findings':[]})
    assert result['fields']['n_per_group']['value'] is None
    assert result['execution'].endswith('never executed.')


def test_invented_findings_are_rejected_instead_of_becoming_accusations():
    from powerbench.review.assistant import validate_assistance
    result=validate_assistance('audit','Alpha was .05.',{'findings':[{'code':'missing_alpha','quote':'Not in source'},{'code':'author_is_wrong','quote':'Alpha was .05.'}]})
    assert result['findings']==[]
    assert result['rejected_unsupported_findings']==2


def test_rewrite_preserves_unknown_rationale_and_confirmed_record():
    from powerbench.review.assistant import validate_assistance
    confirmed={'alpha':.05,'target_power':.8,'reported_n':100,'chronology':'unknown'}
    good={'paragraph':'With alpha .05 and target power .8, N=100 was considered. [effect rationale needed]','confirmed':confirmed}
    assert validate_assistance('rewrite','A draft.',good,confirmed)['status']=='proposal_requires_confirmation'
    for paragraph in ['An a-priori analysis used N=100. [effect rationale needed]','N=200. [effect rationale needed]','N=100.']:
        with pytest.raises(ValueError):validate_assistance('rewrite','A draft.',{**good,'paragraph':paragraph},confirmed)


def test_assistance_replay_reexecutes_public_parser():
    import json
    import subprocess
    import sys

    from powerbench.review.assistant import assistance_record
    result=assistance_record('audit','We used observed effects after data collection.',{'findings':[]})
    replay=subprocess.run([sys.executable,'-c',result['reproduction'][0]['code']],capture_output=True,text=True,check=True,timeout=120)
    assert json.loads(replay.stdout)['findings']==[]


def test_request_draft_never_invents_alpha_target_or_design_defaults():
    from powerbench.review.assistant import request_from_proposal
    draft=request_from_proposal({'fields':{'model':{'value':'two_sample_t','status':'reported'},'effect':{'value':.4,'status':'reported'}}})
    assert draft['request']['scenario']['target_power'] is None
    assert draft['request']['scenario']['decision_rule']['alpha'] is None
    assert draft['request']['scenario']['design']['allocation_ratio'] is None
    assert 'multiplicity_method' in draft['missing_fields']
