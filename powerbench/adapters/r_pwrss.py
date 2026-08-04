"""R `pwrss` adapter: generalized-outcome methods plus the t-family designs pwr cannot reach.

`pwr` cannot represent logistic, Poisson or ordinal regression, which is precisely where
PowerBench's own formulas were wrong before 2026-08-03. `pwrss` reaches them, so it is the
most valuable second opinion available for this engine. Since 2026-08-04 it also covers
the designs `pwr`'s t entry points cannot: unbalanced pooled t, Welch, one-sided
non-inferiority, one-covariate ANCOVA, and single planned contrasts.

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

_SUPPORTED = {
    "logistic_regression",
    "poisson_regression",
    "two_sample_t",
    "welch_t",
    "noninferiority_t",
    "ancova",
    "planned_contrast",
}

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
            "Called with dist=list(dist='bernoulli', prob=ratio/(1+ratio)) -- the "
            "scenario's allocation fractions, 0.5 when balanced. The pwrss default is a "
            "standard-normal predictor, which powers a different estimand entirely. "
            "Verified at ratio=1.5: both tools return 903."
        ),
    ),
    "poisson_regression": Parameterization(
        effect_definition="rate ratio between two equally sized groups",
        test_variant="Wald normal approximation on the log rate",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        tails_support="two.sided|greater|less",
        notes=(
            "Called with an explicit Bernoulli(0.5) predictor and the scenario's "
            "mean.exposure to match PowerBench's rate scale."
        ),
    ),
    "two_sample_t": Parameterization(
        effect_definition="Cohen's d, difference in means over the pooled SD",
        test_variant="exact noncentral t, pooled variance",
        # df_convention is deliberately UNDECLARED rather than declared different: pwrss
        # 1.0.0 forces welch.df = TRUE for unbalanced designs, but with equal declared SDs
        # the noncentrality is identical to the pooled test and the returned N matches the
        # exact pooled answer on every committed scenario (196/294 unbalanced, 100/100
        # balanced). A declared difference would classify exact agreement as "answering a
        # different question", which the sub-observation df nuance is not; a real gap
        # would fall through to needs_review, where the note below explains the suspect.
        rounding_rule="ceiling per group",
        allocation_support="any ratio",
        tails_support="two.sided|greater|less",
        notes=(
            "pwrss.t.2means with sd1 = sd2 = 1 and kappa = 1 / allocation_ratio. pwrss "
            "forces Welch-Satterthwaite df when unbalanced; with equal declared SDs this "
            "changes only the critical value, not the noncentrality."
        ),
    ),
    "welch_t": Parameterization(
        effect_definition="raw mean difference with separate group SDs",
        test_variant="noncentral t approximation, unequal variances",
        df_convention="Welch-Satterthwaite",
        rounding_rule="ceiling per group",
        allocation_support="any ratio",
        tails_support="two.sided|greater|less",
        notes="pwrss.t.2means with the scenario's group SDs; matches PowerBench's Welch contract.",
    ),
    "noninferiority_t": Parameterization(
        effect_definition="non-inferiority margin on the raw mean difference",
        test_variant="one-sided noncentral t",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling per group",
        allocation_support="any ratio",
        tails_support="one-sided",
        notes=(
            "pwrss places the noncentrality under the null margin where PowerBench shifts "
            "the alternative; the two approximations differ by about one observation per "
            "group at the committed scenario (100 vs 102), inside tolerance."
        ),
    ),
    "ancova": Parameterization(
        effect_definition="Cohen's f adjusted for covariate R-squared, f/sqrt(1 - R^2)",
        test_variant="noncentral F with covariate adjustment",
        df_convention="groups - 1 and N - groups - covariates",
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
        notes=(
            "pwrss.f.ancova takes eta-squared; the adapter converts the ADJUSTED f2 "
            "(f2 / (1 - R^2)). Passing the unadjusted effect returns 200 instead of 150 "
            "for the committed scenario -- a parameterization mismatch, not a finding."
        ),
    ),
    "planned_contrast": Parameterization(
        effect_definition="Cohen's f of the contrast itself, not of the omnibus effect",
        test_variant="noncentral F with one numerator degree of freedom",
        # df_convention deliberately undeclared: power.t.contrast requires
        # k.covariates >= 1, so with r.squared = 0 its error df is N - groups - 1 where
        # PowerBench uses N - groups -- a one-df nuance that changes no committed answer
        # (129 exactly), not a different question. The note carries the fact.
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
        notes=(
            "Cell means placed at w_j / rms(w) * f, realizing the same contract "
            "PowerBench declares; the t statistic pwrss uses is F with one numerator df. "
            "pwrss's phantom covariate slot makes its error df N - groups - 1."
        ),
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
        if scenario.model == "noninferiority_t":
            # Non-inferiority is inherently one-sided; the scenario declares "greater".
            return scenario.decision_rule.alternative == "greater"
        if scenario.decision_rule.alternative != "two.sided":
            return False
        if scenario.model == "logistic_regression":
            # Only the balanced binary contract is comparable; a continuous predictor is a
            # different estimand and must be declined rather than silently matched.
            return str(scenario.design.get("predictor_type", "binary")) == "binary"
        if scenario.model == "ancova":
            # pwrss.f.ancova models exactly one covariate, which is all the scenario
            # schema declares (a single covariate_r2).
            return "covariate_r2" in scenario.design
        if scenario.model == "planned_contrast":
            # The mu_j = w_j / rms(w) * f contract assumes balanced groups.
            weights = scenario.design.get("contrast_weights")
            return bool(weights) and len(weights) == int(scenario.design.get("groups", 0))
        return True

    def run(self, scenario: Scenario) -> dict:
        if not self.supports(scenario):
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "pwrss adapter covers two-sided logistic and Poisson regression with a "
                    "balanced binary predictor, t designs (pooled, Welch, one-sided "
                    "non-inferiority), one-covariate ANCOVA, and balanced planned contrasts"
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
