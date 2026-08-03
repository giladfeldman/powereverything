from powerbench.simulation_lab import run, templates


def test_simulation_lab_templates_are_explicit_and_return_diagnostics():
    assert len(templates()) >= 10
    result = run({"template_id": "clustered_continuous_two_arm", "replications": 80, "seed": 12})
    assert result["classification"] == "simulation_first_exemplar_not_universal_calculator"
    assert result["preview_dataset"]
    assert 0 <= result["power"] <= 1
    assert 0 <= result["type_i_error"] <= 1
    assert len(result["sensitivity_grid"]) == 9


def test_new_simulation_lab_templates_smoke():
    payloads = {
        "factorial_2x2_continuous": {"n_per_cell": 12},
        "ancova_two_arm": {"n_per_arm": 15},
        "logistic_two_arm": {"n_per_arm": 20},
        "mediation_simple": {"n": 40},
        "mixed_model_two_arm_longitudinal": {"participants_per_arm": 20, "occasions": 3},
        "clustered_unequal_mar": {"clusters_per_arm": 6, "cluster_size_min": 5, "cluster_size_max": 12},
        "mixed_model_random_slopes": {"participants_per_arm": 12, "occasions": 4},
        "sem_two_mediators": {"n": 60},
    }
    assert set(payloads).issubset({template["id"] for template in templates()})
    for template_id, values in payloads.items():
        result = run({"template_id": template_id, **values, "replications": 50, "seed": 12})
        assert result["preview_dataset"]
        assert 0 <= result["power"] <= 1
        assert 0 <= result["type_i_error"] <= 1
        assert len(result["sensitivity_grid"]) == 9
