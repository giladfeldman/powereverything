"""R `pwrss` adapter: independent cover for the generalized-outcome methods.

`pwr` cannot represent logistic, Poisson or ordinal regression, which is precisely where
PowerBench's own formulas were wrong before 2026-08-03. `pwrss` reaches them, so it is the
most valuable second opinion available for this engine.

The adapter passes an explicit Bernoulli(0.5) predictor. `pwrss.z.logreg` defaults to a
standard-normal predictor, which powers a one-SD change rather than a two-group contrast:
for OR = 1.5, p0 = 0.30 the default returns N = 249 against PowerBench's 856, and direct
`glm` Monte Carlo measures 0.31 power at 249. Matched on the predictor distribution, pwrss
returns 856 exactly. Comparing against the default and reporting the gap would be a
comparison error, not a finding.
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

_SUPPORTED = {"logistic_regression", "poisson_regression"}

_PWRSS_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "logistic_regression": Parameterization(
        effect_definition="odds ratio between two equally sized exposure groups",
        test_variant="Wald z on the slope (Demidenko 2007)",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        allocation_support="any ratio",
        tails_support="two.sided|greater|less",
        notes=(
            "Called with dist=list(dist='bernoulli', prob=0.5). The pwrss default is a "
            "standard-normal predictor, which powers a different estimand entirely."
        ),
    ),
    "poisson_regression": Parameterization(
        effect_definition="rate ratio between two equally sized groups",
        test_variant="Wald normal approximation on the log rate",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        tails_support="two.sided|greater|less",
        notes="Called with an explicit Bernoulli(0.5) predictor to match PowerBench.",
    ),
}


class RPwrssAdapter(Adapter):
    id = "r.pwrss"
    language = "r"
    version = "1.0.0"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "pwrss_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _PWRSS_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model not in _SUPPORTED or scenario.goal != "required_sample_size":
            return False
        if scenario.decision_rule.alternative != "two.sided":
            return False
        if scenario.model == "logistic_regression":
            # Only the balanced binary contract is comparable; a continuous predictor is a
            # different estimand and must be declined rather than silently matched.
            return str(scenario.design.get("predictor_type", "binary")) == "binary"
        return True

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "pwrss adapter covers two-sided logistic and Poisson regression with a "
                    "balanced binary predictor only"
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
