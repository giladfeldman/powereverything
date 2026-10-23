"""Every public simulation template must produce ordinary strict JSON."""
import json

import pytest

from powerbench.api import analyze
from powerbench.simulation_lab import TEMPLATES


@pytest.mark.parametrize("template",sorted(TEMPLATES))
def test_simulation_result_is_strict_json_without_encoder_fallback(template):
    result=analyze({"operation":"simulate","payload":{"template_id":template,"replications":2}})
    wire=json.loads(json.dumps(result,allow_nan=False))
    assert wire["normalized_request"]["payload"]["template_id"]==template
    assert wire["replications"]==2
