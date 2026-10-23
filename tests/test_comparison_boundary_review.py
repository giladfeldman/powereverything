"""Small review controls; no calibration reruns or external services."""

import pytest

from powerbench.planning import analyze_fields


@pytest.mark.parametrize('goal', ['achieved_power', 'sensitivity'])
def test_fixed_goal_preserves_declared_attrition_as_unapplied_metadata(goal):
    payload = {'model': 'two_sample_t', 'goal': goal, 'effect': .4, 'alpha': .05,
               'target_power': .8, 'allocation_ratio': 1, 'attrition_rate': .2,
               'n1': 30, 'n2': 30}
    result = analyze_fields(payload)
    assert result['result']['n_total'] == 60
    assert result['normalized_request']['scenario']['design']['attrition_rate'] == .2
    assert any('not applied' in warning for warning in result['warnings'])


def test_fixed_goal_zero_attrition_positive_control():
    result = analyze_fields({'model': 'two_sample_t', 'goal': 'achieved_power',
                             'effect': .4, 'alpha': .05, 'attrition_rate': 0,
                             'allocation_ratio': 1, 'n1': 30, 'n2': 30})
    assert result['result']['n_total'] == 60
    assert result['normalized_request']['scenario']['target_power'] is None


def test_exact_difference_contains_extreme_binomial_boundary(monkeypatch):
    from powerbench import comparison
    n=2000
    def plan(fields):
        successes=fields['successes']
        return {'reference': {'n_total': 200, 'power': .8},
                'simulation': {'power': successes/n, 'replications_completed': n},
                'recruitment_total': None}
    monkeypatch.setattr(comparison,'make_plan',plan)
    for first,second in [(0,2000),(1,2000),(0,1999)]:
        result=comparison.compare_fields({'planA':{'successes':first},'planB':{'successes':second}})
        low,high=result['deltas']['simulation_power_mc_ci95_conservative']
        assert low <= .99996 <= high
        assert 'Clopper-Pearson' in result['mc_difference_interval']['method']
        assert result['comparison_policy_version']=='1.1'


def test_exact_difference_degenerate_and_balanced_bounds(monkeypatch):
    from powerbench import comparison
    n=2000
    def plan(fields):
        return {'reference': {'n_total': 200, 'power': .8},'simulation': {'power': fields['successes']/n, 'replications_completed': n},'recruitment_total': None}
    monkeypatch.setattr(comparison,'make_plan',plan)
    for successes in (0,1000,2000):
        result=comparison.compare_fields({'planA':{'successes':successes},'planB':{'successes':successes}})
        low,high=result['deltas']['simulation_power_mc_ci95_conservative']
        assert -1 <= low < 0 < high <= 1


def test_analytic_comparison_never_invokes_simulation_or_external_process(monkeypatch):
    from powerbench import comparison
    from powerbench.api import analyze
    def forbidden(*args,**kwargs):
        raise AssertionError('Heavy make_plan path was invoked')
    monkeypatch.setattr(comparison,'make_plan',forbidden)
    fields={'model':'two_sample_t','effect':.4,'alpha':.05,'allocation_ratio':1,'attrition_rate':0,'target_power':.8}
    result=analyze({'operation':'compare','execution':'analytic','planA':fields,'planB':{**fields,'target_power':.95}})
    assert result['planA']['result']['n_total']==200
    assert result['planB']['result']['n_total']>200
    assert result['normalized_request']['execution']=='analytic'
    assert 'simulation_power' not in result['deltas']
    assert analyze(result['normalized_request'])['deltas']==result['deltas']


@pytest.mark.parametrize('payload',[[],{'operation':'power'},{'planA':{},'planB':{},'execution':[]},{'planA':{},'planB':{},'execution':'unknown'}])
def test_comparison_malformed_execution_is_a_validation_error(payload):
    from powerbench.comparison import compare_fields
    with pytest.raises(ValueError):
        compare_fields(payload)
