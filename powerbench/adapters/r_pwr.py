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
    "moderation": Parameterization(
        effect_definition="Cohen's f-squared for the interaction increment",
        test_variant="noncentral F, one tested predictor, fixed predictors",
        df_convention="1 and N - total predictors - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="fixed (conditioned on the design matrix)",
        tails_support="two.sided",
        notes="pwr.f2.test with u = 1; N reconstructed as v + total_predictors + 1.",
    ),
    "one_sample_proportion": Parameterization(
        effect_definition="Cohen's arcsine h, 2*asin(sqrt(p1)) - 2*asin(sqrt(p0))",
        test_variant="normal approximation on the arcsine scale",
        df_convention="not applicable (z test)",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support="two.sided|greater|less",
        notes=(
            "pwr.p.test is an APPROXIMATION; PowerBench uses an exact binomial "
            "rejection region. The two legitimately disagree — for p0=.30, "
            "p1=.50, power=.80 pwr returns 47 and PowerBench 43. Verified "
            "independently in R: exact binomial power at n=43 is 0.819812, so "
            "43 is the correct exact answer and the gap is the arcsine "
            "approximation's cost, not a defect. Exact tests are also "
            "non-monotonic in n (n=43 beats n=44 and n=46), which no normal "
            "approximation can reproduce."
        ),
    ),
    "two_sample_proportion": Parameterization(
        effect_definition="Cohen's arcsine h between the two group proportions",
        test_variant="normal approximation on the arcsine scale",
        df_convention="not applicable (z test)",
        rounding_rule="ceiling per group, doubled for the total",
        allocation_support="balanced only (pwr.2p.test); unbalanced needs pwr.2p2n.test",
        tails_support="two.sided|greater|less",
        notes=(
            "PowerBench uses a pooled-variance two-proportion z test on the raw "
            "scale; pwr works on the arcsine scale. They agree exactly at "
            "n_total=186 for p1=.30, p2=.50, but that agreement is not "
            "guaranteed away from this region."
        ),
    ),
    "chi_square_independence": Parameterization(
        effect_definition="Cohen's w via ES.w2 from the joint cell probabilities",
        test_variant="noncentral chi-square approximation",
        df_convention="(rows - 1) * (cols - 1)",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support="two.sided",
        notes=(
            "pwr.chisq.test enforces NO minimum expected cell count; PowerBench "
            "enforces min_expected_count from the scenario design (5 here). That "
            "is why pwr returns 48 and PowerBench 50 — PowerBench's floor is "
            "binding, not a disagreement about the noncentral chi-square. The "
            "same caveat already applies to chi_square_gof above."
        ),
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

    #: Models with a balanced-only pwr entry point. Reporting a balanced answer
    #: for an unbalanced design would be a fabricated comparison, so these are
    #: declined outright when allocation_ratio != 1.
    _BALANCED_ONLY = {"two_sample_t", "two_sample_proportion"}

    def supports(self, scenario: Scenario) -> bool:
        if scenario.model not in {
            "two_sample_t", "paired_t", "chi_square_gof", "one_way_anova",
            "linear_regression", "incremental_regression", "correlation",
            "one_sample_proportion", "two_sample_proportion", "chi_square_independence",
            "moderation",
        }:
            return False
        if scenario.goal != "required_sample_size":
            return False
        if scenario.decision_rule.alternative != "two.sided":
            return False
        if scenario.model in self._BALANCED_ONLY and scenario.design.get("allocation_ratio", 1.0) != 1.0:
            return False
        # NOTE: attrition_rate is deliberately NOT a reason to decline. PowerBench
        # reports the ANALYSIS n in `reference.n_total` and inflates separately into
        # `recruitment_total` (200 vs 223 for the balanced d=0.40 scenario), and the
        # matrix compares the analysis n. pwr answers that same question, so gating on
        # attrition would drop a valid comparison. Caught by
        # test_studio_two_sample_plan_is_assumption_visible.
        return True

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {"status": "unsupported", "reason": "pwr adapter supports two-sided required-sample-size scenarios for t, correlation, one-way ANOVA, regression (including the moderation increment), proportion, and chi-square designs, with balanced allocation where the pwr entry point is balanced-only"}
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
