"""Confirmed follow-up review regressions; authored numeric boundary controls."""
import pytest

from powerbench.planning import scenario_from_fields
from powerbench.review import assistant_prompt


def logrank(**changes):
    return {"model":"logrank_two_arm","effect":1.5,"alpha":.05,"allocation_ratio":1,**changes}

def test_conflicting_logrank_aliases_are_not_silently_dropped():
    with pytest.raises(ValueError,match="Conflicting hazard"):
        scenario_from_fields(logrank(hazard_ratio=3))

def test_conflicting_event_and_hazard_inputs_fail_closed():
    with pytest.raises(ValueError,match="Conflicting event"):
        scenario_from_fields(logrank(p_event=.5,control_hazard=.1,followup_years=1))

def test_matching_event_and_hazard_inputs_are_preserved():
    from powerbench.specialist_extras import derive_logrank_event_probability
    event=derive_logrank_event_probability(1.5,.1,0,1,0,1)
    scenario,*_=scenario_from_fields(logrank(p_event=event,control_hazard=.1,followup_years=1))
    assert scenario.design["control_hazard"]==.1
    assert scenario.design["followup_years"]==1

def test_prompt_supplies_exact_canonical_json_for_hash_binding():
    from powerbench.provenance import canonical_json, input_hash
    confirmed={"a":1.0,"b":1e-7}
    prompt=assistant_prompt("rewrite","source",confirmed)
    assert prompt["confirmed_canonical_json"]==canonical_json(confirmed)
    assert input_hash(confirmed) in prompt["prompt"]
