"""Per-method versioning: the identity a human validation attests to.

A validation record is only meaningful if it names *exactly what was validated*. Binding
it to the package version alone is too coarse -- an unrelated fix to the ordinal formula
would invalidate someone's validation of the t-test. Binding it to the method name alone
is too loose -- a formula can change underneath a validation that still looks current.

So each method carries its own version, bumped only when its computed answers change.
This mirrors the `NORMALIZATION_VERSION` / `SECTIONING_VERSION` pattern in the sibling
`docpluck` package, where sub-versions let consumers invalidate cached results when
*behaviour* changes, independently of packaging churn.

Rules for changing this file:

* Bump a method's version **only** when its numeric output changes for some input.
  Docstring edits, renames and refactors that leave every answer identical do not bump it,
  because they would invalidate validations for no scientific reason.
* Never reuse a version number. Validations reference `(method_id, method_version)`
  permanently, so a reused number silently re-points historical attestations.
* Record *why* the answers changed in `METHOD_CHANGELOG`. A validator whose attestation
  goes stale is owed an explanation of what moved and by how much.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from .schema import Model

#: Bumped when the *set* of methods or the versioning contract itself changes, not on
#: every individual method bump.
METHOD_VERSION = "2.0.0"

#: method_id -> semantic version of that method's computed answers.
METHOD_VERSIONS: dict[str, str] = {
    "two_sample_t": "1.0.0",
    "welch_t": "1.0.0",
    "paired_t": "1.0.0",
    "one_sample_proportion": "1.0.0",
    "two_sample_proportion": "1.0.0",
    "chi_square_gof": "1.0.0",
    "chi_square_independence": "1.0.0",
    "one_way_anova": "1.0.0",
    "factorial_anova": "1.0.0",
    "ancova": "1.0.0",
    "planned_contrast": "1.1.0",
    "linear_regression": "1.0.0",
    "incremental_regression": "1.0.0",
    "moderation": "1.0.0",
    "logistic_regression": "2.0.0",
    "poisson_regression": "1.0.0",
    "correlation": "1.0.0",
    "tost_equivalence": "1.1.0",
    "mediation_indirect": "2.0.0",
    "meta_analysis_fixed": "1.0.0",
    "meta_analysis_random": "2.0.0",
    "noninferiority_t": "1.0.0",
    "ordinal_regression": "2.0.0",
    "bayes_factor_t": "1.0.0",
    "group_sequential_t": "2.0.0",
    "logrank_two_arm": "1.1.0",
    "rope_equivalence_t": "1.0.0",
}


@dataclass(frozen=True)
class MethodChange:
    """One version bump, with enough detail for a validator to re-attest cheaply."""

    method_id: str
    version: str
    date: str
    summary: str
    numeric_impact: str


#: Newest first. `numeric_impact` must state what moved and by how much -- "improved
#: accuracy" is not enough for someone deciding whether to re-check their study plan.
METHOD_CHANGELOG: tuple[MethodChange, ...] = (
    MethodChange(
        method_id="ordinal_regression",
        version="2.0.0",
        date="2026-08-03",
        summary=(
            "Replaced a flat Var(beta) = 4/n, which ignored the declared number of "
            "categories, with the Whitehead (1993) proportional-odds variance."
        ),
        numeric_impact=(
            "Required N for OR=1.5, k=4, 80% power moves from 191 to 614. The previous "
            "sample size delivered about 0.34 power measured by MASS::polr. Every prior "
            "ordinal plan understated the required sample by roughly threefold."
        ),
    ),
    MethodChange(
        method_id="logistic_regression",
        version="2.0.0",
        date="2026-08-03",
        summary=(
            "Fisher information now evaluates both arms, not only the baseline "
            "probability (Demidenko 2007)."
        ),
        numeric_impact=(
            "Required N for OR=1.5, p0=0.30 moves from 910 to 856. The error changed sign "
            "around p0=0.5: previously +21% at OR=3.0/p0=0.20 but -6% at OR=2.0/p0=0.50, "
            "so some prior plans were under-powered rather than merely wasteful."
        ),
    ),
    MethodChange(
        method_id="meta_analysis_random",
        version="2.0.0",
        date="2026-08-03",
        summary=(
            "Implemented Hartung-Knapp properly: df = k-1 rather than k-2, the q variance "
            "rescaling is applied, and the statistic is referred to a t distribution "
            "rather than a normal one."
        ),
        numeric_impact=(
            "Required per-study N shifts modestly; the previous implementation combined "
            "three errors that partially offset, so it landed near the right answer for "
            "the wrong reasons and drifted for other k and tau."
        ),
    ),
    MethodChange(
        method_id="group_sequential_t",
        version="2.0.0",
        date="2026-08-03",
        summary=(
            "Reported power is now the sequential operating characteristic under "
            "Lan-DeMets O'Brien-Fleming boundaries solved to exactly alpha, replacing a "
            "hardcoded inflation table plus fixed-design power."
        ),
        numeric_impact=(
            "For d=0.4 with 2 looks, N moves from 202 to 200 and the reported power now "
            "describes the sequential design rather than a single final test. Designs "
            "with more than five looks are now supported instead of raising an error."
        ),
    ),
    MethodChange(
        method_id="mediation_indirect",
        version="2.0.0",
        date="2026-08-03",
        summary=(
            "Path standard errors are now the OLS regression-coefficient SEs on residual "
            "degrees of freedom, replacing the Fisher-z SE for a correlation."
        ),
        numeric_impact=(
            "Joint power at n=117 falls from 0.8024 to 0.7909 against a Monte Carlo truth "
            "of 0.7877; required N for a=b=0.3 at 80% power moves from 118 to 119."
        ),
    ),
    MethodChange(
        method_id="logrank_two_arm",
        version="1.1.0",
        date="2026-08-03",
        summary=(
            "The event probability is now derived from the declared accrual, follow-up "
            "and dropout plan when those are supplied, instead of requiring p_event by "
            "hand."
        ),
        numeric_impact=(
            "Plans that supply p_event directly are unchanged. Plans that declare an "
            "accrual schedule now get a derived p_event: for HR=1.5 with 1y accrual, 1y "
            "follow-up and 0.1 dropout hazard, p_event=0.673 and N=284."
        ),
    ),
    MethodChange(
        method_id="planned_contrast",
        version="1.1.0",
        date="2026-08-03",
        summary=(
            "Documented that contrast weights cannot affect power once cohens_f is "
            "declared as the contrast's own standardized effect; the weights are retained "
            "for provenance and validation. A non-zero weight is now required."
        ),
        numeric_impact=(
            "No change to any previously returned sample size. The weights cancel "
            "algebraically under this parameterization, so the prior answers were correct "
            "even though the contract was unclear."
        ),
    ),
    MethodChange(
        method_id="tost_equivalence",
        version="1.1.0",
        date="2026-08-03",
        summary="Removed dead code; clamping behaviour in the low-power region documented.",
        numeric_impact=(
            "No change to any returned sample size. Verified against "
            "TOSTER::power_t_TOST, which agrees to four decimal places."
        ),
    ),
)


def method_version(method_id: str) -> str:
    """Version of the named method's computed answers."""
    try:
        return METHOD_VERSIONS[method_id]
    except KeyError:
        raise ValueError(f"unknown method_id {method_id!r}") from None


def changes_since(method_id: str, version: str) -> list[MethodChange]:
    """Changes to `method_id` published after `version`, newest first.

    This is what turns a stale validation into an actionable one: a validator who checked
    version 1.0.0 can be shown exactly what moved and by how much, rather than being told
    only that their attestation no longer applies.
    """
    if method_id not in METHOD_VERSIONS:
        raise ValueError(f"unknown method_id {method_id!r}")
    current = METHOD_VERSIONS[method_id]
    if version == current:
        return []
    return [
        change
        for change in METHOD_CHANGELOG
        if change.method_id == method_id and _parse(change.version) > _parse(version)
    ]


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def method_fingerprint(method_id: str) -> str:
    """Stable identity a validation record binds to."""
    return f"{method_id}@{method_version(method_id)}"


def all_methods() -> dict[str, str]:
    """Every planner method with its current version."""
    return dict(METHOD_VERSIONS)


def _validate_registry() -> None:
    """The registry must cover exactly the planner's models -- no more, no fewer."""
    declared = set(METHOD_VERSIONS)
    engine = set(get_args(Model))
    missing = sorted(engine - declared)
    extra = sorted(declared - engine)
    if missing or extra:
        raise RuntimeError(
            f"METHOD_VERSIONS is out of sync with schema.Model; missing={missing}, extra={extra}"
        )


_validate_registry()
