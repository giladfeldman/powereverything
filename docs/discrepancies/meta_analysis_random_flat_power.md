# Random-effects meta-analysis: a flat power curve makes N nearly unidentified

Status: **explained — Monte Carlo resolution on a plateau, not a defect in either tool**
Applies to: `meta_analysis_random`
Tools: PowerBench reference vs `metafor::rma(test = "knha")` Monte Carlo
Last reviewed: 2026-08-03

## The observation

For k = 6 studies, tau = 0.2, d = 0.3 at 80% target power:

| Source | Total N | Per group per study |
|---|---|---|
| PowerBench reference | 6,504 | 542 |
| `metafor` Monte Carlo bisection | 5,088 | 424 |

A 22% difference, which the cross-tool classifier flagged `needs_review` because no
declared assumption difference explains it. That flag was correct: the tools *do* declare
the same estimand, the same Hartung-Knapp adjustment and the same `k - 1` degrees of
freedom. The explanation is not in the assumptions — it is in the shape of the problem.

## Why the two numbers are both defensible

Between-study heterogeneity puts a ceiling on what more participants can buy. As
per-study N grows, the summary standard error approaches `tau / sqrt(k)`, so power
asymptotes rather than approaching 1:

| Per group per study | Total N | Analytic power |
|---|---|---|
| 100 | 1,200 | 0.671 |
| 300 | 3,600 | 0.774 |
| **424** | **5,088** | **0.791** |
| **542** | **6,504** | **0.800** |
| 800 | 9,600 | 0.810 |
| 2,000 | 24,000 | 0.824 |
| 100,000 | 1,200,000 | 0.832 |

Between the two candidate answers, a **28% increase in total sample size buys 0.9
percentage points of power**. The curve is nearly flat there, so the sample size is only
weakly identified by the target power: small differences in how power is estimated move N
a great deal.

The `metafor` adapter estimates power by simulation over 400 replications, giving a Monte
Carlo standard error of roughly 0.02 near p = 0.8 — larger than the entire 0.009 power
difference between the two answers. Its bisection therefore stops wherever noise first
carries an estimate above the target, which on a plateau can be far from where the analytic
curve crosses.

PowerBench's own simulator, run at both candidates, is consistent with this reading:
0.783 [0.769, 0.798] at N = 5,088 and 0.790 [0.775, 0.804] at N = 6,504. Both intervals
straddle or sit below 0.80, and they overlap each other — the data cannot cleanly separate
the two sample sizes either.

## What this means for a user

**The sample size is the wrong lever for this design.** Adding participants to existing
studies cannot overcome heterogeneity; only more studies can, because the floor is
`tau / sqrt(k)`. A planner who sees 6,504 and interprets it as "collect this and you will
have 80% power" has been given a technically correct answer to a question that is close to
degenerate.

The planner already surfaces this: `_heterogeneity_curve` shows how the required N moves
with tau, and `required_n_meta_analysis_random` raises an explicit error when the target is
unreachable at any finite N. The gap documented here is the milder version of the same
phenomenon — reachable, but only just.

## What would make this a defect

- The two tools disagreeing where the power curve is *steep* (small tau, or few studies
  relative to the effect), where N is well identified.
- The analytic asymptote disagreeing with the simulated asymptote. Both give 0.832 here.
- PowerBench falling *below* the target at its own recommended N by more than Monte Carlo
  error.

## Resolution

Recorded as an explained `needs_review`, not promoted to `probable_defect`. Neither
implementation is wrong; the design is one where the reported sample size carries much less
information than usual, and that is what the user needs to be told.
