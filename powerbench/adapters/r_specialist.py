"""R adapters for specialist methods: TOSTER, metafor, MASS::polr.

These cover equivalence, random-effects meta-analysis and ordinal regression -- methods
`pwr` and `pwrss` cannot reach, and three of the paths where PowerBench's own formulas were
wrong before 2026-08-03. An independent second opinion is most valuable exactly where the
internal implementation was weakest.

Two of the three branches are Monte Carlo rather than closed form, because `metafor` and
`MASS` are model fitters rather than power calculators. That is a strength for adjudication
-- a simulated fit of the actual model shares no approximation with the analytic reference
-- but it means the answers carry Monte Carlo resolution, reported in `assumptions` and
respected by the comparison tolerance. A Monte Carlo adapter is slow, so these are run by
the batch matrix refresh rather than on the request path.
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

#: Monte Carlo branches need a generous timeout: the bisection fits hundreds of models per
#: candidate sample size.
_TIMEOUT_SECONDS = 900

_SUPPORTED = {"tost_equivalence", "meta_analysis_random", "ordinal_regression"}

_SPECIALIST_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "tost_equivalence": Parameterization(
        effect_definition="equivalence bounds on the raw mean difference",
        test_variant="two one-sided t tests, exact",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling per group",
        allocation_support="any ratio",
        tails_support="two one-sided",
        notes="TOSTER::power_t_TOST. Symmetric bounds only in this adapter.",
    ),
    "meta_analysis_random": Parameterization(
        effect_definition="mean standardized mean difference with between-study SD tau",
        test_variant="Hartung-Knapp adjusted random-effects summary",
        df_convention="k - 1",
        rounding_rule="ceiling per group per study, Monte Carlo resolution +/- 8",
        allocation_support="balanced within study",
        tails_support="two.sided|greater|less",
        notes=(
            "metafor::rma(test='knha') Monte Carlo with tau2 fixed at the declared value. "
            "metafor is the reference implementation of the Hartung-Knapp adjustment."
        ),
    ),
    "ordinal_regression": Parameterization(
        effect_definition="proportional odds ratio between two equally sized groups",
        test_variant="proportional-odds cumulative logit fit, Wald z",
        df_convention="asymptotic normal",
        rounding_rule="ceiling, Monte Carlo resolution +/- 16",
        predictor_distribution="balanced binary",
        allocation_support="any ratio",
        tails_support="two.sided|greater|less",
        notes=(
            "MASS::polr Monte Carlo on a standard logistic latent variable cut at equally "
            "spaced thresholds, matching the PowerBench data-generating contract."
        ),
    ),
}

#: Monte Carlo branches cannot be compared at the 2% tolerance used for closed forms; the
#: bisection resolution alone is wider than that. Declared per method so the comparison
#: uses the tool's own stated precision rather than a single global number.
MONTE_CARLO_TOLERANCE: dict[str, float] = {
    "meta_analysis_random": 0.10,
    "ordinal_regression": 0.06,
}


class RSpecialistAdapter(Adapter):
    id = "r.specialist"
    language = "r"
    version = "TOSTER 0.8.6 / metafor 5.0.1 / MASS 7.3-60.2"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "specialist_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _SPECIALIST_PARAMETERIZATIONS.get(method_id, Parameterization())

    def tolerance_for(self, method_id: str, default: float = 0.02) -> float:
        """Comparison tolerance appropriate to how this tool produced its answer."""
        return MONTE_CARLO_TOLERANCE.get(method_id, default)

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model not in _SUPPORTED or scenario.goal != "required_sample_size":
            return False
        if scenario.model == "tost_equivalence":
            lower = float(scenario.effect.get("lower_bound", 0.0))
            upper = float(scenario.effect.get("upper_bound", 0.0))
            # Asymmetric bounds are a different design; decline rather than approximate.
            if abs(lower + upper) > 1e-9:
                return False
        if scenario.model == "meta_analysis_random":
            return int(scenario.design.get("studies", 0)) > 2
        return True

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "specialist adapter covers symmetric TOST equivalence, random-effects "
                    "meta-analysis with more than two studies, and ordinal proportional odds"
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
                    timeout=_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                return {
                    "status": "unavailable",
                    "adapter": self.id,
                    "reason": f"R comparison exceeded {_TIMEOUT_SECONDS}s",
                }
            except OSError as error:
                return {"status": "unavailable", "adapter": self.id, "reason": f"R comparison could not start: {error}"}
            if call.returncode != 0:
                return {"status": "error", "adapter": self.id, "reason": call.stderr.strip() or call.stdout.strip()}
            result = json.loads(output.read_text(encoding="utf-8"))
        return {"status": "ok", "adapter": self.id, "language": self.language, **result}
