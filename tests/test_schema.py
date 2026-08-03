import json
import pytest

from powerbench.schema import load_scenario


def test_scenarios_validate():
    for name in ("two_sample_t_balanced.json", "two_sample_t_unbalanced.json", "welch_t_heteroscedastic.json", "chi_square_gof_three_category.json", "correlation_two_sided.json"):
        assert load_scenario(f"data/scenarios/{name}").id


def test_rejects_invalid_alpha(tmp_path):
    raw = json.loads(open("data/scenarios/two_sample_t_balanced.json", encoding="utf-8").read())
    raw["decision_rule"]["alpha"] = 1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="alpha"):
        load_scenario(path)


def test_welch_contract_rejects_equal_variance_and_missing_group_sd(tmp_path):
    raw = json.loads(open("data/scenarios/welch_t_heteroscedastic.json", encoding="utf-8").read())
    raw["design"]["equal_variance"] = True
    path = tmp_path / "not-welch.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="must not declare"):
        load_scenario(path)

    raw = json.loads(open("data/scenarios/welch_t_heteroscedastic.json", encoding="utf-8").read())
    raw["effect"].pop("sd_group2")
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="sd_group1 and sd_group2"):
        load_scenario(path)


def test_chi_square_contract_rejects_nonprobabilities_and_one_sided_rule(tmp_path):
    raw = json.loads(open("data/scenarios/chi_square_gof_three_category.json", encoding="utf-8").read())
    raw["effect"]["p_null"][0] = 0
    path = tmp_path / "bad-chi.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="strictly between"):
        load_scenario(path)

    raw = json.loads(open("data/scenarios/chi_square_gof_three_category.json", encoding="utf-8").read())
    raw["decision_rule"]["alternative"] = "greater"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="omnibus chi-square"):
        load_scenario(path)
