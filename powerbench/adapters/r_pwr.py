from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .base import Adapter
from ..parameterization import Parameterization
from ..schema import Scenario

#: How R `pwr` defines what it computes, per method it supports. Declared so that a
#: numeric difference can be attributed rather than merely reported. Empty declarations are
#: treated as unknown, so a method omitted here can never have a gap explained away.
_PWR_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "two_sample_t": Parameterization(
        effect_definition="Cohen's d, difference in means over the pooled SD",
        test_variant="exact noncentral t, pooled variance",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support="two.sided|greater|less",
    ),
    "paired_t": Parameterization(
        effect_definition="Cohen's dz, standardized within-person change",
        test_variant="exact noncentral t",
        df_convention="n - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support="two.sided|greater|less",
    ),
    "chi_square_gof": Parameterization(
        effect_definition="Cohen's w over the null and alternative cell probabilities",
        test_variant="noncentral chi-square",
        df_convention="categories - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support="two.sided",
        notes="pwr.chisq.test applies no minimum expected cell count; PowerBench does.",
    ),
    "one_way_anova": Parameterization(
        effect_definition="Cohen's f across group means",
        test_variant="noncentral F, omnibus",
        df_convention="groups - 1 and N - groups",
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
    ),
    "linear_regression": Parameterization(
        effect_definition="Cohen's f-squared for the full model",
        test_variant="noncentral F, fixed predictors",
        df_convention="predictors and N - predictors - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="fixed (conditioned on the design matrix)",
        tails_support="two.sided",
    ),
    "incremental_regression": Parameterization(
        effect_definition="Cohen's f-squared for the tested block",
        test_variant="noncentral F, fixed predictors",
        df_convention="tested predictors and N - total predictors - 1; lambda uses u + v + 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="fixed (conditioned on the design matrix)",
        tails_support="two.sided",
    ),
    "correlation": Parameterization(
        effect_definition="Pearson r",
        test_variant="Fisher-z normal approximation",
        df_convention="n - 3",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support="two.sided|greater|less",
    ),
}


def _resolve_rscript(preferred: str = "Rscript") -> str:
    found = shutil.which(preferred)
    if found:
        return found
    roots = [Path(r"C:\Program Files\R"), Path(r"C:\Program Files (x86)\R")]
    for root in roots:
        if not root.exists():
            continue
        for candidate in sorted(root.glob("R-*/bin/Rscript.exe"), reverse=True):
            return str(candidate)
        for candidate in sorted(root.glob("R-*/bin/x64/Rscript.exe"), reverse=True):
            return str(candidate)
    return preferred


class RPwrAdapter(Adapter):
    id = "r.pwr"
    language = "r"
    version = "1.3.0"

    def __init__(self, rscript: str = "Rscript", script: str | Path | None = None):
        self.rscript = _resolve_rscript(rscript)
        self.script = Path(script or Path(__file__).parents[2] / "tools" / "r" / "pwr_adapter.R")

    def parameterization(self, method_id: str) -> Parameterization:
        return _PWR_PARAMETERIZATIONS.get(method_id, Parameterization())

    def supports(self, scenario: Scenario) -> bool:
        return (scenario.model in {"two_sample_t", "paired_t", "chi_square_gof", "one_way_anova", "linear_regression", "incremental_regression", "correlation"}
                and scenario.goal == "required_sample_size"
                and scenario.decision_rule.alternative == "two.sided"
                and (scenario.model != "two_sample_t" or scenario.design.get("allocation_ratio", 1.0) == 1.0))

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {"status": "unsupported", "reason": "pwr adapter supports matched two-sided t, correlation, one-way ANOVA, and overall-regression scenarios only"}
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "scenario.json", Path(tmp) / "result.json"
            source.write_text(json.dumps(scenario.to_dict()), encoding="utf-8")
            try:
                call = subprocess.run([self.rscript, str(self.script), str(source), str(output)], text=True, capture_output=True, check=False)
            except OSError as error:
                return {"status": "unavailable", "reason": f"R comparison could not start: {error}", "adapter": self.id}
            if call.returncode != 0:
                return {"status": "error", "reason": call.stderr.strip() or call.stdout.strip(), "adapter": self.id}
            result = json.loads(output.read_text(encoding="utf-8"))
        return {"status": "ok", "adapter": self.id, "language": self.language, **result}
