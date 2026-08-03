# Poisson rate-ratio: Wald normal approximation is mildly conservative

Status: **documented conservative approximation — within gate tolerance, checked strictly**
Applies to: `poisson_regression`
Last reviewed: 2026-08-03

## The observation

For `poisson_rr15_rate02` the analytic reference reports 0.8001 power at N = 796 while the
independent simulation measures marginally more. Measured at the alignment gate's own
settings (12,000 replications on each of three fixed seeds), the gaps are −0.0065, −0.0050
and −0.0094: the reference sits below the simulation by well under one point, and the
scenario aligns on all three seeds.

The scenario is therefore **not** allowlisted — it is checked strictly. This document
records the direction and cause of a known small bias, not an exemption. An earlier draft
allowlisted it on a 2,000-replication reading, which overstated the effect.

## Why this is expected

The reference uses the Wald normal approximation for the log rate ratio with

    Var(log RR) = 1 / E_0 + 1 / E_1

where `E_j` are the expected event counts in each arm. This treats the log-rate estimate as
exactly normal with a known variance evaluated at the true parameter.

The simulation fits the actual Poisson model, and its likelihood-based test is slightly more
efficient than the Wald approximation at finite counts — a well-documented property: the
Wald statistic is the least powerful of the three classical tests (Wald, score, likelihood
ratio) in this setting, because its variance is evaluated at the estimate rather than under
the null.

The consequence is that the analytic reference recommends a marginally larger sample than
strictly required. That is the safe direction for a planning tool.

## Cross-tool context

R `pwrss.z.poisson` returns N = 787 for the same design against PowerBench's 796 — about a
1% difference, consistent with small variations in how each tool handles the variance term.
This is an agreement, not a disagreement: no tool in this family claims exactness.

## What would make this a defect

- The reference sitting *above* the simulation, which would mean under-powering.
- The gap failing to shrink as expected event counts grow — the normal approximation must
  improve as counts increase.
- Divergence appearing at large counts, where Wald, score, and likelihood-ratio tests
  should all coincide.

## Consequence for the coverage matrix

`Poisson / count regression rate ratio` carries `verified_with_approximation` and passes
the strict alignment gate. This document records the direction of the residual bias so a
future sign change is recognisable as a regression rather than accepted as noise.
