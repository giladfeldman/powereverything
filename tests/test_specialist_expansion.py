import json
from pathlib import Path

import pytest

from powerbench.schema import load_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
from powerbench.references import analytic_reference
from powerbench.specialist_extras import ordinal_proportional_odds_power

SPECIALIST_SCENARIOS = [
    "chi_square_independence_2x2.json",
    "factorial_anova_2x2_interaction.json",
    "ancova_two_group_f020.json",
    "planned_contrast_three_group.json",
    "moderation_interaction_f2_020.json",
    "logistic_or15_p030.json",
    "poisson_rr15_rate02.json",
    "tost_equivalence_dbounds.json",
    "mediation_indirect_a03_b03.json",
    "meta_analysis_fixed_d030_k6.json",
    "meta_analysis_random_d030_tau02_k6.json",
    "noninferiority_t_margin05.json",
    "ordinal_or15_k4.json",
    "bayes_factor_t_d040_bf3.json",
    "group_sequential_t_d040_looks2.json",
    "logrank_hr15_pevent06.json",
    "rope_equivalence_t_dbounds.json",
]


def test_specialist_scenarios_hit_targets():
    for name in SPECIALIST_SCENARIOS:
        scenario = load_scenario(f"{REPO_ROOT}/data/scenarios/{name}")
        result = analytic_reference(scenario)
        # `n_total > 1` was the original assertion here and is close to vacuous. The
        # target-power assertion below is also weak on its own, because every
        # `required_n_*` is a `while power < target: n += 1` loop -- it cannot fail
        # regardless of whether the formula is right. Real falsification lives in
        # tests/test_reference_simulation_alignment.py; these are contract checks.
        assert result["n_total"] >= 2
        assert result["power"] >= scenario.target_power
        if scenario.model == "meta_analysis_random":
            assert result.get("hartung_knapp") is True
            assert len(result["prediction_interval_95"]) == 2


def test_ordinal_reference_uses_declared_categories_and_is_minimal():
    """Regression guard for the pre-2026-08-03 ordinal defect.

    The old implementation used a flat `Var(beta) = 4/n`, so its answer did not depend on
    `categories` at all: k=3, 4, 5 and 6 all returned N=191. `MASS::polr` measures roughly
    0.34 power at that N against a 0.80 target. Both properties are pinned here.
    """
    scenario = load_scenario(REPO_ROOT / "data/scenarios/ordinal_or15_k4.json")
    result = analytic_reference(scenario)
    assert result["method"] == "whitehead_proportional_odds"
    assert result["n_total"] == 614
    assert result["power"] >= scenario.target_power

    # Minimality: one fewer observation must miss the target.
    assert (
        ordinal_proportional_odds_power(
            result["n_total"] - 1,
            scenario.effect["odds_ratio"],
            scenario.design["categories"],
            scenario.decision_rule.alpha,
            scenario.decision_rule.alternative,
        )
        < scenario.target_power
    )

    # The declared number of categories must actually move the answer.
    required = {}
    for categories in (3, 4, 5, 6):
        n = 20
        while ordinal_proportional_odds_power(n, 1.5, categories, 0.05, "two.sided") < 0.8:
            n += 1
        required[categories] = n
    assert len(set(required.values())) == len(required), (
        f"`categories` is not influencing the ordinal sample size: {required}"
    )


def test_group_sequential_boundaries_spend_exactly_alpha():
    """Regression guard for the pre-2026-08-03 group-sequential defects.

    The old implementation used a hardcoded five-entry inflation table insensitive to
    alpha, target power and alternative, and reported `two_sample_t_power` -- the
    fixed-design power at the inflated N, not the sequential operating characteristic.
    The simulator's separate `z_crit / sqrt(t)` boundary was not a valid boundary set
    either: at two looks it spent 0.05216 against a nominal 0.05.
    """
    import numpy as np
    from scipy.stats import multivariate_normal

    from powerbench.specialist_extras import group_sequential_boundaries, group_sequential_power

    # Boundary solving runs brentq over multivariate-normal CDFs, so cost grows quickly
    # with the number of looks. Two look counts per alternative exercise both the
    # single-look reduction and the multi-look recursion without making the default
    # suite slow; the 6-look case is checked separately below for the ValueError the old
    # hardcoded table raised.
    for alternative in ("two.sided", "greater"):
        for looks in (1, 3):
            boundaries = group_sequential_boundaries(looks, 0.05, alternative)
            fractions = [(index + 1) / looks for index in range(looks)]
            covariance = np.array([[(min(a, b) / max(a, b)) ** 0.5 for b in fractions] for a in fractions])
            if alternative == "two.sided":
                lower = np.array([-b for b in boundaries])
            else:
                lower = np.full(looks, -np.inf)
            continue_all = float(
                multivariate_normal.cdf(np.array(boundaries), mean=np.zeros(looks), cov=covariance, lower_limit=lower)
            )
            spent = 1.0 - continue_all
            assert abs(spent - 0.05) < 0.002, (
                f"{alternative} with {looks} looks spends alpha={spent:.5f}, not 0.05"
            )

            # Boundaries must decrease: O'Brien-Fleming is conservative early.
            assert all(a >= b for a, b in zip(boundaries, boundaries[1:])), (
                f"OBF boundaries must be non-increasing, got {boundaries}"
            )

    # A single look must reduce to the fixed-design critical value.
    assert group_sequential_boundaries(1, 0.05, "two.sided")[0] == pytest.approx(1.959964, abs=1e-4)

    # Six looks must work; the old table raised ValueError beyond five.
    assert len(group_sequential_boundaries(6, 0.05, "two.sided")) == 6

    # Reported power must be the sequential characteristic, which exceeds the
    # fixed-design power at the same N because there are multiple chances to stop.
    from powerbench.references import two_sample_t_power

    sequential = group_sequential_power(100, 0.4, 3, 0.05, "two.sided")
    fixed = two_sample_t_power(100, 100, 0.4, 0.05, "two.sided")
    assert sequential != pytest.approx(fixed, abs=1e-6), (
        "sequential power is identical to fixed-design power, which means the interim "
        "looks are not entering the calculation"
    )


def test_logistic_reference_matches_independent_r_glm_benchmark():
    """Regression guard for the pre-2026-08-03 logistic defect.

    The old implementation evaluated the binomial variance only at the baseline
    probability, ignoring that the exposed arm sits at `expit(logit(p0) + beta)`. It
    shipped N=910 where the Demidenko information gives 856, and R `glm` Monte Carlo
    measures 0.805 power at 856. The second fixture case pins the pwrss
    normal-predictor result as a documented *assumption difference*, so a future
    cross-tool run cannot silently reinterpret it as a defect.
    """
    from powerbench.references import logistic_regression_power

    fixture = json.loads(
        Path(REPO_ROOT / "data/benchmarks/logistic_regression_r_glm.json").read_text(encoding="utf-8")
    )
    binary_case = fixture["cases"][0]
    inputs, expected = binary_case["inputs"], binary_case["expected"]
    observed = logistic_regression_power(
        inputs["n_total"],
        inputs["odds_ratio"],
        inputs["p_baseline"],
        inputs["predictor_type"],
        inputs["alpha"],
        inputs["alternative"],
    )
    assert abs(observed - expected["power"]) <= binary_case["tolerance"], (
        f"Demidenko reference gives {observed:.4f}, R glm measured {expected['power']:.4f}"
    )

    scenario = load_scenario(REPO_ROOT / "data/scenarios/logistic_or15_p030.json")
    result = analytic_reference(scenario)
    assert result["n_total"] == 856
    assert result["method"] == "demidenko_logistic_wald"

    # The exposed-arm probability must actually enter the calculation: a formula that
    # only reads p_baseline is insensitive to swapping the direction of the odds ratio
    # around p = 0.5, which is precisely the old defect.
    below = logistic_regression_power(400, 2.0, 0.20, "binary", 0.05, "two.sided")
    above = logistic_regression_power(400, 2.0, 0.50, "binary", 0.05, "two.sided")
    assert abs(below - above) > 0.01


def test_ordinal_reference_matches_independent_r_polr_benchmark():
    """The Whitehead reference must agree with MASS::polr, not just with itself."""
    fixture = json.loads(
        Path(REPO_ROOT / "data/benchmarks/ordinal_regression_r_polr.json").read_text(encoding="utf-8")
    )
    for case in fixture["cases"]:
        inputs, expected = case["inputs"], case["expected"]
        observed = ordinal_proportional_odds_power(
            inputs["n_total"],
            inputs["odds_ratio"],
            inputs["categories"],
            inputs["alpha"],
            inputs["alternative"],
        )
        assert abs(observed - expected["power"]) <= case["tolerance"], (
            f"{case['label']}: Whitehead reference gives {observed:.4f}, "
            f"MASS::polr measured {expected['power']:.4f}"
        )



