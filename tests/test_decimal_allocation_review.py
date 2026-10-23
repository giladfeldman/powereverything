"""Integer allocation controls use a rational oracle, not replay agreement."""
import json
import subprocess
from fractions import Fraction

import pytest

from powerbench.api import analyze
from powerbench.references import two_sample_t_power


def boundary_request():
    target=(two_sample_t_power(99,109,.4,.05,'two.sided')+two_sample_t_power(100,110,.4,.05,'two.sided'))/2
    return {'operation':'plan','scenario':{'model':'two_sample_t','effect':{'cohens_d':.4},'design':{'allocation_ratio':1.1},'target_power':target}}


def test_decimal_allocation_does_not_add_a_spurious_participant():
    result=analyze(boundary_request())
    assert (result['result']['n1'],result['result']['n2'],result['result']['n_total'])==(100,110,210)
    assert result['result']['power']>=result['normalized_request']['scenario']['target_power']


def test_independent_base_r_uses_the_same_exact_decimal_allocation(tmp_path):
    from powerbench.adapters.r_pwr import _resolve_rscript
    result=analyze(boundary_request())
    script=next(row['code'] for row in result['reproduction'] if row['language']=='r')
    source=tmp_path/'decimal-allocation.R';source.write_text(script,encoding='utf-8')
    completed=subprocess.run([_resolve_rscript(),'--vanilla',str(source)],capture_output=True,text=True,timeout=30,check=True)
    actual=json.loads(completed.stdout.strip().splitlines()[-1])
    assert (actual['n1'],actual['n2'],actual['n_total'])==(100,110,210)


@pytest.mark.parametrize('ratio',[.1,.7,1.1,1.3,1.5,2.1,1.0000000000000002])
def test_allocation_grid_matches_an_independent_rational_oracle(ratio):
    from powerbench.allocation import allocated_arm_count
    r=Fraction(str(ratio))
    for first in [2,3,10,30,50,90,100,110,1000,10000]:
        value=r*first
        expected=max(2,-(-value.numerator//value.denominator))
        assert allocated_arm_count(first,ratio)==expected
