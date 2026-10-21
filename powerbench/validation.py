"""Portable external-tool comparison and adjudication, independent of PowerMate."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import powerbench

from .adapters.manual_gpower import ManualGPowerAdapter
from .adapters.r_specialist import RSpecialistAdapter
from .parameterization import classify_difference
from .reference_parameterization import reference_parameterization
from .references import analytic_reference
from .registry import automated_adapters
from .schema import load_scenario
from .simulation import simulate

CASE_STUDIES: dict[str, str] = {
    "meta_analysis_random": "docs/discrepancies/meta_analysis_random_flat_power.md",
    # Both surfaced on 2026-08-06 when the G*Power captures were wired in: neither method
    # had an external comparison before, so neither difference could appear.
    "chi_square_independence": "docs/discrepancies/chi_square_independence_floor.md",
    "one_sample_proportion": "docs/discrepancies/one_sample_proportion_sawtooth.md",
    "incremental_regression": "docs/discrepancies/incremental_regression.md",
}

def jsonable(value):
    """Coerce numpy scalars to plain Python types.

    The simulator returns numpy floats and bools, which `json.dumps` refuses. Failing at
    write time is particularly bad here because the Monte Carlo adapters take minutes --
    the work is finished and then thrown away. Coercing on the way out makes the failure
    impossible rather than merely rare.
    """
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return value
    return value

SCHEMA_VERSION = 1

SLOW_ADAPTERS = {"r.specialist"}

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

SIMULATION_REPLICATIONS = 4000

SIMULATION_SEED = 20260803

def adapters_for(skip_slow: bool) -> list:
    adapters = list(automated_adapters())
    if not any(adapter.id == "r.specialist" for adapter in adapters):
        adapters.append(RSpecialistAdapter())
    # Reads committed captures rather than launching anything, so it is cheap and is never
    # excluded by --skip-slow.
    if not any(adapter.id == "desktop.gpower" for adapter in adapters):
        adapters.append(ManualGPowerAdapter())
    if skip_slow:
        adapters = [adapter for adapter in adapters if adapter.id not in SLOW_ADAPTERS]
    # Canonical order by tool_id. Without this the order depends on whether
    # `automated_adapters()` already contained r.specialist / desktop.gpower (they
    # keep their registry position) or not (they get appended last), so two runs
    # could emit the same tools in different orders. Every downstream comparison
    # is positional, so that made unrelated tools diff against each other and the
    # matrix report stale forever. Same defect class as the cell-order fix in
    # commit e8646b5 -- fixed there for cells, missed here for tools.
    adapters.sort(key=lambda adapter: adapter.id)
    return adapters

def simulate_for(scenario, reference: dict, path: Path | None = None) -> dict | None:
    """Re-run the in-house simulation at a fixed seed and replication count.

    The complete scenario is copied in memory; no website path or temporary file is required.
    The optional path parameter is retained for compatibility.
    """
    resimulated = replace(scenario, simulation={"replications": SIMULATION_REPLICATIONS, "seed": SIMULATION_SEED})
    resimulated.validate()
    try:
        if resimulated.model in TWO_ARM_MODELS:
            return simulate(resimulated, n1=reference["n1"], n2=reference["n2"])
        return simulate(resimulated, n_total=reference["n_total"])
    except Exception as error:  # noqa: BLE001 - record failed simulation as an explicit failure
        # Deliberately blind: one scenario's simulator raising must not throw away the
        # other 27 cells, several of which cost minutes of Monte Carlo. The failure is
        # RECORDED in the cell rather than swallowed, so it still surfaces in the output.
        return {"error": str(error)}

def build_cell(path: Path, adapters: list) -> dict:
    return evaluate_scenario(load_scenario(path), adapters)


def evaluate_scenario(scenario, adapters: list | None = None) -> dict:
    if adapters is None:
        adapters = adapters_for(False)
    scenario.validate()
    reference = analytic_reference(scenario)
    declaration = reference_parameterization(scenario.model)

    simulation = simulate_for(scenario, reference, None)
    simulation_block = None
    if simulation and "error" not in simulation:
        simulation_block = {
            "power": simulation["power"],
            "mc_ci95": list(simulation["mc_ci95"]),
            "replications": SIMULATION_REPLICATIONS,
            "seed": SIMULATION_SEED,
        }

    tools = []
    for adapter in adapters:
        result = adapter.run(scenario)
        status = result.get("status", "error")
        tool_n = result.get("result", {}).get("n_total") if status == "ok" else None
        tolerance = getattr(adapter, "tolerance_for", lambda _method, default=0.02: default)(scenario.model)
        classification = classify_difference(
            reference["n_total"],
            tool_n,
            declaration,
            adapter.parameterization(scenario.model),
            tool_status=status,
            relative_tolerance=tolerance,
        )
        tools.append(
            {
                "tool_id": adapter.id,
                "tool_version": getattr(adapter, "version", "unknown"),
                "status": status,
                "reason": result.get("reason"),
                "n_total": tool_n,
                "delta_n_total": None if tool_n is None else tool_n - reference["n_total"],
                "package": result.get("package"),
                "package_version": result.get("package_version"),
                "method": result.get("result", {}).get("method") if status == "ok" else None,
                "parameterization": adapter.parameterization(scenario.model).to_dict(),
                "relative_tolerance": tolerance,
                **classification.to_dict(),
            }
        )

    return {
        "scenario_id": scenario.id,
        "method_id": scenario.model,
        "method_version": powerbench.method_version(scenario.model),
        "title": scenario.title,
        "target_power": scenario.target_power,
        "alpha": scenario.decision_rule.alpha,
        "alternative": scenario.decision_rule.alternative,
        "reference": {
            "n_total": reference["n_total"],
            "power": reference["power"],
            "method": reference.get("method"),
            "parameterization": declaration.to_dict(),
        },
        "simulation": simulation_block,
        "tools": tools,
        "adjudication": adjudicate(tools, reference, simulation_block),
        "case_study": CASE_STUDIES.get(scenario.model),
    }

def adjudicate(tools: list[dict], reference: dict, simulation: dict | None) -> dict:
    """Summarize a cell without ranking tools globally.

    A global leaderboard would misrepresent tools that are correct for a different
    estimand. Per scenario the arbiter is the independent simulation, which shares no code
    with any analytic reference; where tools disagree under *different* assumptions there
    is no most-accurate answer, only two different questions.
    """
    answered = [tool for tool in tools if tool["status"] == "ok"]
    if not answered:
        return {
            "verdict": "no_external_coverage",
            "summary": "No external tool returned a matched numeric result in this run. Inspect the recorded decline and failure reasons.",
        }

    disagreements = [tool for tool in answered if tool["category"] == "needs_review"]
    assumption_differences = [tool for tool in answered if tool["is_assumption_difference"]]
    agreements = [tool for tool in answered if tool["category"] in {"compatible", "rounding_display"}]

    if disagreements:
        supported_by_simulation = None
        if simulation:
            low, high = simulation["mc_ci95"]
            # The interval bounds come back as numpy scalars, so the comparison yields a
            # numpy bool that json.dumps refuses. Coerce here rather than at write time,
            # so the value is a plain bool everywhere downstream.
            supported_by_simulation = bool(low <= reference["power"] <= high)
        return {
            "verdict": "unresolved",
            "summary": (
                f"{len(disagreements)} tool(s) differ under matched assumptions. This is a "
                "signal to investigate, not a finding that either implementation is wrong."
            ),
            "simulation_supports_reference": supported_by_simulation,
        }
    if assumption_differences and not agreements:
        return {
            "verdict": "assumption_divergence",
            "summary": (
                "Every external tool that answered is powering a different estimand, so the "
                "sample sizes are not directly comparable."
            ),
        }
    return {
        "verdict": "agreement",
        "summary": (
            f"{len(agreements)} external tool(s) agree with PowerBench under matched "
            "assumptions."
        ),
    }

def comparable_cells(cells: list[dict], executed: set[str]) -> dict:
    """Reduce cells to the form `--check` compares, keyed by `scenario_id`.

    Compares the cells rather than the whole document: tool version strings and the
    generation environment legitimately vary between machines.

    Only adapters in `executed` are compared. With `--skip-slow` the Monte Carlo adapters
    do not run, so their results are legitimately absent from a fresh build; comparing
    them against a committed matrix that has them would report "stale" on every quick
    check. A drift detector that cries wolf gets ignored, which is worse than not having
    one.

    Ordering is canonicalised at BOTH levels, because a positional comparison at either
    one reports content drift that does not exist:

    - cells are keyed by `scenario_id` (a full run emitted them in filename order, a
      partial run in scenario_id order);
    - `tools` within a cell are sorted by `tool_id` (`adapters_for` appended
      `r.specialist` / `desktop.gpower` only when the registry did not already hold them,
      so their index depended on the call path, and `r.pwr` got diffed against
      `desktop.gpower`).

    The second fix came six commits after the first: the same defect existed one level
    down and survived, because the original fix only addressed the level where the symptom
    showed. See PM-021.

    Extracted from `main()` so tests can exercise the comparison without shelling out.
    Each subprocess `--check` rebuilds all 28 cells through R, so a test file with three
    of them added roughly 35 minutes to the suite.
    """
    trimmed = []
    for cell in cells:
        copy = dict(cell)
        copy["tools"] = sorted(
            (t for t in cell.get("tools", []) if t["tool_id"] in executed),
            key=lambda t: t["tool_id"],
        )
        # `adjudication` summarises every tool in the cell, so it is not comparable when
        # only a subset ran.
        copy.pop("adjudication", None)
        trimmed.append(copy)
    return {cell["scenario_id"]: cell for cell in jsonable(trimmed)}

def matrices_agree(committed: list[dict], fresh: list[dict], executed: set[str]) -> bool:
    """True when a committed matrix matches a fresh build, ignoring benign ordering."""
    return comparable_cells(committed, executed) == comparable_cells(fresh, executed)
