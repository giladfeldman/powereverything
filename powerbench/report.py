from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path


def write_artifacts(output_dir: str | Path, payload: dict) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = datetime.now(UTC).isoformat()
    (output / "result.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    ref, sim = payload["analytic_reference"], payload["simulation"]
    rows = []
    for adapter in payload["adapter_results"]:
        if adapter.get("status") == "ok":
            result = adapter["result"]
            delta = result.get("n_total", 0) - ref.get("n_total", 0)
            classification = "compatible" if delta == 0 else "assumption_or_implementation_review"
            rows.append(f"| {adapter['adapter']} | {adapter.get('package_version', 'unknown')} | {result.get('n_total', 'n/a')} | {delta:+} | {classification} |")
        else:
            rows.append(f"| {adapter.get('adapter', 'unknown')} | - | - | - | {adapter['status']}: {adapter.get('reason', '')} |")
    markdown = f"""# PowerBench result: {payload['scenario']['id']}

## Canonical scenario

- Model: `{payload['scenario']['model']}`
- Goal: `{payload['scenario']['goal']}`
- Decision rule: alpha = {payload['scenario']['decision_rule']['alpha']}, alternative = `{payload['scenario']['decision_rule']['alternative']}`
- Analytic reference method: `{ref['method']}`
- Reference required total N: **{ref['n_total']}** (estimated power: {ref['power']:.4f})

## Independent simulation

- Empirical power: **{sim['power']:.4f}**
- Monte Carlo SE: {sim['mc_standard_error']:.4f}; 95% Monte Carlo interval: [{sim['mc_ci95'][0]:.4f}, {sim['mc_ci95'][1]:.4f}]
- Replications: {sim['replications_completed']} completed; failures: {sim['failures']}; seed: {sim['seed']}

## Adapter comparison

| Adapter | Package version | Required total N | Delta from reference | Status |
| --- | --- | ---: | ---: | --- |
{chr(10).join(rows)}

This report compares matched scenarios only. A difference is a review signal, not evidence of an error, until its assumptions and parameterization have been examined.
"""
    (output / "report.md").write_text(markdown, encoding="utf-8")

