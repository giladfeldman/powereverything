from copy import deepcopy

import pytest

from powerbench.review import extraction_prompt, review, validate_extraction
from powerbench.schema import load_scenario


def record():
    s=load_scenario("data/scenarios/two_sample_t_balanced.json").to_dict()
    return {"source_text":"The planned total sample was 200, with alpha .05 and power .80.", "confirmed":True,"confirmed_request":{"operation":"plan","scenario":s},"reported_value":200}


def test_review_no_default_confirmation_and_no_false_error_certification():
    r=record();r["confirmed"]=False
    assert review(r)["classification"]=="incomplete_reporting"
    r["confirmed"]=True;result=review(r)
    assert result["classification"]=="consistent_under_stated_assumptions"
    r["reported_value"]=100
    assert review(r)["classification"]=="possible_discrepancy"
    assert "not certify" in review(r)["explanation"]


def test_missing_source_values_not_filled_with_new_plan_defaults():
    r=record();del r["confirmed_request"]["scenario"]["target_power"]
    assert review(r)["classification"]=="incomplete_reporting"


def test_quote_match_checks_positions_not_model_confidence():
    text="Target power was .95."
    proposed={"has_power_analysis":True,"analyses":[{"fields":{"target_power":{"value":.95,"quote":".95","start":17,"end":20,"status":"reported"}}}]}
    valid=validate_extraction(text,proposed)
    assert valid["analyses"][0]["fields"]["target_power"]["quote_match"]=="verbatim"
    proposed["analyses"][0]["fields"]["target_power"]["quote"]=".80"
    invalid=validate_extraction(text,proposed)
    assert invalid["analyses"][0]["fields"]["target_power"]["status"]=="ambiguous"
    assert not invalid["analyses"][0]["fields"]["target_power"]["confirmed"]
    assert "untrusted" in extraction_prompt(text)["system"]
