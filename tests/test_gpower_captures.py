"""G*Power captures: a human in the loop must not weaken the evidence.

G*Power cannot be scripted, so its comparisons are recorded by hand. That introduces two
ways for the record to become quietly wrong -- an edit after the fact, and a scenario that
changed after capture -- and both must surface as a refusal rather than as a number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from powerbench.adapters.manual_gpower import (
    REQUIRED_FIELDS,
    ManualGPowerAdapter,
    capture_signature,
    scenario_hash,
)
from powerbench.schema import load_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = REPO_ROOT / "data" / "gpower_captures"
SCENARIO = "data/scenarios/two_sample_t_balanced.json"


def _capture(scenario, **overrides) -> dict:
    capture = {
        "scenario_id": scenario.id,
        "method_id": scenario.model,
        "tool_version": "3.1.9.7",
        "operating_system": "Windows 11",
        "captured_on": "2026-08-03",
        "captured_by": "0000-0000-0000-0000",
        "gui_test_family": "t tests - Means: Difference between two independent means",
        "gui_inputs": {"tails": "Two", "effect_size_d": 0.4, "alpha_err_prob": 0.05, "power": 0.8},
        "gui_outputs": {"total_sample_size": 200, "actual_power": 0.8036475},
        "scenario_hash_at_capture": scenario_hash(scenario),
        "screenshots": [],
    }
    capture.update(overrides)
    capture["signature"] = capture_signature(capture)
    return capture


def _write(directory: Path, capture: dict) -> ManualGPowerAdapter:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    return ManualGPowerAdapter(directory=directory)


def test_scenario_hash_ignores_simulation_settings(tmp_path):
    """Tuning replications must not invalidate every capture.

    If it did, people would learn to ignore staleness warnings -- which are the whole
    mechanism protecting these records.
    """
    payload = json.loads((REPO_ROOT / SCENARIO).read_text(encoding="utf-8"))
    original = load_scenario(REPO_ROOT / SCENARIO)

    payload["simulation"] = {"replications": 999, "seed": 12345}
    path = tmp_path / "retuned.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert scenario_hash(load_scenario(path)) == scenario_hash(original)


def test_scenario_hash_changes_when_the_design_changes(tmp_path):
    payload = json.loads((REPO_ROOT / SCENARIO).read_text(encoding="utf-8"))
    original = load_scenario(REPO_ROOT / SCENARIO)

    payload["effect"]["cohens_d"] = 0.5
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert scenario_hash(load_scenario(path)) != scenario_hash(original)


def test_valid_capture_is_reported(tmp_path):
    scenario = load_scenario(REPO_ROOT / SCENARIO)
    adapter = _write(tmp_path / "captures", _capture(scenario))
    result = adapter.run(scenario)
    assert result["status"] == "ok"
    assert result["result"]["n_total"] == 200
    assert result["package"] == "G*Power"
    assert result["captured_by"]


def test_edited_capture_is_refused(tmp_path):
    """A number changed after signing must not be served as evidence."""
    scenario = load_scenario(REPO_ROOT / SCENARIO)
    capture = _capture(scenario)
    capture["gui_outputs"] = {"total_sample_size": 120, "actual_power": 0.80}  # no re-sign
    adapter = _write(tmp_path / "captures", capture)

    result = adapter.run(scenario)
    assert result["status"] == "error"
    assert "edited since it was signed" in result["reason"]


def test_stale_capture_is_refused_not_reported(tmp_path):
    """A capture answering a design that no longer exists must not be shown as a result."""
    scenario = load_scenario(REPO_ROOT / SCENARIO)
    adapter = _write(tmp_path / "captures", _capture(scenario, scenario_hash_at_capture="deadbeefdeadbeef"))

    result = adapter.run(scenario)
    assert result["status"] == "unavailable"
    assert result["stale_capture"] is True
    assert "no longer exists" in result["reason"]


def test_incomplete_capture_is_refused(tmp_path):
    scenario = load_scenario(REPO_ROOT / SCENARIO)
    capture = _capture(scenario)
    del capture["gui_inputs"]
    adapter = _write(tmp_path / "captures", capture)

    result = adapter.run(scenario)
    assert result["status"] == "error"
    assert "missing required fields" in result["reason"]


def test_missing_capture_declines_honestly(tmp_path):
    """No capture is `unsupported`, never a guess."""
    adapter = ManualGPowerAdapter(directory=tmp_path / "empty")
    result = adapter.run(load_scenario(REPO_ROOT / SCENARIO))
    assert result["status"] == "unsupported"
    assert "cannot be scripted" in result["reason"]


def test_adapter_never_executes_anything():
    """The adapter must read files only. G*Power has no scriptable interface at all."""
    source = (REPO_ROOT / "powerbench" / "adapters" / "manual_gpower.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "Popen", "shutil.which"):
        assert forbidden not in source, (
            f"manual_gpower.py references {forbidden!r}; captures are read, never run"
        )


@pytest.mark.parametrize("path", sorted(CAPTURE_DIR.glob("*.json")) if CAPTURE_DIR.exists() else [])
def test_committed_captures_are_signed_current_and_complete(path: Path):
    """Every committed capture must verify. An unverifiable one is not evidence."""
    capture = json.loads(path.read_text(encoding="utf-8"))

    missing = [field for field in REQUIRED_FIELDS if field not in capture]
    assert not missing, f"{path.name} is missing {missing}"

    assert capture.get("signature") == capture_signature(capture), (
        f"{path.name} has been edited since signing; re-capture rather than re-signing"
    )

    scenarios = {
        json.loads(p.read_text(encoding="utf-8"))["id"]: p
        for p in sorted((REPO_ROOT / "data" / "scenarios").glob("*.json"))
    }
    assert capture["scenario_id"] in scenarios, f"{path.name} names an unknown scenario"
    current = scenario_hash(load_scenario(scenarios[capture["scenario_id"]]))
    assert capture["scenario_hash_at_capture"] == current, (
        f"{path.name} is stale: the scenario changed after capture. Re-run G*Power."
    )

    for screenshot in capture.get("screenshots", []):
        assert (REPO_ROOT / screenshot).exists(), (
            f"{path.name} names screenshot {screenshot}, which does not exist; "
            "a capture without its screenshot is not verifiable"
        )
