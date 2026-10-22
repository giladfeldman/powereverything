import io
import zipfile

import pytest

from powerbench.api import analyze
from powerbench.planning import scenario_from_fields
from powerbench.reproducibility import export_bundle
from powerbench.resources import example


def test_paired_sensitivity_rejects_independent_arm_counts():
    source = example('paired_t_dz_040')
    source['goal'] = 'sensitivity'
    with pytest.raises(ValueError):
        analyze({'operation': 'detectable_effect', 'scenario': source,
                 'sample': {'n_total': 20, 'n1': 999, 'n2': 999}})


def test_export_bundle_cannot_export_replaced_code():
    result = analyze({'operation': 'plan', 'scenario': example('two_sample_t_balanced')})
    result['reproduction'] = [{'language': 'python', 'code': 'print("FORGED")\n'}]
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as bundle:
        assert 'FORGED' not in bundle.read('reproduce.py').decode()


def test_export_bundle_cannot_export_replaced_paragraph():
    result = analyze({'operation': 'plan', 'scenario': example('two_sample_t_balanced')})
    result['reporting']['apa'] = 'FORGED PARAGRAPH: N = 1'
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as bundle:
        assert 'FORGED' not in bundle.read('reporting.txt').decode()


def test_boolean_ratio_rejected_as_numeric_design():
    source = example('two_sample_t_balanced')
    source['design']['allocation_ratio'] = True
    with pytest.raises(ValueError):
        analyze({'operation': 'plan', 'scenario': source})


def test_fractional_wizard_group_count_rejected():
    with pytest.raises(ValueError):
        scenario_from_fields({'model': 'one_way_anova', 'groups': 2.9, 'effect': .25,
                              'alpha': .05, 'target_power': .8, 'attrition_rate': 0})


def test_frequentist_model_rejects_bayesian_framework_label():
    source = example('two_sample_t_balanced')
    source['framework'] = 'bayesian'
    with pytest.raises(ValueError):
        analyze({'operation': 'plan', 'scenario': source})


@pytest.mark.parametrize('operation, goal', [('power', 'achieved_power'), ('detectable_effect', 'sensitivity')])
def test_single_sample_shape_cannot_hide_independent_arms(operation, goal):
    source = example('paired_t_dz_040'); source['goal'] = goal
    with pytest.raises(ValueError):
        analyze({'operation': operation, 'scenario': source, 'sample': {'n_total': 20, 'n1': 10, 'n2': 10}})


def test_sensitivity_returns_the_validated_total_for_two_arms():
    source = example('two_sample_t_balanced'); source['goal'] = 'sensitivity'
    result = analyze({'operation': 'detectable_effect', 'scenario': source, 'sample': {'n1': 30, 'n2': 60}})
    assert result['result']['n_total'] == 90
    assert result['normalized_request']['sample'] == {'n1': 30, 'n2': 60, 'n_total': 90}


def test_bundle_does_not_trust_injected_dependency_or_citation_fields():
    result = analyze({'operation': 'plan', 'scenario': example('two_sample_t_balanced')})
    result['provenance']['dependencies']['unverified-package'] = 'https://example.invalid/wheel'
    result['citations'] = [{'source': 'FORGED CITATION'}]
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as bundle:
        assert b'unverified-package' not in bundle.read('requirements.lock.txt')
        assert b'FORGED' not in bundle.read('references.txt')


def test_bundle_is_stable_after_replay_and_does_not_mutate_saved_record():
    from copy import deepcopy
    result = analyze({'operation': 'plan', 'scenario': example('two_sample_t_balanced')})
    saved = deepcopy(result)
    assert export_bundle(result) == export_bundle(result)
    assert result == saved


def test_derived_total_respects_the_same_bound_as_explicit_total():
    from powerbench.power import sample_design
    with pytest.raises(ValueError, match="n_total"):
        sample_design("two_sample_t", {"n1": 6_000_000, "n2": 6_000_000})


@pytest.mark.parametrize("primary_tests", [0, False, "", None])
def test_explicit_invalid_primary_test_count_is_not_replaced_by_one(primary_tests):
    with pytest.raises(ValueError, match="primary_tests"):
        scenario_from_fields({"model": "two_sample_t", "effect": .4, "alpha": .05,
                              "allocation_ratio": 1, "attrition_rate": 0, "primary_tests": primary_tests})


def test_legacy_planner_bundle_exports_verified_canonical_calculation():
    import json
    from copy import deepcopy

    from powerbench.planning import make_plan
    result = make_plan({"model": "two_sample_t", "effect": .4, "alpha": .05,
                        "target_power": .8, "allocation_ratio": 1, "attrition_rate": 0})
    result["reporting"]["apa"] = "FORGED LEGACY PARAGRAPH"
    result["reproduction"] = [{"language": "python", "code": "FORGED LEGACY CODE"}]
    saved = deepcopy(result)
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as bundle:
        canonical = json.loads(bundle.read("result.json"))
        assert canonical["result"] == result["reference"]
        assert b"FORGED" not in bundle.read("reproduce.py")
        assert b"FORGED" not in bundle.read("reporting.txt")
        assert b"Legacy wizard" in bundle.read("README.md")
        assert b"simulation" in bundle.read("README.md")
    assert result == saved
    result["reference"]["n_total"] += 1
    with pytest.raises(ValueError, match="scientific reproduction"):
        export_bundle(result)
    result["reference"] = saved["reference"]
    result["result"] = None
    with pytest.raises(ValueError, match="scientific reproduction"):
        export_bundle(result)
