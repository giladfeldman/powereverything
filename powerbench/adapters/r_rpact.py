"""R `rpact` adapter: group-sequential sample size for the two-sample t design.

rpact is a validated clinical-trials package that shares no code with gsDesign, so the
group-sequential scenario gets two genuinely independent external opinions. Unlike
gsDesign's normal-approximation base, `getSampleSizeMeans` computes the t-test sample
size, which lands one observation under PowerBench's exact-t sequential search (199 -> 100
per arm after per-arm ceiling, exactly PowerBench's 200 total) for the committed scenario.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

from .base import Adapter
from .r_pwr import _resolve_rscript
from ..parameterization import Parameterization
from ..schema import Scenario

_RPACT_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "group_sequential_t": Parameterization(
        effect_definition="Cohen's d at the final analysis",
        test_variant="Lan-DeMets O'Brien-Fleming alpha spending, efficacy stopping only",
        df_convention="asymptotic normal with sqrt(t_i / t_j) covariance",
        rounding_rule="ceiling per arm",
        allocation_support="balanced only",
        # tails_support undeclared: two-sided call path only, enforced by supports().
        notes=(
            "getDesignGroupSequential(typeOfDesign='asOF', sided=2) with "
            "getSampleSizeMeans's t-test sample size at the final look. Two-sided "
            "designs only in this adapter."
        ),
    ),
}


class RRpactAdapter(Adapter):
    id = "r.rpact"
    language = "r"
    version = "4.4.0"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "rpact_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _RPACT_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model != "group_sequential_t" or scenario.goal != "required_sample_size":
            return False
        if scenario.decision_rule.alternative != "two.sided":
            return False
        return float(scenario.design.get("allocation_ratio", 1.0)) == 1.0

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": "rpact adapter covers two-sided balanced group-sequential t designs only",
            }
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "scenario.json", Path(tmp) / "result.json"
            source.write_text(json.dumps(scenario.to_dict()), encoding="utf-8")
            try:
                call = subprocess.run(
                    [self.rscript, str(self.script), str(source), str(output)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError as error:
                return {"status": "unavailable", "adapter": self.id, "reason": f"R comparison could not start: {error}"}
            if call.returncode != 0:
                return {"status": "error", "adapter": self.id, "reason": call.stderr.strip() or call.stdout.strip()}
            result = json.loads(output.read_text(encoding="utf-8"))
        return {"status": "ok", "adapter": self.id, "language": self.language, **result}
