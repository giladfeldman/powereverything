"""Regression controls for defects found by the 2026-10-23 takeover review (Sonnet seat).

Each test was observed failing on commit 2980d01 before its repair.
"""
from __future__ import annotations

import pytest

from powerbench.api import analyze
from powerbench.planning import _plan_report, make_plan, request_from_fields
from powerbench.sharing import anonymous_snapshot

LOGRANK = {"model": "logrank_two_arm", "effect": 0.7, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1}


def test_wizard_defaults_are_disclosed_in_ledger_and_paragraph():
    """Blank survival fields are filled by the parser; the result must say so."""
    result = analyze(request_from_fields(LOGRANK))
    defaults = result["reporting"]["defaults_applied"]
    assert defaults["design.control_hazard"] == 1.0
    assert defaults["design.followup_years"] == 1.0
    assert "control_hazard = 1.0" in result["reporting"]["apa"]


def test_supplied_values_are_not_reported_as_defaults():
    payload = {**LOGRANK, "control_hazard": 1, "followup_years": 1, "accrual_years": 0, "dropout_hazard": 0}
    defaults = analyze(request_from_fields(payload))["reporting"]["defaults_applied"]
    assert not any(key.startswith(("design.control_hazard", "design.followup_years")) for key in defaults)


def test_logrank_hazard_ratio_sensitivity_rederives_event_probability():
    rows = make_plan(LOGRANK)["sensitivity"]
    assert [row["status"] for row in rows] == ["complete"] * 5
    totals = [row["n_total"] for row in rows]
    # Multipliers scale log(HR); larger multipliers are larger effects and need fewer participants.
    assert totals == sorted(totals, reverse=True)


def test_anonymous_snapshot_keeps_mediation_direct_path():
    payload = {"model": "mediation_indirect", "a_path": 0.3, "b_path": 0.3, "direct_cprime": 0.2, "alpha": 0.05, "target_power": 0.95}
    shared = anonymous_snapshot(analyze(request_from_fields(payload)))
    assert shared["normalized_request"]["scenario"]["effect"]["direct_cprime"] == 0.2


def test_anonymous_snapshot_refuses_to_drop_a_scientific_field(monkeypatch):
    """Any schema field missing from the share allowlist must stop the share."""
    from powerbench import sharing
    payload = {"model": "mediation_indirect", "a_path": 0.3, "b_path": 0.3, "direct_cprime": 0.2, "alpha": 0.05, "target_power": 0.95}
    result = analyze(request_from_fields(payload))
    monkeypatch.setattr(sharing, "_EFFECT", sharing._EFFECT - {"direct_cprime"})
    with pytest.raises(ValueError, match="effect.direct_cprime"):
        sharing.anonymous_snapshot(result)


def test_share_allowlist_covers_every_schema_field():
    from powerbench import sharing
    from powerbench.schema import COMMON_DESIGN_FIELDS, DESIGN_FIELDS, EFFECT_FIELDS
    categorical = {"predictor_type", "tested_term", "bf_method", "distribution"}
    assert set().union(*EFFECT_FIELDS.values()) - {"parameterization"} <= sharing._EFFECT
    assert set(COMMON_DESIGN_FIELDS).union(*DESIGN_FIELDS.values()) - categorical <= sharing._DESIGN


@pytest.mark.parametrize("bad", [None, [1], {"x": 1}])
def test_non_numeric_attrition_is_a_value_error(bad):
    with pytest.raises(ValueError):
        request_from_fields({"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1, "attrition_rate": bad})


def _report_line(tool):
    plan = make_plan({"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1})
    from powerbench.planning import scenario_from_fields
    scenario, *_ = scenario_from_fields({"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1})
    report = _plan_report(scenario, plan["reference"], plan["simulation"], tool, None, plan["reporting"])
    return next(line for line in report.splitlines() if line.startswith("**Tool comparison:**"))


def test_plan_report_tool_line_compares_sample_sizes():
    assert "differs" in _report_line({"status": "ok", "adapter": "r.pwr", "result": {"n_total": 330}})
    assert "330" in _report_line({"status": "ok", "adapter": "r.pwr", "result": {"n_total": 330}})
    assert "matches" in _report_line({"status": "ok", "adapter": "r.pwr", "result": {"n_total": 328}})
    assert "not compared" in _report_line({"status": "unsupported", "reason": "x"})
    assert "ok" != _report_line({"status": "ok", "adapter": "r.pwr", "result": {}}).split(":** ")[1]


def test_assumption_sensitivity_is_public_and_matches_native_plan():
    """The browser planner has no make_plan; it needs the same curve through a public call."""
    from powerbench.planning import assumption_sensitivity
    fields = {"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1}
    native = make_plan(fields)
    browser = assumption_sensitivity(fields)
    assert browser["sensitivity"] == native["sensitivity"]
    assert browser["heterogeneity_sensitivity"] == native["heterogeneity_sensitivity"]
    assert browser["sensitivity_policy_version"] == native["sensitivity_policy_version"]
    assert [row["multiplier"] for row in browser["sensitivity"]] == [0.5, 0.75, 1.0, 1.25, 1.5]


def test_assumption_sensitivity_refuses_fixed_sample_goals():
    from powerbench.planning import assumption_sensitivity
    with pytest.raises(ValueError):
        assumption_sensitivity({"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "goal": "achieved_power", "n1": 50, "n2": 50})


# Sonnet fix-delta review, 2026-10-23: defaults disclosure must survive sharing and cover
# every substituted planning value, and a disclosure line must match the scenario it describes.

def test_anonymous_snapshot_keeps_default_disclosures():
    shared = anonymous_snapshot(analyze(request_from_fields(LOGRANK)))
    defaults = shared["reporting"]["defaults_applied"]
    assert defaults["design.control_hazard"] == 1.0
    assert "control_hazard = 1.0" in shared["reporting"]["apa"]
    assert all(line.startswith("Planning default applied") for line in shared["normalized_request"]["scenario"]["assumptions"])


def test_target_power_and_attrition_defaults_are_disclosed():
    fields = {"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "allocation_ratio": 1}
    defaults = analyze(request_from_fields(fields))["reporting"]["defaults_applied"]
    assert defaults["target_power"] == 0.95
    assert defaults["design.attrition_rate"] == 0
    supplied = analyze(request_from_fields({**fields, "target_power": 0.95, "attrition_rate": 0}))["reporting"]["defaults_applied"]
    assert "target_power" not in supplied and "design.attrition_rate" not in supplied


def test_forged_default_disclosure_is_rejected():
    from powerbench.planning import WIZARD_DEFAULT_PREFIX
    request = request_from_fields({"model": "two_sample_t", "effect": 0.4, "alpha": 0.05, "target_power": 0.95, "allocation_ratio": 1})
    request["scenario"]["assumptions"].append(WIZARD_DEFAULT_PREFIX + "effect.cohens_d = 0.2")
    with pytest.raises(ValueError, match="does not match"):
        analyze(request)


def test_bayes_simulation_survives_bayes_factors_beyond_float_range():
    """powerbench-review 2026-10-23: jzs_bf10_from_t now raises above exp(709); the
    simulation called it unguarded, so one huge replicate aborted the whole run."""
    from powerbench.schema import DecisionRule, Scenario
    from powerbench.simulation import simulate
    s = Scenario(id="t", title="t", framework="bayesian", goal="required_sample_size", model="bayes_factor_t",
                 target_power=0.95, effect={"cohens_d": 5.0}, design={"allocation_ratio": 1.0, "bf_threshold": 3, "bf_method": "jzs"},
                 decision_rule=DecisionRule(alpha=0.05, alternative="two.sided"), simulation={"seed": 1, "replications": 20})
    result = simulate(s, n1=600, n2=600)
    diagnostics = result["bayes_diagnostics"]
    assert diagnostics["bf10_beyond_numeric_range"] == 20
    assert diagnostics["mean_bf10"] is None and diagnostics["median_bf10"] is None
    assert result["power"] == 1.0
