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
    assert "r.pwr" in ids and "r.pwrss" in ids


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
