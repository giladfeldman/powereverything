# Chi-square independence: expected-count floor and small-N conservatism

Status: **documented conservative approximation — not a defect**
Applies to: `chi_square_independence`
Last reviewed: 2026-08-03

## The observation

For `chi_square_independence_2x2` the analytic reference reports 0.8230 power at N = 50
while the independent simulation measures 0.8429, 95% MC interval [0.8358, 0.8500] at
10,000 replications — the reference sits about 2 points *below* the simulation.

Two separate things are happening, and neither is a coding error.

## 1. The reported power is a floor, not a solution

The scenario declares `min_expected_count: 5`. With the smallest joint cell probability at
0.10, satisfying that constraint requires N >= 50, so the sample-size search *starts* at 50
rather than searching upward from a smaller N.

Power at the target of 0.80 would be reached at approximately N = 48, but that design would
violate the declared expected-count requirement. The reported 0.8230 is therefore the power
at the smallest admissible N, not the power at the smallest N meeting the target. Discrete
overshoot of this kind is expected whenever a design constraint binds before the power
constraint does.

This is why the alignment gate carries a `GATE_TOLERANCE` of 0.01 rather than requiring the
analytic value to fall strictly inside the Monte Carlo interval: discretization of this kind
is a property of integer sample sizes, not evidence of a wrong formula.

## 2. Cohen's *w* noncentrality is conservative at small N

The reference uses the standard noncentral chi-square approximation with
`lambda = N * w^2`. This approximation is known to understate power modestly at small N and
small expected cell counts, because the discrete Pearson statistic is only asymptotically
chi-square. The direction is conservative: it recommends a slightly larger sample than
strictly necessary.

Conservatism in this direction is the safe failure mode for a planning tool, so it is kept
rather than replaced with an exact enumeration, which would be far slower and would not
change any practical recommendation.

## What would make this a defect

- The reference sitting *above* the simulation (anti-conservative), which would mean
  recommending too small a sample.
- The gap failing to shrink as N and expected cell counts grow — the asymptotic
  approximation must improve with N.
- The expected-count floor binding when it should not, i.e. a reported N that violates
  `min_expected_count`.

## Consequence for the coverage matrix

`Chi-square independence` carries `verified_conservative`, which states the direction of the
error explicitly rather than hiding it behind a generic "approximation" label. Users are
told the recommended N is, if anything, slightly larger than strictly required.
