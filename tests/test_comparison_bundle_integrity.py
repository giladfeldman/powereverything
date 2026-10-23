from copy import deepcopy

import pytest

from powerbench.api import analyze
from powerbench.reproducibility import export_bundle


def test_comparison_bundle_rejects_tampered_deltas():
    fields={'model':'two_sample_t','effect':.4,'alpha':.05,'allocation_ratio':1,'attrition_rate':0,'target_power':.8}
    result=analyze({'operation':'compare','execution':'analytic','planA':fields,'planB':{**fields,'target_power':.95}})
    assert export_bundle(result)
    forged=deepcopy(result);forged['deltas']['n_total']=999
    with pytest.raises(ValueError,match='comparison'):
        export_bundle(forged)


def test_comparison_bundle_rejects_missing_or_tampered_plan_numeric_result():
    fields={'model':'two_sample_t','effect':.4,'alpha':.05,'allocation_ratio':1,'attrition_rate':0,'target_power':.8}
    result=analyze({'operation':'compare','execution':'analytic','planA':fields,'planB':fields})
    for alteration in ('missing','tampered'):
        forged=deepcopy(result)
        if alteration=='missing':forged.pop('planA')
        else:forged['planA']['result']['n_total']=999
        with pytest.raises(ValueError,match='comparison'):
            export_bundle(forged)
