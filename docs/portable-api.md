# Portable scientific API (0.9.0 candidate)

This candidate is not yet a published release. Build it with `python -m pip wheel .`
and install that wheel into a clean environment. Production consumers must wait for
publication of `powerbench==0.9.0` and verify its artifact hash. No PowerMate account,
database, web server, or AI service is required.

```python
from powerbench.api import analyze
from powerbench.resources import example
from powerbench.capabilities import capabilities
from powerbench.reproducibility import export_bundle
from pathlib import Path

scenario = example("two_sample_t_balanced")
# This historical example explicitly specifies .80. New requests that omit power
# use .95; explicit historical values are preserved.
scenario["target_power"] = .95
result = analyze({"operation": "plan", "scenario": scenario})
print(result["result"])
Path("reproduction.zip").write_bytes(export_bundle(result))
```

For fixed-sample power set `operation="power"`, `scenario["goal"]="achieved_power"`
and `sample={"n1":100,"n2":100}`. For minimum detectable effect set
`operation="detectable_effect"`, `scenario["goal"]="sensitivity"`, and retain the
explicit fixed sample and target power. One-group designs use `sample={"n_total":300}`;
paired designs count pairs. Sensitivity removes the solved effect from canonical
inputs and returns the selected direction, bracket/search diagnostics, and achieved
power. Unreachable and unsupported results are distinct from complete results.

`capabilities()` enumerates supported goals per method. Eight methods have matched
independent base-R scripts: pooled/Welch/paired t, correlation, one-way ANOVA, overall
and incremental regression, and moderation. Representative examples for three goals
passed pinned WebR 0.6.0 in Chromium, Firefox and WebKit. This is not validation of all
possible parameter combinations, browser versions, or scientific designs. Other
methods retain Python reproduction with explicit fixed-sample limitations.

`analyze` also accepts `compare` (left/right planner fields), `convert_effect`, and
`simulate` operations. `powerbench.planning.analyze_fields` is the compatibility
wizard contract; `make_plan` additionally computes simulation and assumption sweeps.
`powerbench.validation.evaluate_scenario` and `adapters_for` expose external-tool
comparisons and adjudication without the website. R packages are optional; absence,
unsupported parameterizations and runtime failures are reported explicitly.

`python -m powerbench analyze request.json --output result.json` and
`python -m powerbench capabilities` are equivalent CLI entry points. The installed
`powerbench` command accepts the same arguments. Inputs/results are JSON-compatible;
nonfinite numbers and contradictory goals are rejected. Record `schema_version`,
engine version, method version and the canonical input hash with any archived result.

`powerbench.review.review` checks a user-confirmed request against a reported value
at declared reporting precision. It does not infer missing alpha, sidedness, power,
allocation or study timing from prose. `powerbench.review.extraction_prompt` and
`validate_extraction` expose the same prompts and quote-grounding parser used by the
prototype extraction arena. Unconfirmed model proposals are not calculation inputs.
The four power-review arenas are provisional synthetic instruments; no provider has
been qualified for production scientific review, rewriting or code auditing.

Bundles contain executable Python, matched R where supported, request/result,
provenance, dependency versions, paragraph draft, references and a SHA256 manifest.
An account-free consumer can inspect and execute every file. Exact Python execution
requires the pinned package and dependency versions; R scripts are independent matched
checks. Base R needs no CRAN dependency lock. Record `sessionInfo()` with local R runs.
Generated paragraphs remain drafts requiring an effect rationale and confirmation of
study timing, sampling units, analysis model, missingness and multiplicity.

Simulation replay freezes all defaults, including seed, rejects nonfinite/fractional
counts and oversized requests, and exposes invalid sensitivity-grid points without
clipping. Simulation policy 1.1 leaves ordinary accepted main-scenario computations
unchanged; boundary-grid behavior and invalid-input handling changed. These exemplars
are conditional model demonstrations, not universal mixed-model or SEM calculators.
