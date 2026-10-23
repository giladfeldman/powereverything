import numpy as np
import pytest

from powerbench.json_values import json_values
from powerbench.provenance import input_hash
from powerbench.review.assistant import validate_assistance
from powerbench.review.evidence import finding_supported, labeled_numbers


def test_reliability_alpha_does_not_hide_reported_significance():
    text="Cronbach's alpha was .91. The significance level alpha was 0.05."
    assert labeled_numbers('alpha',text)==[.05]
    assert not finding_supported('missing_alpha',"Cronbach's alpha was .91",text)
    assert labeled_numbers('alpha',"Cronbach's alpha was .91")==[]


def test_numpy_extended_scalar_fails_explicitly_instead_of_recursing():
    value=np.longdouble(1.5)
    if isinstance(value.item(),np.generic):
        with pytest.raises(ValueError,match='precision'):json_values(value)
    else:assert json_values(value)==1.5


def test_masked_array_cannot_be_silently_exported_as_missing():
    with pytest.raises(ValueError,match='Masked'):json_values(np.ma.array([1.,2.],mask=[False,True]))


def test_rewrite_cannot_swap_total_and_per_arm_counts():
    paragraph="An independent two-sample t test requires N = 128 (64 per group), alpha = 0.05, target power = 0.95, effect d = 0.4."
    confirmed={'canonical_paragraph':paragraph,'canonical_request':{'scenario':{'model':'two_sample_t','effect':{'cohens_d':.4},'decision_rule':{'alpha':.05,'alternative':'two.sided'},'target_power':.95}},'canonical_result':{'n_total':128,'n1':64,'n2':64},'effect_rationale':'functional control','chronology':'unknown'}
    good={'paragraph':paragraph,'confirmed_sha256':input_hash(confirmed)}
    assert validate_assistance('rewrite','Functional source',good,confirmed)['paragraph']==paragraph
    bad={**good,'paragraph':paragraph.replace('N = 128 (64 per group)','N = 64 (128 per arm)')}
    with pytest.raises(ValueError):validate_assistance('rewrite','Functional source',bad,confirmed)
