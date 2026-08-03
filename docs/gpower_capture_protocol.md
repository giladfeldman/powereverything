# Capturing a G*Power comparison

G*Power is the tool most psychology and social-science researchers actually use, which
makes it the most valuable external comparison this project can carry. It is also a desktop
GUI with no scriptable interface, so it is the one comparison that can never be automated.

This is the protocol for recording one by hand in a way that stays trustworthy.

## What a capture is, and is not

A capture is a **record of a run someone actually performed**. It is not a prediction of
what G*Power would say. Never write a capture from a formula, from memory, or from what the
number "should" be — a fabricated capture is worse than no capture, because it manufactures
corroboration where none exists.

If you cannot run G*Power, leave the comparison absent. `data/tool_catalog.csv` already
records G*Power as `manual`, and the cross-check page shows methods with no external
coverage honestly rather than pretending.

## Steps

1. **Pick a committed scenario** from `data/scenarios/`. Captures are tied to those, not to
   ad-hoc inputs, so that the comparison is reproducible.

2. **Compute the scenario hash** you are capturing against:

   ```bash
   python -c "from powerbench.schema import load_scenario; from powerbench.adapters.manual_gpower import scenario_hash; print(scenario_hash(load_scenario('data/scenarios/two_sample_t_balanced.json')))"
   ```

   Record it. If the scenario is later edited, this is what makes the capture flag itself as
   stale instead of silently comparing against a design that no longer exists.

3. **Run G*Power.** Choose the test family and statistical test that match the scenario's
   declared estimand — not the one with a similar name. Check
   `powerbench/reference_parameterization.py` for what PowerMate is powering. If G*Power has
   no matching option, stop: that is an honest `unsupported`, and forcing the nearest
   option produces a comparison between different questions.

4. **Screenshot the whole G*Power window**, including the input panel. A screenshot of only
   the output is not verifiable — the inputs are the part that can be wrong. Save it under
   `docs/tool_dossiers/assets/`.

5. **Write the capture JSON** into `data/gpower_captures/<scenario_id>.json` using the
   template below. Transcribe the inputs exactly as typed and the outputs exactly as shown,
   including G*Power's own rounding.

6. **Sign it:**

   ```bash
   python scripts/sign_gpower_capture.py data/gpower_captures/<scenario_id>.json
   ```

   The signature is tamper-*evidence*, not authentication: anyone with the repository can
   recompute it. Its job is to make a later silent edit visible — a screenshot swapped
   without updating the numbers, or a number adjusted after the fact.

7. **Commit the JSON and the screenshot together**, then regenerate the matrix:

   ```bash
   python scripts/refresh_validation_matrix.py --only <method_id>
   ```

## Template

```json
{
  "scenario_id": "two-sample-t-balanced-d-0.40",
  "method_id": "two_sample_t",
  "tool_version": "3.1.9.7",
  "operating_system": "Windows 11",
  "captured_on": "2026-08-03",
  "captured_by": "0000-0000-0000-0000",
  "gui_test_family": "t tests — Means: Difference between two independent means (two groups)",
  "gui_inputs": {
    "type_of_power_analysis": "A priori: Compute required sample size",
    "tails": "Two",
    "effect_size_d": 0.4,
    "alpha_err_prob": 0.05,
    "power": 0.8,
    "allocation_ratio_n2_n1": 1
  },
  "gui_outputs": {
    "noncentrality_parameter_delta": 2.8284271,
    "critical_t": 1.9720175,
    "df": 198,
    "sample_size_group_1": 100,
    "sample_size_group_2": 100,
    "total_sample_size": 200,
    "actual_power": 0.8036475
  },
  "parameterization": {
    "effect_definition": "Cohen's d, difference in means over the pooled SD",
    "test_variant": "exact noncentral t, pooled variance",
    "df_convention": "n1 + n2 - 2",
    "rounding_rule": "ceiling to the smallest integer meeting target power",
    "allocation_support": "any ratio",
    "tails_support": "two.sided|greater|less"
  },
  "assumptions": [
    "Balanced allocation",
    "Equal variances",
    "Exact noncentral t distribution"
  ],
  "screenshots": ["docs/tool_dossiers/assets/two_sample_t_gpower.png"],
  "scenario_hash_at_capture": "…",
  "signature": "…"
}
```

`captured_by` should be an ORCID iD where the capturer has one. It is a claim about
provenance, so it should identify a person rather than a machine.

## When a capture goes stale

If `scenario_hash_at_capture` no longer matches, the adapter reports `unavailable` with
`stale_capture: true` and the cross-check page shows no G*Power number for that method.
That is intended. Re-run G*Power against the current scenario and replace the capture; do
not edit the hash to make the warning go away.

## Why not just trust the numbers in the dossier

`docs/tool_dossiers/gpower_two_sample_t.md` has carried "PowerBench matched N = 200" since
July with `Screenshot paths: TBD`. That claim was never backed by a run, and the dossier
says so at line 77 — "treat external GUI agreement as unverified for release claims". This
protocol exists to convert that placeholder into evidence, or to leave it honestly empty.
