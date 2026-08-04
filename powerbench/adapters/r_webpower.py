"""R `WebPower` adapter: factorial ANOVA terms and simple mediation.

`wp.kanova` powers one term of a multi-way ANOVA with the same noncentral-F convention
PowerBench uses (error df = N - cells), so the factorial comparison is like-for-like and
agrees exactly (128) on the committed 2x2 interaction scenario.

`wp.mediation` is DELIBERATELY a different test: it powers the Sobel z on the product a*b
where PowerBench powers the joint-significance decision. Sobel is conservative, so
WebPower's N (183) exceeds PowerBench's (119) by design. The test variant is declared so
the classifier attributes the gap instead of reporting a defect -- and instead of the
adapter silently declining a comparison that carries real information about how the two
decision rules differ.
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

_SUPPORTED = {"factorial_anova", "mediation_indirect"}

_WEBPOWER_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "factorial_anova": Parameterization(
        effect_definition="Cohen's f for the tested term",
        test_variant="noncentral F for one term of a factorial design",
        df_convention="term df and N - cells",
        rounding_rule="ceiling per cell",
        allocation_support="balanced only",
        tails_support="two.sided",
        notes="wp.kanova with ndf = the tested term's df and ng = the cell count.",
    ),
    "mediation_indirect": Parameterization(
        effect_definition="standardized a and b path coefficients of the indirect effect",
        test_variant="Sobel z on the product a*b",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="random normal X",
        tails_support="two.sided",
        notes=(
            "A different decision rule from PowerBench's joint significance, declared as "
            "such: Sobel is conservative, so its N is expected to be larger (183 vs 119 "
            "at the committed scenario). Total variances are derived from PowerBench's "
            "standardized paths and residual SDs; c' = 0 designs only."
        ),
    ),
}


class RWebPowerAdapter(Adapter):
    id = "r.webpower"
    language = "r"
    version = "0.9.4"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "webpower_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _WEBPOWER_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model not in _SUPPORTED or scenario.goal != "required_sample_size":
            return False
        if scenario.decision_rule.alternative != "two.sided":
            return False
        if scenario.model == "factorial_anova":
            return str(scenario.design.get("tested_term", "")) in {"A", "B", "AB"}
        # wp.mediation's var(y) conversion assumes no direct path; a nonzero c' would
        # need covariance terms the committed contract does not exercise.
        return float(scenario.effect.get("direct_cprime", 0.0)) == 0.0

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "WebPower adapter covers two-sided balanced factorial ANOVA terms and "
                    "simple mediation with no direct path"
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
