import json

import pytest

from powerbench.references import analytic_reference, chi_square_gof_power, chi_square_gof_w, paired_t_power, two_sample_t_power, welch_t_power
from powerbench.schema import load_scenario


def test_two_sample_reference_hits_target_and_is_minimal():
    scenario = load_scenario("data/scenarios/two_sample_t_balanced.json")
    result = analytic_reference(scenario)
    assert result["power"] >= scenario.target_power
    assert two_sample_t_power(result["n1"] - 1, result["n2"] - 1, scenario.effect["cohens_d"], 0.05, "two.sided") < scenario.target_power


def test_correlation_reference_hits_target():
    scenario = load_scenario("data/scenarios/correlation_two_sided.json")
    result = analytic_reference(scenario)
    assert result["n_total"] >= 4
    assert result["power"] >= scenario.target_power


def test_new_core_references_hit_their_targets():
    for path in [
        "data/scenarios/paired_t_dz_040.json",
        "data/scenarios/one_proportion_030_050.json",
        "data/scenarios/one_way_anova_f025_k3.json",
        "data/scenarios/linear_regression_f2_015_p3.json",
        "data/scenarios/two_proportions_030_050.json",
        "data/scenarios/incremental_regression_f2_015.json",
    ]:
        scenario = load_scenario(path)
        result = analytic_reference(scenario)
        assert result["n_total"] > 1
        assert result["power"] >= scenario.target_power


def test_paired_reference_is_minimal_for_default_case():
    scenario = load_scenario("data/scenarios/paired_t_dz_040.json")
    result = analytic_reference(scenario)
    assert paired_t_power(result["n_total"] - 1, scenario.effect["cohens_dz"], 0.05, "two.sided") < scenario.target_power


def test_incremental_regression_respects_full_model_degrees_of_freedom():
    scenario = load_scenario("data/scenarios/incremental_regression_f2_015.json")
    result = analytic_reference(scenario)
    assert result["power"] >= scenario.target_power
    assert result["n_total"] > 55


def test_welch_reference_matches_independent_r_stats_benchmarks():
    fixtures = json.loads(open("data/benchmarks/welch_t_r_stats.json", encoding="utf-8").read())["cases"]
    for fixture in fixtures:
        inputs, expected = fixture["inputs"], fixture["expected"]
        observed = welch_t_power(**inputs)
        assert observed == pytest.approx(expected["power"], abs=2e-12)


def test_welch_reference_hits_target_and_is_minimal_at_stated_allocation():
    scenario = load_scenario("data/scenarios/welch_t_heteroscedastic.json")
    result = analytic_reference(scenario)
    assert (result["n1"], result["n2"], result["n_total"]) == (116, 174, 290)
    assert result["power"] >= scenario.target_power
    assert welch_t_power(115, 173, 0.5, 1.0, 2.0, 0.05, "two.sided") < scenario.target_power
    assert result["method"] == "welch_satterthwaite_noncentral_t_approximation"


def test_chi_square_reference_matches_independent_r_stats_benchmark():
    fixture = json.loads(open("data/benchmarks/chi_square_gof_r_stats.json", encoding="utf-8").read())["cases"][0]
    inputs, expected = fixture["inputs"], fixture["expected"]
    assert chi_square_gof_w(inputs["p_null"], inputs["p_alternative"]) == pytest.approx(expected["cohens_w"], abs=2e-12)
    assert chi_square_gof_power(**inputs) == pytest.approx(expected["power"], abs=2e-12)


def test_chi_square_reference_hits_target_is_minimal_and_respects_expected_counts():
    scenario = load_scenario("data/scenarios/chi_square_gof_three_category.json")
    result = analytic_reference(scenario)
    assert result["n_total"] == 181
    assert result["power"] >= scenario.target_power
    assert result["min_expected_null_count"] >= 5
    assert chi_square_gof_power(180, scenario.effect["p_null"], scenario.effect["p_alternative"], 0.05) < scenario.target_power
