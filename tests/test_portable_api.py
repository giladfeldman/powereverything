"""Cross-runtime checks for goal semantics and executable code, not just target searches."""
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from powerbench.api import analyze
from powerbench.capabilities import R_MODELS, capabilities
from powerbench.references import analytic_reference
from powerbench.reproducibility import export_bundle
from powerbench.schema import load_scenario


def request(model="two_sample_t", operation="plan"):
    files = {"two_sample_t": "two_sample_t_balanced", "paired_t": "paired_t_change", "correlation": "correlation_positive"}
    if model in files and Path(f"data/scenarios/{files[model]}.json").exists():
        s = load_scenario(f"data/scenarios/{files[model]}.json").to_dict()
    else:
        candidates = [load_scenario(p) for p in Path("data/scenarios").glob("*.json")]
        s = next(s.to_dict() for s in candidates if s.model == model)
    s["goal"] = {"plan": "required_sample_size", "power": "achieved_power", "detectable_effect": "sensitivity"}[operation]
    return {"operation": operation, "scenario": s}


def test_goal_dispatch_cannot_silently_return_required_n():
    s = load_scenario("data/scenarios/two_sample_t_balanced.json")
    with pytest.raises(ValueError, match="explicit sample"):
        analytic_reference(replace(s, goal="sensitivity"))
    q = request(operation="power")
    q["sample"] = {"n1": 50, "n2": 50}
    r = analyze(q)
    assert r["result"]["n_total"] == 100
    assert .49 < r["result"]["power"] < .53
    assert r["operation"] == "power"


def test_default_does_not_overwrite_explicit_history():
    q = request()
    del q["scenario"]["target_power"]
    assert analyze(q)["normalized_request"]["scenario"]["target_power"] == .95
    q["scenario"]["target_power"] = .8
    assert analyze(q)["result"]["n_total"] == 200


@pytest.mark.parametrize("sample", [{"n1": 10.5, "n2": 20}, {"n1": True, "n2": 20}, {"n1": 20, "n2": 20, "n_total": 41}])
def test_invalid_sample_rejected(sample):
    q = request(operation="power")
    q["sample"] = sample
    with pytest.raises(ValueError):
        analyze(q)


def test_nonfinite_and_conflicting_goals_rejected():
    q = request()
    q["scenario"]["effect"]["cohens_d"] = float("nan")
    with pytest.raises(ValueError, match="Nonfinite"):
        analyze(q)
    q = request()
    q["operation"] = "power"
    with pytest.raises(ValueError, match="conflict"):
        analyze(q)


def test_sensitivity_keeps_sample_fixed_and_exposes_unreachable_target():
    q = request(operation="detectable_effect")
    q["sample"] = {"n1": 100, "n2": 100}
    r = analyze(q)
    assert .39 < r["result"]["detectable_effect"] < .41
    assert r["result"]["power"] == pytest.approx(.8, abs=1e-8)
    q["domain"] = {"lower": .001, "upper": .01}
    assert analyze(q)["status"] == "unreachable"


@pytest.mark.parametrize("model", sorted(R_MODELS))
@pytest.mark.parametrize("operation", ["plan", "power", "detectable_effect"])
def test_independent_base_r_reproduction(model, operation, tmp_path):
    q = request(model, operation)
    # Use an exactly declared, balanced fixed sample, large enough for all predictors.
    if operation != "plan":
        q["sample"] = {"n1": 100, "n2": 100} if model in {"two_sample_t", "welch_t"} else {"n_total": 300}
    result = analyze(q)
    assert result["status"] == "complete"
    script = next(x["code"] for x in result["reproduction"] if x["language"] == "r")
    source = tmp_path / "reproduce.R"
    source.write_text(script, encoding="utf-8")
    from powerbench.adapters.r_pwr import _resolve_rscript
    run = subprocess.run([_resolve_rscript("Rscript"), str(source)], capture_output=True, text=True, check=True, timeout=45)
    other = json.loads(run.stdout.strip())
    expected = result["result"]
    assert other["power"] == pytest.approx(expected["power"], abs=2e-8)
    if operation != "detectable_effect":
        assert other["n_total"] == expected["n_total"]
    else:
        assert other["effect"] == pytest.approx(expected["detectable_effect"], abs=2e-8)


def test_bundle_manifest_and_python_execution(tmp_path):
    import hashlib
    import io
    import sys
    import zipfile
    q = request()
    result = analyze(q)
    with zipfile.ZipFile(io.BytesIO(export_bundle(result))) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert "reproduce.py" in manifest["files"]
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
        code = z.read("reproduce.py").decode()
    # Run generated code; never replace it with an expected answer.
    output = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert json.loads(output.stdout)["result"] == result["result"]
    assert all(item["python"] for item in capabilities()["methods"])
