"""An explicit pair distinguishes exact fractional intent from decimal input."""
import json
import subprocess
from fractions import Fraction

import pytest

from powerbench.allocation import (
    allocated_arm_count,
    declared_allocation_ratio,
    rounded_control_arm,
)
from powerbench.api import analyze
from powerbench.planning import analyze_fields, scenario_from_fields
from powerbench.references import two_sample_t_power


def test_exact_pair_and_decimal_are_distinct_declared_inputs():
    ratio=declared_allocation_ratio({"allocation_numerator":5,"allocation_denominator":3})
    assert allocated_arm_count(3,ratio)==5
    assert allocated_arm_count(3,5/3)==6
    assert allocated_arm_count(100,1.1)==110

def test_portable_pair_retains_exact_sample_size_and_independent_r_parameters(tmp_path):
    target=(two_sample_t_power(2,4,.4,.05,"two.sided")+two_sample_t_power(3,5,.4,.05,"two.sided"))/2
    result=analyze({"operation":"plan","scenario":{"model":"two_sample_t","effect":{"cohens_d":.4},"design":{"allocation_numerator":5,"allocation_denominator":3},"target_power":target}})
    assert (result["result"]["n1"],result["result"]["n2"])==(3,5)
    assert result["normalized_request"]["scenario"]["design"]["allocation_ratio"]==5/3
    code=next(row["code"] for row in result["reproduction"] if row["language"]=="r")
    assert "ratio_num <- 5; ratio_den <- 3" in code
    from powerbench.adapters.r_pwr import _resolve_rscript
    script=tmp_path/"fraction-pair.R";script.write_text(code,encoding="utf-8")
    output=subprocess.run([_resolve_rscript(),"--vanilla",str(script)],capture_output=True,text=True,check=True,timeout=30)
    actual=json.loads(output.stdout.strip().splitlines()[-1])
    assert (actual["n1"],actual["n2"])==(3,5)

def test_wizard_pair_and_fixed_counts_preserve_fractional_intent():
    scenario,*_=scenario_from_fields({"model":"two_sample_t","effect":.4,"alpha":.05,"allocation_ratio":"5:3"})
    assert scenario.design["allocation_numerator"]==5
    assert scenario.design["allocation_denominator"]==3
    fixed=analyze_fields({"model":"two_sample_t","goal":"achieved_power","effect":.4,"alpha":.05,"n1":3,"n2":5})
    assert fixed["normalized_request"]["scenario"]["design"]["allocation_numerator"]==5

@pytest.mark.parametrize("design",[{"allocation_numerator":5},{"allocation_numerator":True,"allocation_denominator":3},{"allocation_numerator":5,"allocation_denominator":0},{"allocation_numerator":5,"allocation_denominator":3,"allocation_ratio":2}])
def test_invalid_and_conflicting_pairs_fail_closed(design):
    with pytest.raises(ValueError):declared_allocation_ratio(design)

def test_total_split_matches_exact_half_up_oracle():
    for ratio in (Fraction(3,25),Fraction(1,10),Fraction(7,3),Fraction(1,1)):
        for total in range(4,201):
            first=Fraction(total)/(1+ratio)
            expected=max(2,min(total-2,(first+Fraction(1,2)).numerator//(first+Fraction(1,2)).denominator))
            assert rounded_control_arm(total,ratio)==expected


def test_review_logrank_rounding_counterexample_is_exact():
    assert int(67/(1+.072)+.5)==62
    assert rounded_control_arm(67,Fraction(72,1000))==63
