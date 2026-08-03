import shutil
import subprocess

import pytest

from powerbench.adapters.r_pwr import _resolve_rscript
from powerbench.run import run


def _rscript_is_runnable() -> bool:
    """True only if Rscript can actually be executed.

    `_resolve_rscript` falls back to returning the bare string "Rscript" when nothing is
    found, so its return value cannot be used as a presence check -- it is never None.
    """
    resolved = _resolve_rscript()
    if resolved == "Rscript" and shutil.which("Rscript") is None:
        return False
    try:
        completed = subprocess.run(
            [resolved, "--version"], capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


#: The R `pwr` adapter is a genuine third-party cross-check, not a mock: it shells out to
#: Rscript and compares numbers. Where R is present that assertion should be enforced, but
#: it must skip rather than red-fail on a runner without R (CI, a fresh clone), or the
#: signal degrades into noise people learn to ignore.
requires_r = pytest.mark.skipif(
    not _rscript_is_runnable(),
    reason="Rscript not available; the R pwr cross-check cannot run on this machine",
)


def test_runner_writes_auditable_artifacts(tmp_path):
    payload = run("data/scenarios/two_sample_t_balanced.json", tmp_path)
    assert payload["analytic_reference"]["n_total"] > 0
    assert (tmp_path / "result.json").exists()
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Monte Carlo SE" in report
    assert "r.pwr" in report


def test_unbalanced_scenario_is_not_silently_sent_to_balanced_pwr(tmp_path):
    payload = run("data/scenarios/two_sample_t_unbalanced.json", tmp_path)
    pwr = next(row for row in payload["adapter_results"] if row["adapter"] == "r.pwr")
    assert pwr["status"] == "unsupported"


def test_welch_scenario_uses_unequal_variance_simulation_and_no_pooled_adapter(tmp_path):
    payload = run("data/scenarios/welch_t_heteroscedastic.json", tmp_path)
    assert payload["analytic_reference"]["method"] == "welch_satterthwaite_noncentral_t_approximation"
    assert payload["simulation"]["engine"] == "independent_numpy_scipy_simulation"
    pwr = next(row for row in payload["adapter_results"] if row["adapter"] == "r.pwr")
    assert pwr["status"] == "unsupported"


def test_chi_square_scenario_runs_multinomial_simulation(tmp_path):
    payload = run("data/scenarios/chi_square_gof_three_category.json", tmp_path)
    assert payload["analytic_reference"]["n_total"] == 181
    assert payload["simulation"]["replications_completed"] == 10000


@requires_r
def test_chi_square_scenario_agrees_with_r_pwr(tmp_path):
    """Live third-party cross-check: R `pwr` must independently produce N = 181."""
    payload = run("data/scenarios/chi_square_gof_three_category.json", tmp_path)
    pwr = next(row for row in payload["adapter_results"] if row["adapter"] == "r.pwr")
    assert pwr["status"] == "ok", f"R pwr adapter did not run: {pwr}"
    assert pwr["result"]["n_total"] == 181
