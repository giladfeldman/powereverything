"""R `powerSurvEpi` adapter: Welch unequal-variance t sample size.

`ssizeWelchT` implements exactly PowerBench's Welch contract -- raw mean difference,
separate group SDs, Satterthwaite degrees of freedom, two-sided noncentral t -- and agrees
exactly (116/174) on the committed scenario, giving the Welch path a second independent
tool alongside pwrss.

The survival functions the package is named for (ssizeCT and relatives) use the Freedman
formula parameterized by per-arm event probabilities pE and pC. The committed log-rank
scenario declares only an overall p_event, which does not determine pE and pC, so this
adapter does not cover log-rank: answering would require inventing assumptions the
scenario does not state, and gsDesign's Schoenfeld implementation already matches the
scenario's declared formula exactly.
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

_POWERSURVEPI_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "welch_t": Parameterization(
        effect_definition="raw mean difference with separate group SDs",
        test_variant="noncentral t approximation, unequal variances",
        df_convention="Welch-Satterthwaite",
        rounding_rule="ceiling per group",
        allocation_support="any ratio",
        # tails_support undeclared: ssizeWelchT has no alternative argument at all, so the
        # tool is inherently two-sided and supports() declines one-sided scenarios.
        notes="ssizeWelchT solves the minimal n1 for a fixed n2/n1 ratio; two-sided only.",
    ),
}


class RPowerSurvEpiAdapter(Adapter):
    id = "r.powersurvepi"
    language = "r"
    version = "0.1.5"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "powersurvepi_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _POWERSURVEPI_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model != "welch_t" or scenario.goal != "required_sample_size":
            return False
        return scenario.decision_rule.alternative == "two.sided"

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "powerSurvEpi adapter covers the two-sided Welch t design only; its "
                    "survival functions need per-arm event probabilities the scenarios do "
                    "not declare"
                ),
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
