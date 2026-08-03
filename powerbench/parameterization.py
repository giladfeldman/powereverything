"""How a tool defines what it is computing.

Two power tools can return sample sizes differing by a factor of three and both be
correct, because they are answering different questions. `pwrss.z.logreg` returns N = 249
where PowerBench returns 856 for what looks like the same logistic design; the difference
is that pwrss defaults to a *standard-normal* predictor (the effect is a one-SD change)
while PowerBench's binary branch contrasts two equally sized groups. Direct Monte Carlo
confirms 0.31 power at N = 249 and 0.805 at N = 856 for a balanced binary predictor.

A cross-tool comparison that only compares numbers cannot tell that story. It would report
a 3.4x defect in one of two correct tools. So every adapter must *declare* its own
semantics, and differences are attributed by comparing declarations before comparing
numbers.

This module defines the declaration vocabulary and the classification procedure. The
procedure is deliberately mechanical up to the last step, and deliberately refuses to
automate the last step: a difference that survives every declared explanation is marked
`needs_review` for a human, never `probable_defect`. Calling something a defect is a claim
about another project's correctness and has to be made by a person who has looked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

#: Fields compared when attributing a difference, in the order they are checked. The order
#: matters: if two tools do not agree on what the effect size means, that is the
#: explanation, and there is no point reporting a df convention as the cause.
COMPARED_FIELDS: tuple[str, ...] = (
    "effect_definition",
    "predictor_distribution",
    "test_variant",
    "df_convention",
    "allocation_support",
    "tails_support",
)

#: Ordered from "these agree" to "someone must look". Generalized from the seven-category
#: taxonomy sketched in docs/tool_dossiers/gpower_two_sample_t.md.
CATEGORIES = (
    "compatible",
    "rounding_display",
    "effect_definition",
    "df_or_test_variant",
    "approximation_method",
    "allocation_or_tails",
    "version_drift",
    "unsupported_here",
    "needs_review",
    "probable_defect",
)

#: Categories that describe a legitimate difference of question rather than an error.
ASSUMPTION_CATEGORIES = frozenset(
    {"effect_definition", "df_or_test_variant", "approximation_method", "allocation_or_tails"}
)

CATEGORY_MEANINGS: dict[str, str] = {
    "compatible": "The tools agree within tolerance under matched assumptions.",
    "rounding_display": "The tools agree; the difference is integer rounding or display precision.",
    "effect_definition": "The tools define the effect size differently, so they are powering different quantities.",
    "df_or_test_variant": "The tools use a different test variant or degrees-of-freedom convention.",
    "approximation_method": "At least one tool uses a documented approximation where the other is exact, or they use different approximations.",
    "allocation_or_tails": "The tools assume different group allocation or a different number of tails.",
    "version_drift": "The same tool returns different answers across versions.",
    "unsupported_here": "The tool cannot represent this design, so it declines to answer.",
    "needs_review": "The numbers differ and no declared assumption explains it. A human must investigate.",
    "probable_defect": "A human has investigated and concluded one implementation is wrong. Never assigned automatically.",
}


@dataclass(frozen=True)
class Parameterization:
    """A tool's declaration of what it computes for one method.

    Fields left as ``None`` mean "not declared", which is treated as *unknown* rather than
    as agreement: an undeclared field can never be used to explain away a difference.
    """

    effect_definition: str | None = None
    test_variant: str | None = None
    df_convention: str | None = None
    rounding_rule: str | None = None
    predictor_distribution: str | None = None
    allocation_support: str | None = None
    tails_support: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def differing_fields(self, other: "Parameterization") -> list[str]:
        """Declared fields where the two tools disagree.

        A field is only counted when *both* sides declared it. Comparing a declared value
        against an undeclared one would let a silent adapter appear to explain a gap it
        never accounted for.
        """
        differing = []
        for name in COMPARED_FIELDS:
            mine, theirs = getattr(self, name), getattr(other, name)
            if mine is None or theirs is None:
                continue
            if mine != theirs:
                differing.append(name)
        return differing


#: Which category a differing field implies. Checked in `Parameterization.COMPARED` order,
#: so the most fundamental difference wins: if two tools do not even agree on what the
#: effect size means, that is the explanation, not the df convention.
FIELD_CATEGORY: dict[str, str] = {
    "effect_definition": "effect_definition",
    "predictor_distribution": "effect_definition",
    "test_variant": "df_or_test_variant",
    "df_convention": "df_or_test_variant",
    "allocation_support": "allocation_or_tails",
    "tails_support": "allocation_or_tails",
}


@dataclass(frozen=True)
class Classification:
    category: str
    explanation: str
    differing_fields: tuple[str, ...] = ()

    @property
    def is_assumption_difference(self) -> bool:
        return self.category in ASSUMPTION_CATEGORIES

    @property
    def needs_human(self) -> bool:
        return self.category == "needs_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "explanation": self.explanation,
            "differing_fields": list(self.differing_fields),
            "is_assumption_difference": self.is_assumption_difference,
        }


def classify_difference(
    reference_n: int | None,
    tool_n: int | None,
    reference_parameterization: Parameterization,
    tool_parameterization: Parameterization,
    *,
    tool_status: str = "ok",
    relative_tolerance: float = 0.02,
) -> Classification:
    """Attribute a difference between PowerBench and one external tool.

    The procedure, in order:

    1. The tool declined to answer            -> unsupported_here
    2. Declared parameterizations differ      -> the category that field implies
    3. Numbers agree within tolerance         -> compatible (or rounding_display)
    4. Numbers differ, nothing explains it    -> needs_review  [HUMAN]

    Step 2 runs *before* the numeric comparison on purpose. Two tools answering different
    questions may still happen to produce similar numbers; reporting that as "compatible"
    would be luck misread as corroboration, and would hide the divergence until a
    parameter changed.

    `probable_defect` is never returned. Promoting `needs_review` to a defect requires a
    written case study in `docs/discrepancies/`, because it asserts that a named third-party
    tool -- or this one -- is wrong.

    `relative_tolerance` should match how the tool produced its answer. A closed-form
    solver can be held to a couple of percent; a Monte Carlo adapter cannot, because its
    own search resolution is wider than that. Adapters that estimate by simulation declare
    the resolution in their parameterization notes and expose `tolerance_for(method_id)`,
    and the caller passes that value here so the comparison is made against the tool's
    stated precision rather than an arbitrary global constant.
    """
    if tool_status in {"unsupported", "unavailable"}:
        return Classification(
            category="unsupported_here",
            explanation=(
                "The tool declines to answer this design rather than forcing a number. "
                "Declining is the correct response to a design it cannot represent."
            ),
        )

    differing = reference_parameterization.differing_fields(tool_parameterization)
    if differing:
        primary = differing[0]
        category = FIELD_CATEGORY[primary]
        details = ", ".join(
            f"{name}: PowerBench={getattr(reference_parameterization, name)!r} vs "
            f"tool={getattr(tool_parameterization, name)!r}"
            for name in differing
        )
        return Classification(
            category=category,
            explanation=(
                f"{CATEGORY_MEANINGS[category]} The tools are not answering the same "
                f"question, so their sample sizes are not directly comparable. {details}."
            ),
            differing_fields=tuple(differing),
        )

    if reference_n is None or tool_n is None:
        return Classification(
            category="needs_review",
            explanation="A sample size is missing on one side, so no comparison is possible.",
        )

    difference = abs(reference_n - tool_n)
    if difference == 0:
        return Classification(
            category="compatible",
            explanation="Both tools return the same sample size under matched assumptions.",
        )
    if difference <= 1:
        return Classification(
            category="rounding_display",
            explanation=(
                "The tools differ by a single observation, which is integer rounding of the "
                "same underlying answer rather than a disagreement."
            ),
        )

    largest = max(abs(reference_n), abs(tool_n), 1)
    if difference / largest <= relative_tolerance:
        return Classification(
            category="compatible",
            explanation=(
                f"The tools differ by {difference} of {largest} observations "
                f"({difference / largest:.1%}), within the {relative_tolerance:.0%} "
                "tolerance for matched assumptions."
            ),
        )


    # If one side declared an approximation and the other did not, that is the most
    # likely explanation -- but it is still only a hypothesis, so it is reported as an
    # assumption difference rather than closing the case.
    approximations = [
        side
        for side, parameters in (("PowerBench", reference_parameterization), ("tool", tool_parameterization))
        if parameters.test_variant and "approx" in parameters.test_variant.lower()
    ]
    if len(approximations) == 1:
        return Classification(
            category="approximation_method",
            explanation=(
                f"{CATEGORY_MEANINGS['approximation_method']} Only {approximations[0]} "
                f"declares an approximation, and the sample sizes differ by "
                f"{difference} observations ({difference / largest:.1%})."
            ),
            differing_fields=("test_variant",),
        )

    return Classification(
        category="needs_review",
        explanation=(
            f"The sample sizes differ by {difference} observations "
            f"({difference / largest:.1%}) and no declared difference in effect definition, "
            "test variant, degrees of freedom, allocation, or tails explains it. This is a "
            "signal to investigate, not a finding that either tool is wrong: promote it to "
            "probable_defect only with a written case study in docs/discrepancies/."
        ),
    )
