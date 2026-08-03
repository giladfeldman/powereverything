"""Correctness gate: every analytic reference must agree with the independent simulator.

The engine already computes this comparison for every plan
(`studio/server.py::_reference_simulation_alignment`) and shows the verdict to users,
but until this module existed nothing asserted its *value* — the only assertion was
`assert result["reference_simulation_alignment"]["status"]`, which is truthy for the
failing status `"requires_assumption_review"` as well as for `"compatible"`.

Every other numeric test in the suite is self-referential: `required_n_*` is a
`while power < target: n += 1` loop, so `assert power >= target_power` is a tautology
that holds no matter how wrong the formula is. This gate is the one test that can
falsify a formula, because the simulator shares no code with the analytic reference.

Design notes that matter if you change anything here:

* **Multiple seeds, majority verdict.** At the replication counts the shipped scenarios
  use (2_000), a single seed is a lottery: `tost_equivalence` reads as misaligned on the
  committed seed and aligns comfortably at 12_000 replications. With ~28 scenarios and a
  nominal 5% excursion rate, a single-seed gate would be expected to fail ~1.4 times per
  run on correct code. Majority-of-three drives that below 1% while still catching a real
  defect, which fails on every seed.
* **Replications are raised here.** The gate overrides each scenario's committed
  `replications` so the Monte Carlo interval is tight enough to be informative
  (MC SE ~= 0.003 at p ~= 0.8).
* **Allowlist entries are structured, not bare strings.** An allowlisted scenario is
  still tested — against a documented envelope instead of the CI. A sign flip or a
  documented 2pp gap growing to 20pp still fails.

Marked `slow`: `powerbench/simulation.py` runs a per-replication Python loop, so a full
pass is a nightly job, not a pre-commit hook. Run it with `pytest -m slow`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from powerbench.references import analytic_reference
from powerbench.schema import load_scenario
from powerbench.simulation import simulate

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"

# Seeds are hardcoded, never time-derived: a flaky gate on a scientific engine is worse
# than no gate, because it trains you to ignore it.
GATE_SEEDS = (20260801, 424242, 99)
GATE_REPLICATIONS = 12_000

# Absorbs discretization that is not a formula error -- notably chi-square independence,
# where `min_expected_count` forces the search to start at a floor N whose power already
# exceeds the target. Still far tighter than the defects this gate exists to catch
# (ordinal was off by 0.53, logistic by 0.028).
GATE_TOLERANCE = 0.01

# Models whose simulator draws two arms; everything else is sized by total N.
TWO_ARM_MODELS = {
    "two_sample_t",
    "welch_t",
    "two_sample_proportion",
    "tost_equivalence",
    "noninferiority_t",
    "bayes_factor_t",
    "group_sequential_t",
    "logrank_two_arm",
    "rope_equivalence_t",
}


@dataclass(frozen=True)
class DocumentedDivergence:
    """A scenario whose analytic reference legitimately differs from the simulator.

    This is *not* an exemption from testing. The scenario is still checked, against the
    envelope declared here, so that a documented divergence cannot silently grow or flip
    sign. Adding an entry requires a written case study on disk.
    """

    scenario_id: str
    reason: str
    doc: str
    expected_direction: str  # "reference_above" | "reference_below"
    max_abs_gap: float

    def envelope_contains(self, reference_power: float, simulated_power: float) -> bool:
        gap = reference_power - simulated_power
        if self.expected_direction == "reference_above" and gap < 0:
            return False
        if self.expected_direction == "reference_below" and gap > 0:
            return False
        return abs(gap) <= self.max_abs_gap


# Deliberately short. An allowlist entry is a standing claim that a scenario *cannot* be
# checked strictly, so it must be earned at the gate's own replication count and seed set.
# Five entries were drafted on 2026-08-03 from 2,000-replication readings; at 12,000
# replications across three seeds, `linear_regression` (3/3 aligned),
# `moderation` (3/3) and `poisson` (3/3) all agree and were removed. Measuring at low
# replications turns Monte Carlo noise into a permanent exemption -- see PM-012.
ALLOWLIST: tuple[DocumentedDivergence, ...] = (
    DocumentedDivergence(
        scenario_id="chi_square_independence_2x2",
        reason=(
            "Two effects, both conservative, and neither is a coding error. The declared "
            "min_expected_count of 5 forces the sample-size search to start at N=50, so the "
            "reported power is a floor rather than a solution at the target; and the Cohen's w "
            "noncentral chi-square approximation understates power at small expected cell counts. "
            "The reference therefore sits about 2.5 points below the simulation on every seed."
        ),
        doc="docs/discrepancies/chi_square_independence_floor.md",
        expected_direction="reference_below",
        max_abs_gap=0.05,
    ),
    DocumentedDivergence(
        scenario_id="incremental_regression_f2_015",
        reason=(
            "Fixed-versus-random predictor difference: the reference follows the pwr.f2.test "
            "fixed-design convention, conditioning on the predictor matrix, while the simulation "
            "draws fresh random predictors each replication, which averages power over the "
            "sampling distribution of X and yields slightly less. This case was written up before "
            "the 2026-08-03 correctness pass and remains the only member of the regression family "
            "that still exceeds tolerance at gate replications."
        ),
        doc="docs/discrepancies/incremental_regression.md",
        expected_direction="reference_above",
        max_abs_gap=0.05,
    ),
)

ALLOWLIST_BY_ID = {entry.scenario_id: entry for entry in ALLOWLIST}


def scenario_paths() -> list[Path]:
    """Glob rather than enumerate, so a new scenario is enrolled in the gate for free."""
    return sorted(SCENARIO_DIR.glob("*.json"))


def _scenario_id(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["id"]


def run_alignment(path: Path, seed: int, replications: int = GATE_REPLICATIONS) -> dict:
    """Return the reference power, the simulated interval, and the verdict for one seed."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["simulation"] = {"replications": replications, "seed": seed}

    scratch = REPO_ROOT / ".tmp" / "alignment"
    scratch.mkdir(parents=True, exist_ok=True)
    scratch_path = scratch / f"{payload['id']}_seed{seed}.json"
    scratch_path.write_text(json.dumps(payload), encoding="utf-8")

    scenario = load_scenario(scratch_path)
    scenario.validate()
    reference = analytic_reference(scenario)
    if scenario.model in TWO_ARM_MODELS:
        simulation = simulate(scenario, n1=reference["n1"], n2=reference["n2"])
    else:
        simulation = simulate(scenario, n_total=reference["n_total"])

    low, high = simulation["mc_ci95"]
    reference_power = float(reference["power"])
    return {
        "model": scenario.model,
        "reference_power": reference_power,
        "simulated_power": float(simulation["power"]),
        "ci_low": float(low),
        "ci_high": float(high),
        "aligned": (low - GATE_TOLERANCE) <= reference_power <= (high + GATE_TOLERANCE),
    }


@pytest.mark.slow
@pytest.mark.parametrize("path", scenario_paths(), ids=_scenario_id)
def test_analytic_reference_agrees_with_independent_simulation(path: Path) -> None:
    scenario_id = _scenario_id(path)
    runs = [run_alignment(path, seed) for seed in GATE_SEEDS]
    aligned_count = sum(run["aligned"] for run in runs)
    allowed = ALLOWLIST_BY_ID.get(scenario_id)

    detail = "\n".join(
        f"  seed={seed}: reference={run['reference_power']:.4f} "
        f"simulated={run['simulated_power']:.4f} "
        f"ci=[{run['ci_low']:.4f}, {run['ci_high']:.4f}] "
        f"{'aligned' if run['aligned'] else 'MISALIGNED'}"
        for seed, run in zip(GATE_SEEDS, runs)
    )

    if allowed is None:
        assert aligned_count >= 2, (
            f"{scenario_id}: the analytic reference disagrees with the independent "
            f"simulation on {len(runs) - aligned_count} of {len(runs)} seeds.\n{detail}\n"
            "Either the analytic formula is wrong, or the analytic and simulated designs "
            "make different assumptions. If it is the latter, write the case study in "
            "docs/discrepancies/ and add a DocumentedDivergence entry -- do not widen "
            "the tolerance."
        )
        return

    # Allowlisted: still tested, against the documented envelope.
    for seed, run in zip(GATE_SEEDS, runs):
        assert allowed.envelope_contains(run["reference_power"], run["simulated_power"]), (
            f"{scenario_id} is an allowlisted divergence, but it has moved outside its "
            f"documented envelope (direction={allowed.expected_direction}, "
            f"max_abs_gap={allowed.max_abs_gap}).\n{detail}\n"
            f"Documented in {allowed.doc}. Re-examine the divergence before widening it."
        )


@pytest.mark.slow
def test_allowlist_has_no_stale_entries() -> None:
    """An allowlisted scenario that now aligns must be removed from the allowlist.

    Without this, a divergence fixed as a side effect of unrelated work keeps its
    permanent amnesty, and the allowlist slowly becomes a list of things nobody checks.
    """
    for entry in ALLOWLIST:
        path = SCENARIO_DIR / f"{entry.scenario_id}.json"
        if not path.exists():
            matches = [p for p in scenario_paths() if _scenario_id(p) == entry.scenario_id]
            assert matches, f"allowlist references unknown scenario {entry.scenario_id!r}"
            path = matches[0]
        runs = [run_alignment(path, seed) for seed in GATE_SEEDS]
        assert sum(run["aligned"] for run in runs) < 2, (
            f"{entry.scenario_id} now agrees with the simulation on a majority of seeds. "
            "Remove its DocumentedDivergence entry so the strict gate applies again."
        )


def test_allowlist_entries_are_justified() -> None:
    """Cheap, fast structural checks on the allowlist -- deliberately not marked slow."""
    seen: set[str] = set()
    for entry in ALLOWLIST:
        assert entry.scenario_id not in seen, f"duplicate allowlist entry {entry.scenario_id!r}"
        seen.add(entry.scenario_id)
        assert len(entry.reason) >= 80, (
            f"{entry.scenario_id}: `reason` must explain *why* the divergence is legitimate "
            "in enough detail to be reviewable, not just name it."
        )
        assert entry.expected_direction in {"reference_above", "reference_below"}
        assert 0 < entry.max_abs_gap < 0.5, (
            f"{entry.scenario_id}: a gap of {entry.max_abs_gap} is too large to call a "
            "documented divergence -- that is a defect."
        )
        doc_path = REPO_ROOT / entry.doc
        assert doc_path.exists(), (
            f"{entry.scenario_id}: allowlisted divergences require a written case study; "
            f"{entry.doc} does not exist."
        )


def test_every_model_has_at_least_one_scenario() -> None:
    """The gate can only protect models that have a committed scenario."""
    from typing import get_args

    from powerbench.schema import Model

    covered = {json.loads(path.read_text(encoding="utf-8"))["model"] for path in scenario_paths()}
    missing = sorted(set(get_args(Model)) - covered)
    assert not missing, (
        f"models with no committed scenario are invisible to the alignment gate: {missing}"
    )
