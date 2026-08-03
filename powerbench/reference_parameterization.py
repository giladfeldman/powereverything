"""What PowerBench itself computes, per method.

Every cross-tool comparison has two sides. Declaring only the external tool's semantics
would be half a contract: a difference is attributable only when *both* sides say what
they are powering.

These declarations are the reference side. They are written from the implementation in
`references.py` and `specialist_extras.py` -- if a formula changes such that one of these
becomes untrue, the method's version must be bumped and the declaration updated together.
"""

from __future__ import annotations

from .parameterization import Parameterization

_TWO_SIDED_OR_ONE = "two.sided|greater|less"

#: method_id -> what PowerBench powers, and how.
REFERENCE_PARAMETERIZATIONS: dict[str, Parameterization] = {
    "two_sample_t": Parameterization(
        effect_definition="Cohen's d, difference in means over the pooled SD",
        test_variant="exact noncentral t, pooled variance",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "welch_t": Parameterization(
        effect_definition="raw mean difference with separate group SDs",
        test_variant="noncentral t approximation, unequal variances",
        df_convention="Welch-Satterthwaite",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="Deliberately kept separate from the pooled path; pooled tools are declined, not approximated.",
    ),
    "paired_t": Parameterization(
        effect_definition="Cohen's dz, standardized within-person change",
        test_variant="exact noncentral t",
        df_convention="n - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "one_sample_proportion": Parameterization(
        effect_definition="difference between a null and an alternative proportion",
        test_variant="exact binomial rejection region",
        df_convention="not applicable",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "two_sample_proportion": Parameterization(
        effect_definition="difference between two proportions on the raw scale",
        test_variant="pooled-z normal approximation, null SE for the critical value and alternative SE for the spread",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="Differs from pwr.2p.test, which powers the arcsine-transformed h. That is an estimand difference, not an error.",
    ),
    "chi_square_gof": Parameterization(
        effect_definition="Cohen's w over the null and alternative cell probabilities",
        test_variant="noncentral chi-square",
        df_convention="categories - 1",
        rounding_rule="ceiling, subject to a minimum expected cell count",
        tails_support="two.sided",
    ),
    "chi_square_independence": Parameterization(
        effect_definition="Cohen's w from the joint cell probabilities",
        test_variant="noncentral chi-square, omnibus independence",
        df_convention="(rows - 1)(cols - 1)",
        rounding_rule="ceiling, subject to a minimum expected cell count",
        tails_support="two.sided",
    ),
    "one_way_anova": Parameterization(
        effect_definition="Cohen's f across group means",
        test_variant="noncentral F, omnibus",
        df_convention="groups - 1 and N - groups",
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
    ),
    "factorial_anova": Parameterization(
        effect_definition="Cohen's f for the tested term",
        test_variant="noncentral F for one term of a factorial design",
        df_convention="term df and N - cells",
        rounding_rule="ceiling per cell",
        allocation_support="balanced only",
        tails_support="two.sided",
    ),
    "ancova": Parameterization(
        effect_definition="Cohen's f adjusted for covariate R-squared, f/sqrt(1 - R^2)",
        test_variant="noncentral F with covariate adjustment",
        df_convention="groups - 1 and N - groups - covariates",
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
        notes="Matches the G*Power ANCOVA parameterization.",
    ),
    "planned_contrast": Parameterization(
        effect_definition="Cohen's f of the contrast itself, not of the omnibus effect",
        test_variant="noncentral F with one numerator degree of freedom",
        df_convention="1 and N - groups",
        rounding_rule="ceiling per group",
        allocation_support="balanced only",
        tails_support="two.sided",
        notes="Contrast weights record the estimand but cannot change power once f is declared; they cancel algebraically.",
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
        notes="Matches pwr.f2.test. G*Power uses lambda = f^2 * N, which is a documented divergence.",
    ),
    "moderation": Parameterization(
        effect_definition="Cohen's f-squared for the interaction increment",
        test_variant="noncentral F, one tested predictor, fixed predictors",
        df_convention="1 and N - total predictors - 1",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="fixed (conditioned on the design matrix)",
        tails_support="two.sided",
    ),
    "logistic_regression": Parameterization(
        effect_definition="odds ratio between two equally sized exposure groups",
        test_variant="Wald z on the slope (Demidenko 2007)",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
        notes=(
            "The binary branch powers a two-group contrast. Tools defaulting to a "
            "standard-normal predictor power a one-SD change instead, which is a different "
            "estimand and produces very different sample sizes."
        ),
    ),
    "poisson_regression": Parameterization(
        effect_definition="rate ratio between two equally sized groups",
        test_variant="Wald normal approximation on the log rate",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "correlation": Parameterization(
        effect_definition="Pearson r",
        test_variant="Fisher-z normal approximation",
        df_convention="n - 3",
        rounding_rule="ceiling to the smallest integer meeting target power",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "tost_equivalence": Parameterization(
        effect_definition="equivalence bounds on the raw mean difference",
        test_variant="two one-sided noncentral t tests, Frechet lower bound on the intersection",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support="two one-sided",
        notes="Verified against TOSTER::power_t_TOST to four decimal places.",
    ),
    "mediation_indirect": Parameterization(
        effect_definition="standardized a and b path coefficients of the indirect effect",
        test_variant="joint significance of both paths, product of marginal powers",
        df_convention="n - 2 for the a path and n - 3 for the b path",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="random normal X",
        tails_support="two.sided",
        notes="The two path tests are asymptotically orthogonal, which is what licenses the product form.",
    ),
    "meta_analysis_fixed": Parameterization(
        effect_definition="common standardized mean difference across studies",
        test_variant="inverse-variance fixed-effect summary, normal reference",
        df_convention="asymptotic normal",
        rounding_rule="ceiling per group per study",
        allocation_support="balanced within study",
        tails_support=_TWO_SIDED_OR_ONE,
    ),
    "meta_analysis_random": Parameterization(
        effect_definition="mean standardized mean difference with between-study SD tau",
        test_variant="Hartung-Knapp adjusted random-effects summary",
        df_convention="k - 1",
        rounding_rule="ceiling per group per study",
        allocation_support="balanced within study",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="tau is treated as a declared design assumption, not estimated from the data.",
    ),
    "noninferiority_t": Parameterization(
        effect_definition="non-inferiority margin on the raw mean difference",
        test_variant="one-sided noncentral t",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support="one-sided",
    ),
    "ordinal_regression": Parameterization(
        effect_definition="proportional odds ratio between two equally sized groups",
        test_variant="Whitehead (1993) proportional-odds normal approximation",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        predictor_distribution="balanced binary",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="Depends on the marginal category distribution through the 1 - sum(p^3) spread term.",
    ),
    "bayes_factor_t": Parameterization(
        effect_definition="Cohen's d under a JZS Cauchy prior",
        test_variant="Bayes-factor design analysis against a threshold",
        df_convention="n1 + n2 - 2",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support="two.sided",
        notes="Design analysis, not a frequentist power calculation.",
    ),
    "group_sequential_t": Parameterization(
        effect_definition="Cohen's d at the final analysis",
        test_variant="Lan-DeMets O'Brien-Fleming alpha spending, efficacy stopping only",
        df_convention="asymptotic normal with sqrt(t_i / t_j) covariance",
        rounding_rule="ceiling per arm",
        allocation_support="balanced only",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="Reported power is the sequential operating characteristic, not fixed-design power at the same N.",
    ),
    "logrank_two_arm": Parameterization(
        effect_definition="hazard ratio under proportional hazards",
        test_variant="Schoenfeld required-events formula",
        df_convention="asymptotic normal",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support=_TWO_SIDED_OR_ONE,
        notes="Event probability may be supplied or derived from accrual, follow-up and dropout.",
    ),
    "rope_equivalence_t": Parameterization(
        effect_definition="region of practical equivalence on the raw mean difference",
        test_variant="normal-normal posterior, numeric integration",
        df_convention="not applicable",
        rounding_rule="ceiling to the smallest integer meeting target power",
        allocation_support="any ratio",
        tails_support="two-sided region",
        notes="Bayesian; distinct from TOST even though both address equivalence.",
    ),
}


def reference_parameterization(method_id: str) -> Parameterization:
    try:
        return REFERENCE_PARAMETERIZATIONS[method_id]
    except KeyError:
        raise ValueError(f"no reference parameterization declared for {method_id!r}") from None
