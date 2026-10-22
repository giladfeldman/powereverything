import pytest

from powerbench.api import analyze
from powerbench.resources import example
from powerbench.review.assistant import validate_assistance


def confirmed():
    result=analyze({'operation':'plan','scenario':example('two_sample_t_balanced')})
    return {'canonical_request':result['normalized_request'],'canonical_result':result['result'],
            'canonical_paragraph':result['reporting']['apa'],'chronology':'unknown','effect_rationale':None}

@pytest.mark.parametrize('mutation',['pairs','per_group','paired_model','evidence','caveat'])
def test_rewrite_cannot_change_design_or_invent_evidence(mutation):
    record=confirmed();text=record['canonical_paragraph']
    if mutation=='pairs':text=text.replace('observations','complete pairs')
    if mutation=='per_group':text=text.replace('observations (','observations per group (')
    if mutation=='paired_model':text+=' We used a paired-samples t test.'
    if mutation=='evidence':text+=' This effect was informed by prior meta-analytic evidence.'
    if mutation=='caveat':text=text.replace('is a planning assumption.','was selected.')
    assert text != record['canonical_paragraph']
    with pytest.raises(ValueError):
        validate_assistance('rewrite','source',{'paragraph':text+' [effect rationale needed]','confirmed':record},record)
