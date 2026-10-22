import pytest

from powerbench.api import analyze
from powerbench.resources import example


def test_unsupported_effect_cannot_be_reported_as_used():
    source=example('two_sample_t_balanced');source['effect']['icc']=.05
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})


def test_inconsistent_derived_gof_effect_is_rejected():
    source=example('chi_square_gof_three_category');source['effect']['cohens_w']=.9
    with pytest.raises(ValueError):analyze({'operation':'plan','scenario':source})
