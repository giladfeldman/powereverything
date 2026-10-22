"""Required-N lower boundary and extreme noncentral-tail regressions."""
import math
from dataclasses import replace

import pytest

from powerbench.references import required_n_two_sample_t, two_sample_t_power
from powerbench.schema import load_scenario


@pytest.mark.parametrize('effect,target,expected',[(6,.8,2),(10,.999,3)])
def test_two_sample_minimum_includes_two_per_arm(effect,target,expected):
 scenario=replace(load_scenario('data/scenarios/two_sample_t_balanced.json'),effect={'cohens_d':effect},target_power=target)
 result=required_n_two_sample_t(scenario)
 assert result['n1']==result['n2']==expected
 assert result['power']>=target
 if expected>2:assert two_sample_t_power(expected-1,expected-1,effect,.05,'two.sided')<target

@pytest.mark.parametrize('n,effect',[(3,10),(4,8)])
def test_extreme_two_sided_tail_is_finite_and_symmetric(n,effect):
 positive=two_sample_t_power(n,n,effect,.05,'two.sided')
 negative=two_sample_t_power(n,n,-effect,.05,'two.sided')
 assert math.isfinite(positive) and 0<=positive<=1
 assert positive==pytest.approx(negative,abs=1e-14)


def test_extreme_two_sample_power_matches_independent_r_stats():
 import subprocess

 from powerbench.adapters.r_pwr import _resolve_rscript
 script='options(digits=17);for(d in c(6,8,10)) for(n in c(2,3,4)) cat(power.t.test(n=n,delta=d,sd=1,sig.level=.05,type="two.sample",alternative="two.sided",strict=TRUE)$power,"\\n")'
 run=subprocess.run([_resolve_rscript(),'-e',script],capture_output=True,text=True,check=True,timeout=45)
 expected=[float(value) for value in run.stdout.split()]
 actual=[two_sample_t_power(n,n,effect,.05,'two.sided') for effect in (6,8,10) for n in (2,3,4)]
 assert len(expected)==len(actual)==9
 assert actual==pytest.approx(expected,abs=1e-11)
