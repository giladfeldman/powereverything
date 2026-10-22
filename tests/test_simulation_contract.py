import pytest

from powerbench.simulation_lab import normalize_simulation, run


def test_simulation_replay_freezes_defaults_and_seed():
    normalized=normalize_simulation({'template_id':'clustered_continuous_two_arm','replications':'5'})
    assert normalized['replications']==5
    assert normalized['seed']==20260718
    assert normalized['alpha']==.05

@pytest.mark.parametrize('change',[{'replications':True},{'replications':1.5},{'replications':10001},{'icc':float('nan')},{'n':10000000},{'unknown':3}])
def test_simulation_rejects_invalid_and_unbounded_requests(change):
    with pytest.raises(ValueError):
        normalize_simulation({'template_id':'clustered_continuous_two_arm',**change})

def test_invalid_grid_points_are_visible_and_never_clipped():
    result=run({'template_id':'clustered_continuous_two_arm','icc':.9,'replications':5,'seed':1})
    invalid=[point for point in result['sensitivity_grid'] if point['status']=='invalid']
    assert len(invalid)==3
    assert all(point['power'] is None and point['assumptions']['icc']==pytest.approx(1.125) for point in invalid)
    assert result['normalized_request']['payload']['seed']==1
