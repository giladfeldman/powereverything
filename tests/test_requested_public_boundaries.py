import io
import zipfile

import pytest

from powerbench.api import analyze
from powerbench.planning import scenario_from_fields
from powerbench.reproducibility import export_bundle
from powerbench.resources import example
from powerbench.sharing import anonymous_snapshot


@pytest.mark.parametrize('field,value',[('cluster_size',20),('icc',.05),('unit','schools')])
def test_unsupported_design_claim_is_rejected(field,value):
    source=example('two_sample_t_balanced');source['design'][field]=value
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_unadjusted_family_label_cannot_disagree_with_test_alpha():
    source=example('two_sample_t_balanced');source['design']['family_alpha']=.5
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_wizard_cannot_hide_multiple_unadjusted_primary_tests():
    with pytest.raises(ValueError):
        scenario_from_fields({'model':'two_sample_t','effect':.4,'alpha':.05,'allocation_ratio':1,'attrition_rate':0,'primary_tests':3})


def test_bundle_report_is_regenerated_and_not_empty():
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as bundle:
        assert result['reporting']['apa'].encode() in bundle.read('report.md')


def test_changed_stored_input_hash_cannot_hide_changed_recruitment():
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    result['normalized_request']['scenario']['design']['attrition_rate']=.2
    with pytest.raises(ValueError):export_bundle(result)


@pytest.mark.parametrize('value',[{},None])
def test_empty_snapshot_result_cannot_be_complete(value):
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')});result['result']=value
    with pytest.raises(ValueError):anonymous_snapshot(result)


def test_sensitivity_does_not_call_its_placeholder_an_assumption():
    source=example('two_sample_t_balanced');source['goal']='sensitivity'
    result=analyze({'operation':'detectable_effect','scenario':source,'sample':{'n1':30,'n2':30}})
    assert '1e-06' not in result['reporting']['distinctions']['target_effect']
    assert 'solved detectable effect' in result['reporting']['distinctions']['target_effect']


def test_bic_case_does_not_claim_a_cauchy_prior():
    source=example('bayes_factor_t_d040_bf3');source['design']['bf_method']='BIC'
    result=analyze({'operation':'plan','scenario':source})
    assert 'BIC-style approximate' in result['reporting']['apa']
    assert 'under the stated Cauchy prior' not in result['reporting']['apa']


def test_default_rope_threshold_is_reported_as_used():
    source=example('rope_equivalence_t_dbounds');source['design'].pop('rope_threshold')
    result=analyze({'operation':'plan','scenario':source})
    assert 'threshold 0.95' in result['reporting']['apa']
    assert 'threshold None' not in result['reporting']['apa']
