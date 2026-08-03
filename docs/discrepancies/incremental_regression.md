# Discrepancy case study: incremental regression

## What disagrees

The canonical `incremental_regression` scenario uses a fixed-design noncentral-F
reference for a pre-specified final predictor block. Its independent simulation
generates random, independent normal predictors and errors before fitting reduced
and full OLS models. These are not automatically the same design condition, even
when they share the label "incremental f-squared".

## Why PowerBench keeps the warning visible

The reference's noncentrality follows the fixed-design convention used by
`pwr.f2.test`; the simulation's realized predictor matrix changes across replications.
Correlated covariates, measurement reliability, interactions, or a different
predictor distribution alter the mapping between a population effect and a tested
block. Numerical disagreement is therefore an assumption-review signal, not evidence
that either implementation is defective.

## User-facing rule

PowerBench reports `requires_assumption_review` for this path. It must not be raised
to verified until the scenario explicitly selects fixed versus random predictors,
defines their covariance and coefficients, and demonstrates reference/simulation
alignment for that selected estimand. For a focal coefficient or interaction, use a
simulation-first scenario instead of repurposing an omnibus or block formula.
