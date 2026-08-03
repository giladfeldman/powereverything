# Fixed-design reference vs random-predictor simulation (regression family)

Status: **documented assumption difference — within tolerance for most of the family**
Applies to: `linear_regression`, `moderation`, `incremental_regression`
Related: [`incremental_regression.md`](incremental_regression.md)
Last reviewed: 2026-08-03

## The observation

The analytic reference sits slightly above the independent simulation across the
regression family. Measured at the alignment gate's own settings — 12,000 replications on
each of three fixed seeds — the gaps are:

| Scenario | N | Gap (reference − simulation), 3 seeds | Aligned |
|---|---|---|---|
| `linear_regression_f2_015_p3` | 77 | +0.0163, +0.0142, +0.0172 | 3 of 3 |
| `moderation_interaction_f2_020` | 397 | +0.0038, +0.0117, +0.0115 | 3 of 3 |
| `incremental_regression_f2_015` | 58 | +0.0135, +0.0188, +0.0252 | 1 of 3 |

Only `incremental_regression` exceeds the gate's 0.01 tolerance often enough to need a
documented exemption. The other two are checked strictly.

This measurement matters: an earlier draft of this document allowlisted all three on the
strength of 2,000-replication readings, where the apparent divergence was largely Monte
Carlo noise. A divergence claim has to be earned at the replication count the gate
actually uses (see PM-012 in project lessons).

## Why the gap exists and is not a bug

The two sides answer different questions, and both answer their own question correctly.

The **analytic reference** uses the noncentral *F* distribution with noncentrality
`lambda = n * f^2`. That is the *fixed-design* result: it conditions on the predictor
matrix `X`, treating it as fixed and known. This is the convention used by `pwr.f2.test`,
by G*Power's "Linear multiple regression: Fixed model", and by essentially every
closed-form regression power formula in the literature.

The **simulation** draws a fresh random `X` on every replication. Averaging power over the
sampling distribution of `X` is a different estimand: because power is concave in the
realized predictor variance across the relevant region, averaging over random `X` yields
slightly lower mean power than evaluating at the expected `X`. The gap is therefore
expected to be positive and small, which is what is observed.

Neither number is wrong. A researcher conditioning on their realized design matrix (the
usual situation once data are collected) wants the fixed-design number; a researcher
asking "across repeated studies with newly sampled predictors, how often will I detect
this?" wants the random-`X` number.

The gap is largest for `incremental_regression` because it has the smallest N (58) — the
random-`X` effect shrinks as N grows, so this is the member of the family where it is
still visible above Monte Carlo noise.

## How the exemption is bounded

`incremental_regression_f2_015` is registered as a `DocumentedDivergence` in
`tests/test_reference_simulation_alignment.py` with an explicit envelope rather than by
widening the gate tolerance. The envelope pins:

- `expected_direction = "reference_above"` — a sign flip fails the gate, since that would
  indicate something other than the random-`X` effect.
- `max_abs_gap = 0.05` — a documented ~2 point gap growing to 20 points still fails.

The scenario is still tested on every gate run; it is not exempt.

## What would make this a defect

- The gap changing sign (simulation above reference).
- The gap growing with N. The random-`X` effect shrinks as N grows; a gap that widens
  instead indicates a real formula error.
- `linear_regression` or `moderation` starting to fail the strict gate, which would mean
  something changed beyond the known estimand difference.

## Consequence for the coverage matrix

`Overall linear regression` carries `verified_with_design_limits` and
`Moderation / interaction increment` carries `verified_with_approximation`: both pass the
strict gate. `Incremental regression block` remains `requires_assumption_review`, which is
enforced — `tests/test_coverage_matrix_evidence.py` refuses any `verified_*` status for a
method that is allowlisted in the gate.
