"""Attributing cross-tool differences to assumptions rather than to blame.

The scientific core of the cross-tool feature is the distinction between "these two tools
disagree" and "these two tools are answering different questions". Getting it wrong in
either direction is bad: calling an assumption difference a defect libels a correct tool,
and calling a defect an assumption difference hides a wrong number.
"""

from __future__ import annotations

import pytest

from powerbench.parameterization import (
    ASSUMPTION_CATEGORIES,
    CATEGORIES,
    CATEGORY_MEANINGS,
    Parameterization,
    classify_difference,
)

MATCHED = Parameterization(
    effect_definition="cohens d between two groups",
    predictor_distribution="balanced binary",
    test_variant="noncentral t",
    df_convention="n1 + n2 - 2",
    allocation_support="any ratio",
    tails_support="two.sided|greater|less",
)


def test_every_category_has_a_written_meaning():
    assert set(CATEGORIES) == set(CATEGORY_MEANINGS)
    for category, meaning in CATEGORY_MEANINGS.items():
        assert len(meaning) > 30, f"{category} meaning is too thin to show a user"


def test_identical_numbers_under_matched_assumptions_are_compatible():
    assert classify_difference(200, 200, MATCHED, MATCHED).category == "compatible"


def test_off_by_one_is_rounding_not_disagreement():
    assert classify_difference(200, 201, MATCHED, MATCHED).category == "rounding_display"


def test_small_relative_difference_is_compatible():
    assert classify_difference(200, 203, MATCHED, MATCHED).category == "compatible"


def test_declining_to_answer_is_not_a_disagreement():
    """`unsupported` is the correct, honest response to a design a tool cannot represent."""
    for status in ("unsupported", "unavailable"):
        result = classify_difference(200, None, MATCHED, MATCHED, tool_status=status)
        assert result.category == "unsupported_here"
        assert not result.needs_human


def test_real_pwrss_logistic_case_is_an_effect_definition_difference():
    """The case that motivated this module.

    `pwrss.z.logreg` returns N=249 where PowerBench returns 856 for what looks like the
    same logistic design. Direct glm Monte Carlo confirms 0.31 power at 249 and 0.805 at
    856 for a balanced binary predictor: pwrss defaults to a standard-normal predictor, so
    it is powering a one-SD change, not a two-group contrast. A comparison that only
    compared numbers would report a 3.4x defect in one of two correct tools.
    """
    powerbench = Parameterization(
        effect_definition="odds ratio between two equally sized groups",
        predictor_distribution="balanced binary",
        test_variant="Wald z (Demidenko 2007)",
    )
    pwrss = Parameterization(
        effect_definition="odds ratio per one-SD change",
        predictor_distribution="standard normal",
        test_variant="Wald z (Demidenko 2007)",
    )
    result = classify_difference(856, 249, powerbench, pwrss)
    assert result.category == "effect_definition"
    assert result.is_assumption_difference
    assert not result.needs_human
    assert "effect_definition" in result.differing_fields


def test_declared_difference_is_checked_before_the_numbers():
    """Similar numbers must not launder an assumption difference into 'compatible'.

    Two tools answering different questions can coincidentally agree. Reporting that as
    corroboration is luck misread as evidence, and it hides the divergence until some
    parameter changes.
    """
    other = Parameterization(
        effect_definition="cohens f",
        predictor_distribution="balanced binary",
        test_variant="noncentral t",
    )
    result = classify_difference(200, 200, MATCHED, other)
    assert result.category == "effect_definition"


def test_unexplained_gap_is_needs_review_never_probable_defect():
    """Calling a third-party tool wrong is a claim a human must make."""
    result = classify_difference(200, 260, MATCHED, MATCHED)
    assert result.category == "needs_review"
    assert result.needs_human
    assert not result.is_assumption_difference
    assert "docs/discrepancies/" in result.explanation


def test_undeclared_fields_cannot_explain_a_gap():
    """A silent adapter must not appear to account for a difference it never declared."""
    silent = Parameterization()
    result = classify_difference(200, 600, MATCHED, silent)
    assert result.category == "needs_review"


def test_classification_never_auto_assigns_probable_defect():
    """Exhaustive-ish sweep: no input combination may produce `probable_defect`."""
    declarations = [
        MATCHED,
        Parameterization(),
        Parameterization(effect_definition="something else"),
        Parameterization(test_variant="normal approximation"),
        Parameterization(df_convention="k - 1"),
        Parameterization(allocation_support="1:1 only"),
    ]
    for reference in declarations:
        for tool in declarations:
            for numbers in ((200, 200), (200, 201), (200, 260), (200, 5000), (None, 200), (200, None)):
                for status in ("ok", "unsupported", "unavailable"):
                    result = classify_difference(*numbers, reference, tool, tool_status=status)
                    assert result.category != "probable_defect"
                    assert result.category in CATEGORIES


def test_assumption_categories_are_not_treated_as_errors():
    for category in ASSUMPTION_CATEGORIES:
        assert category in CATEGORIES
    assert "needs_review" not in ASSUMPTION_CATEGORIES
    assert "probable_defect" not in ASSUMPTION_CATEGORIES


def test_missing_number_on_one_side_is_reviewable_not_compatible():
    assert classify_difference(None, 200, MATCHED, MATCHED).category == "needs_review"
    assert classify_difference(200, None, MATCHED, MATCHED).category == "needs_review"


def test_parameterization_round_trips_to_a_dict_for_the_matrix():
    payload = MATCHED.to_dict()
    assert payload["effect_definition"] == "cohens d between two groups"
    assert "notes" in payload


def test_every_planner_method_declares_a_reference_parameterization():
    """A comparison needs both sides declared; an undeclared reference explains nothing."""
    from typing import get_args

    from powerbench.reference_parameterization import REFERENCE_PARAMETERIZATIONS
    from powerbench.schema import Model

    missing = sorted(set(get_args(Model)) - set(REFERENCE_PARAMETERIZATIONS))
    assert not missing, f"methods with no declared parameterization: {missing}"


def test_reference_declarations_name_an_effect_and_a_test():
    from powerbench.reference_parameterization import REFERENCE_PARAMETERIZATIONS

    for method_id, declaration in REFERENCE_PARAMETERIZATIONS.items():
        assert declaration.effect_definition, f"{method_id} does not say what effect it powers"
        assert declaration.test_variant, f"{method_id} does not say which test it powers"


def test_adapters_declaring_nothing_get_an_empty_parameterization():
    """The base class default must be empty, i.e. unknown -- never silently agreeing."""
    from powerbench.adapters.base import Adapter
    from powerbench.schema import Scenario

    class Silent(Adapter):
        id = "test.silent"
        language = "python"

        def supports(self, scenario: Scenario) -> bool:
            return False

        def run(self, scenario: Scenario) -> dict:
            return {"status": "unsupported"}

    declaration = Silent().parameterization("two_sample_t")
    assert declaration.effect_definition is None
    assert declaration.differing_fields(MATCHED) == []


def test_r_pwr_declarations_match_the_methods_it_supports():
    """Every method the pwr adapter will actually run must have a declaration.

    A supported method with no declaration would compare a real number against an empty
    contract, and any gap would land in `needs_review` with no way to resolve it.
    """
    from powerbench.adapters.r_pwr import _PWR_PARAMETERIZATIONS, RPwrAdapter
    from powerbench.schema import load_scenario

    adapter = RPwrAdapter()
    supported = set()
    for path in sorted(__import__("pathlib").Path("data/scenarios").glob("*.json")):
        scenario = load_scenario(path)
        if adapter.supports(scenario):
            supported.add(scenario.model)

    missing = sorted(supported - set(_PWR_PARAMETERIZATIONS))
    assert not missing, f"r.pwr runs these methods but declares nothing for them: {missing}"
