"""R `gsDesign` adapter: group-sequential designs and Schoenfeld log-rank events.

gsDesign is the established reference implementation for group-sequential boundary
computation, and `gsDesign::nEvents` is a direct implementation of the Schoenfeld
required-events formula -- the same formula PowerBench declares for the two-arm log-rank
scenario, which makes that comparison like-for-like.

The group-sequential base differs and is declared rather than hidden: gsDesign inflates a
fixed-design sample size from the asymptotic normal test (`nNormal`), while PowerBench
inflates the exact fixed-design t. Both apply Lan-DeMets O'Brien-Fleming spending, so the
answers differ by the normal-vs-t base (a few observations), not by the sequential
machinery: 198 vs 200 for the committed d = 0.40, two-look scenario.
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

_SUPPORTED = {"group_sequential_t", "logrank_two_arm"}

_GSDESIGN_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "group_sequential_t": Parameterization(
        effect_definition="Cohen's d at the final analysis",
        test_variant="Lan-DeMets O'Brien-Fleming alpha spending, efficacy stopping only",
        df_convention="asymptotic normal with sqrt(t_i / t_j) covariance",
        rounding_rule="ceiling per arm",
        allocation_support="balanced only",
        # tails_support undeclared: this adapter implements the two-sided call path only
        # (and supports() declines anything else), so a tails difference can never be the
        # explanation for a gap it produces.
        notes=(
            "gsDesign(test.type=2, sfu=sfLDOF) inflating nNormal's asymptotic-normal "
            "fixed N; PowerBench inflates the exact fixed-design t, so gsDesign sits a "
            "few observations lower (198 vs 200 at the committed scenario). Two-sided "
            "designs only in this adapter."
        ),
    ),
    "logrank_two_arm": Parameterization(
        effect_definition="hazard ratio under proportional hazards",
        test_variant="Schoenfeld required-events formula",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        notes=(
            "gsDesign::nEvents returns the required event count; the adapter applies "
            "N = ceiling(events / p_event), the same convention the scenario declares. "
            "Scenarios that derive p_event from accrual/follow-up are declined. "
            "Two-sided designs only in this adapter."
        ),
    ),
}


class RGsDesignAdapter(Adapter):
    id = "r.gsdesign"
    language = "r"
    version = "3.9.0"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "gsdesign_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _GSDESIGN_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model not in _SUPPORTED or scenario.goal != "required_sample_size":
            return False
        if scenario.decision_rule.alternative != "two.sided":
            return False
        if scenario.model == "group_sequential_t":
            return float(scenario.design.get("allocation_ratio", 1.0)) == 1.0
        # The R side divides events by a SUPPLIED p_event; a derived event probability
        # would need the accrual model reimplemented, which is PowerBench's own code and
        # therefore not an independent check.
        return "p_event" in scenario.effect
    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "gsDesign adapter covers two-sided balanced group-sequential t designs "
                    "and two-arm log-rank scenarios with a supplied p_event"
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
