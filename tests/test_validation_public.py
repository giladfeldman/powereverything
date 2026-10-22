from powerbench.contracts import normalize
from powerbench.resources import example
from powerbench.validation import adjudicate, evaluate_scenario


def test_no_external_result_does_not_claim_an_incapable_catalog():
    result = adjudicate([], {"power": .8}, None)
    assert result["verdict"] == "no_external_coverage"
    assert "returned" in result["summary"]
    assert "can represent" not in result["summary"]


def test_standalone_validation_accepts_a_scenario_without_app_paths():
    _, scenario = normalize({"operation": "plan", "scenario": example("two_sample_t_balanced")})
    result = evaluate_scenario(scenario, [])
    assert result["reference"]["n_total"] == 200
    assert result["simulation"]["replications"] == 4000
    assert result["tools"] == []
