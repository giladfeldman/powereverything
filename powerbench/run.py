from __future__ import annotations

import argparse
from pathlib import Path

from .references import analytic_reference
from .registry import automated_adapters
from .report import write_artifacts
from .schema import load_scenario
from .simulation import simulate


def run(path: str | Path, output: str | Path) -> dict:
    scenario = load_scenario(path)
    reference = analytic_reference(scenario)
    simulation = simulate(scenario, n1=reference.get("n1"), n2=reference.get("n2"), n_total=reference.get("n_total"))
    adapter_results = []
    for adapter in automated_adapters():
        item = adapter.run(scenario)
        item.setdefault("adapter", adapter.id)
        adapter_results.append(item)
    payload = {"scenario": scenario.to_dict(), "analytic_reference": reference, "simulation": simulation, "adapter_results": adapter_results}
    write_artifacts(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a PowerBench scenario")
    parser.add_argument("scenario")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = run(args.scenario, args.output)
    print(f"{payload['scenario']['id']}: reference total N = {payload['analytic_reference']['n_total']}")


if __name__ == "__main__":
    main()

