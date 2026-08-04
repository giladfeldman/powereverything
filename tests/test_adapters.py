"""Adapter contract: declining honestly matters as much as answering correctly."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from powerbench.adapters import RPwrAdapter, RPwrssAdapter
from powerbench.adapters.r_pwr import _resolve_rscript
from powerbench.parameterization import classify_difference
from powerbench.reference_parameterization import reference_parameterization
from powerbench.references import analytic_reference
from powerbench.registry import automated_adapters
from powerbench.schema import load_scenario


def _rscript_is_runnable() -> bool:
    resolved = _resolve_rscript()
    if resolved == "Rscript" and shutil.which("Rscript") is None:
        return False
    try:
        return subprocess.run([resolved, "--version"], capture_output=True, timeout=30, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


requires_r = pytest.mark.skipif(not _rscript_is_runnable(), reason="Rscript not available")


def test_registry_declares_every_adapter_once():
    adapters = automated_adapters()
    ids = [adapter.id for adapter in adapters]
    assert len(ids) == len(set(ids)), f"duplicate adapter ids: {ids}"
    assert {"r.pwr", "r.pwrss", "r.gsdesign", "r.rpact", "r.webpower", "r.powersurvepi"} <= set(ids)


def test_every_registered_adapter_declares_a_version():
    for adapter in automated_adapters():
        assert adapter.version and adapter.version != "unknown", (
            f"{adapter.id} does not declare its tool version, so version drift is invisible"
        )


def test_adapters_decline_rather_than_guess():
    """An adapter must return `unsupported` for a design it cannot represent.

    Forcing a number for a design the tool does not implement is worse than silence: it
    manufactures false corroboration.
    """
    scenario = load_scenario("data/scenarios/welch_t_heteroscedastic.json")
    for adapter in automated_adapters():
        if adapter.supports(scenario):
            continue
        result = adapter.run(scenario)
        assert result["status"] == "unsupported"
        assert result.get("reason"), f"{adapter.id} declined without saying why"


def test_pwrss_declines_a_continuous_predictor_logistic_design(tmp_path):
    """A continuous predictor is a different estimand, so it must be declined, not matched.

    This is the guard against the exact comparison error the adapter exists to avoid:
    powering a one-SD change in a continuous predictor and reporting it against a
    two-group contrast.
    """
    import json

    payload = json.loads(open("data/scenarios/logistic_or15_p030.json", encoding="utf-8").read())
    payload["design"]["predictor_type"] = "continuous"
    path = tmp_path / "logistic_continuous.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    adapter = RPwrssAdapter()
    assert not adapter.supports(load_scenario(path))
    assert adapter.run(load_scenario(path))["status"] == "unsupported"


@requires_r
def test_pwrss_independently_confirms_the_corrected_logistic_sample_size():
    """The strongest available check on the 2026-08-03 logistic correction.

    Called with a matched Bernoulli(0.5) predictor, pwrss returns exactly the sample size
    PowerBench derives from the Demidenko information. Called with its own default
    (standard normal) it returns 249 -- a different estimand, which is why the adapter
    passes the predictor distribution explicitly.
    """
    scenario = load_scenario("data/scenarios/logistic_or15_p030.json")
    scenario.validate()
    reference = analytic_reference(scenario)
    result = RPwrssAdapter().run(scenario)
    assert result["status"] == "ok", result
    assert result["result"]["n_total"] == reference["n_total"] == 856


@requires_r
def test_pwr_and_powerbench_agree_on_every_method_pwr_supports():
    """Seven methods, live R, exact agreement -- classified through the real taxonomy."""
    adapter = RPwrAdapter()
    checked = 0
    for name in (
        "two_sample_t_balanced",
        "paired_t_dz_040",
        "chi_square_gof_three_category",
        "one_way_anova_f025_k3",
        "linear_regression_f2_015_p3",
        "incremental_regression_f2_015",
        "correlation_two_sided",
    ):
        scenario = load_scenario(f"data/scenarios/{name}.json")
        scenario.validate()
        if not adapter.supports(scenario):
            continue
        reference = analytic_reference(scenario)
        result = adapter.run(scenario)
        assert result["status"] == "ok", result
        classification = classify_difference(
            reference["n_total"],
            result["result"]["n_total"],
            reference_parameterization(scenario.model),
            adapter.parameterization(scenario.model),
            tool_status=result["status"],
        )
        assert classification.category in {"compatible", "rounding_display"}, (
            f"{name}: {classification.category} -- {classification.explanation}"
        )
        checked += 1
    assert checked == 7, f"expected 7 live pwr comparisons, ran {checked}"


# ---------------------------------------------------------------------------
# 2026-08-04 coverage expansion: pwrss t-family/ANCOVA/contrast, gsDesign,
# rpact, WebPower, powerSurvEpi. Every pinned integer below was first produced
# by a standalone R prototype run against the package directly, then the
# adapter was required to reproduce it -- the numbers are external ground
# truth, not copies of PowerBench's answers (PowerBench's own N is asserted
# separately where the tools legitimately differ).
# ---------------------------------------------------------------------------


def _classified(scenario_name: str, adapter):
    scenario = load_scenario(f"data/scenarios/{scenario_name}.json")
    scenario.validate()
    reference = analytic_reference(scenario)
    result = adapter.run(scenario)
    assert result["status"] == "ok", result
    tolerance = getattr(adapter, "tolerance_for", lambda _m, default=0.02: default)(scenario.model)
    classification = classify_difference(
        reference["n_total"],
        result["result"]["n_total"],
        reference_parameterization(scenario.model),
        adapter.parameterization(scenario.model),
        tool_status=result["status"],
        relative_tolerance=tolerance,
    )
    return reference, result["result"], classification


@requires_r
def test_pwrss_covers_the_t_family_designs_pwr_cannot():
    """Unbalanced pooled t and Welch t, both exact against the R prototype."""
    reference, tool, classification = _classified("two_sample_t_unbalanced", RPwrssAdapter())
    assert (tool["n1"], tool["n2"], tool["n_total"]) == (196, 294, 490)
    assert reference["n_total"] == 490
    assert classification.category == "compatible", classification.explanation

    reference, tool, classification = _classified("welch_t_heteroscedastic", RPwrssAdapter())
    assert (tool["n1"], tool["n2"], tool["n_total"]) == (116, 174, 290)
    assert reference["n_total"] == 290
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_powersurvepi_is_a_second_independent_welch_confirmation():
    from powerbench.adapters import RPowerSurvEpiAdapter

    reference, tool, classification = _classified("welch_t_heteroscedastic", RPowerSurvEpiAdapter())
    assert (tool["n1"], tool["n2"], tool["n_total"]) == (116, 174, 290)
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_pwrss_ancova_converts_the_covariate_adjusted_effect():
    """f = .20 with R2 = .25 must become eta2 from f2/(1-R2); the naive call returns 200."""
    reference, tool, classification = _classified("ancova_two_group_f020", RPwrssAdapter())
    assert tool["n_total"] == 150
    assert reference["n_total"] == 150
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_pwrss_planned_contrast_realizes_the_declared_mean_contract():
    reference, tool, classification = _classified("planned_contrast_three_group", RPwrssAdapter())
    assert tool["n_total"] == 129
    assert reference["n_total"] == 129
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_pwrss_noninferiority_sits_inside_tolerance():
    """pwrss puts the noncentrality under the null margin, PowerBench shifts the
    alternative; the approximations differ by 2 of 102 observations (1.96%), inside the
    2% closed-form tolerance."""
    reference, tool, classification = _classified("noninferiority_t_margin05", RPwrssAdapter())
    assert tool["n_total"] == 100
    assert reference["n_total"] == 102
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_pwr_covers_the_moderation_increment_exactly():
    reference, tool, classification = _classified("moderation_interaction_f2_020", RPwrAdapter())
    assert tool["n_total"] == 397
    assert reference["n_total"] == 397
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_webpower_factorial_term_agrees_exactly():
    from powerbench.adapters import RWebPowerAdapter

    reference, tool, classification = _classified("factorial_anova_2x2_interaction", RWebPowerAdapter())
    assert tool["n_total"] == 128
    assert reference["n_total"] == 128
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_webpower_mediation_is_a_declared_sobel_difference_not_a_defect():
    """WebPower powers the Sobel z (N = 183); PowerBench powers joint significance
    (N = 119). The declared test variant must absorb the gap: anything classified
    needs_review here would be a comparison error surfacing as a false defect."""
    from powerbench.adapters import RWebPowerAdapter

    reference, tool, classification = _classified("mediation_indirect_a03_b03", RWebPowerAdapter())
    assert tool["n_total"] == 183
    assert reference["n_total"] == 119
    assert classification.category == "df_or_test_variant", classification.explanation
    assert classification.is_assumption_difference
    assert not classification.needs_human


@requires_r
def test_gsdesign_group_sequential_and_schoenfeld_logrank():
    from powerbench.adapters import RGsDesignAdapter

    reference, tool, classification = _classified("group_sequential_t_d040_looks2", RGsDesignAdapter())
    # gsDesign inflates the asymptotic-normal fixed N, PowerBench the exact t: 198 vs
    # 200 is the declared normal-vs-t base gap, inside the 2% tolerance.
    assert tool["n_total"] == 198
    assert reference["n_total"] == 200
    assert classification.category == "compatible", classification.explanation

    reference, tool, classification = _classified("logrank_hr15_pevent06", RGsDesignAdapter())
    assert tool["n_total"] == 319
    assert reference["n_total"] == 319
    assert classification.category == "compatible", classification.explanation


@requires_r
def test_rpact_group_sequential_matches_exactly():
    from powerbench.adapters import RRpactAdapter

    reference, tool, classification = _classified("group_sequential_t_d040_looks2", RRpactAdapter())
    assert tool["n_total"] == 200
    assert reference["n_total"] == 200
    assert classification.category == "compatible", classification.explanation


def test_specialist_declines_one_sided_meta_analysis(tmp_path):
    """metafor's Monte Carlo tests a two-sided p-value; a one-sided scenario must be
    declined, not compared against a two-sided answer. Watched failing against the
    pre-fix supports() on 2026-08-04, which accepted any alternative."""
    import json

    from powerbench.adapters import RSpecialistAdapter

    for name in ("meta_analysis_random_d030_tau02_k6", "meta_analysis_fixed_d030_k6"):
        payload = json.loads(open(f"data/scenarios/{name}.json", encoding="utf-8").read())
        payload["decision_rule"]["alternative"] = "greater"
        path = tmp_path / f"{name}_greater.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        scenario = load_scenario(path)
        adapter = RSpecialistAdapter()
        assert not adapter.supports(scenario), scenario.model
        assert adapter.run(scenario)["status"] == "unsupported"


def _mutated_scenario(tmp_path, name: str, mutate):
    import json

    payload = json.loads(open(f"data/scenarios/{name}.json", encoding="utf-8").read())
    mutate(payload)
    path = tmp_path / f"{name}_variant.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = load_scenario(path)
    scenario.validate()
    return scenario


@requires_r
def test_pwrss_matches_the_unbalanced_and_exposure_variants(tmp_path):
    """2026-08-04 Codex review findings, reproduced and then fixed: the logistic branch
    hardcoded a balanced Bernoulli(0.5), the Poisson branch dropped the scenario's
    exposure, and the non-inferiority branch omitted kappa. Each would have compared a
    different design the moment a scenario declared the variant. All three parameters are
    now wired through; the pinned numbers come from live matched prototypes. Watched red
    against the pre-fix R script: the logistic variant returned the balanced 856 against
    PowerBench's 903."""
    adapter = RPwrssAdapter()

    scenario = _mutated_scenario(
        tmp_path, "logistic_or15_p030", lambda d: d["design"].__setitem__("allocation_ratio", 1.5)
    )
    reference = analytic_reference(scenario)
    result = adapter.run(scenario)
    assert result["status"] == "ok", result
    assert result["result"]["n_total"] == reference["n_total"] == 903

    scenario = _mutated_scenario(
        tmp_path, "noninferiority_t_margin05", lambda d: d["design"].__setitem__("allocation_ratio", 1.5)
    )
    reference = analytic_reference(scenario)
    result = adapter.run(scenario)
    assert result["status"] == "ok", result
    assert result["result"]["n_total"] == reference["n_total"] == 105
    assert (result["result"]["n1"], result["result"]["n2"]) == (42, 63)

    scenario = _mutated_scenario(
        tmp_path, "poisson_rr15_rate02", lambda d: d["design"].__setitem__("exposure", 2)
    )
    reference = analytic_reference(scenario)
    result = adapter.run(scenario)
    assert result["status"] == "ok", result
    # Same ~1% approximation gap the exposure = 1 comparison shows; what matters is that
    # both tools are on the same rate scale rather than pwrss silently assuming 1.
    assert reference["n_total"] == 398
    assert result["result"]["n_total"] == 394
    classification = classify_difference(
        reference["n_total"],
        result["result"]["n_total"],
        reference_parameterization(scenario.model),
        adapter.parameterization(scenario.model),
        tool_status=result["status"],
    )
    assert classification.category == "compatible", classification.explanation
