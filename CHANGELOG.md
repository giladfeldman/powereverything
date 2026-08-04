# Changelog

All notable changes to PowerBench are recorded here. Entries that change a computed number
state the **numeric impact**, because a user planning a study needs to know what moved and
by how much, not merely that something improved.

Method-level versions (`powerbench.METHOD_VERSIONS`) are bumped independently of the package
version and only when a method's answers change. See
[`powerbench/versioning.py`](powerbench/versioning.py).

---

## 0.8.1 — 2026-08-04

**No computed answer changes.** No method version is bumped: `references.py`,
`specialist_extras.py` and `simulation.py` are untouched. This release widens external
comparison coverage only.

### Cross-tool coverage: 12 → 15 of 28 scenarios

The R `pwr` adapter now also answers one-sample proportion, two-sample proportion, and
chi-square test of independence. No new R package is required — these use `pwr.p.test`,
`pwr.2p.test`, and `pwr.chisq.test` with `ES.h` / `ES.w2`.

Two of the three disagree with PowerBench, and both gaps are declared in the adapter's
`parameterization()` so they are attributed rather than reported as bare numbers:

- **One-sample proportion** (p₀=.30, p₁=.50, power=.80): `pwr` 47, PowerBench 43. `pwr.p.test`
  is a normal approximation on Cohen's arcsine scale; PowerBench uses an exact binomial
  rejection region. Verified independently in R — exact binomial power at n=43 is 0.819812,
  so 43 is correct and the gap is the approximation's cost. Exact tests are also
  non-monotonic in n here (n=43 beats n=44 and n=46), which no normal approximation
  reproduces.
- **Chi-square independence** (2×2, joint cell probabilities): `pwr` 48, PowerBench 50.
  `pwr.chisq.test` enforces no minimum expected cell count; PowerBench applies the
  scenario's `min_expected_count` of 5, and that floor is binding. Not a disagreement about
  the noncentral chi-square.
- **Two-sample proportion** (p₁=.30, p₂=.50): both return n_total=186.

The adapter declines unbalanced two-sample proportion designs rather than reporting a
balanced answer for one, since `pwr.2p.test` is balanced-only.

### Fixed

- `scripts/refresh_validation_matrix.py`: tool order within a matrix cell is now canonical,
  and `--check` compares tools by `tool_id` instead of by position. `adapters_for()`
  appended `r.specialist` / `desktop.gpower` only when the registry did not already contain
  them, so their position varied by call path; a positional comparison then diffed `r.pwr`
  against `desktop.gpower` and reported the committed matrix stale when it was correct.
  This is the same defect class as the 0.8.0 cell-order fix, one level down. Regression test
  in `tests/test_validation_matrix_ordering.py` asserts both directions — reordering must
  not read as drift, and a one-unit change to an external `n_total` must still fail.

## 0.8.0 — 2026-08-03

First public release.

### Cross-tool validation

Every method now declares what it computes — effect definition, predictor distribution,
test variant, degrees-of-freedom convention, allocation, tails — and external comparisons
are attributed against those declarations rather than reported as bare number gaps.

- `powerbench/parameterization.py`: the declaration vocabulary and a ten-category
  classification taxonomy. Declarations are compared **before** the numbers, so two tools
  answering different questions cannot launder a coincidental agreement into "compatible".
- `probable_defect` is never assigned automatically. An unexplained gap becomes
  `needs_review`, because asserting a named third-party tool is wrong is a claim a person
  should make after looking.
- Adapters: R `pwr` (7 designs), `pwrss` (logistic, Poisson), and a specialist adapter
  covering `TOSTER`, `metafor::rma(test = "knha")` and `MASS::polr`. Monte Carlo adapters
  declare their own search resolution and are compared against that rather than a
  closed-form tolerance.
- `powerbench/adapters/manual_gpower.py` reads human-recorded G*Power captures and never
  executes anything. Captures are signed (tamper-evidence, not authentication) and bound to
  the scenario hash they were taken against, so an edited or stale record is refused rather
  than reported. Protocol: [`docs/gpower_capture_protocol.md`](docs/gpower_capture_protocol.md).

Twelve of 28 scenarios now have external coverage. Nine agree exactly; Poisson agrees
within 1.1%; ordinal within 1.6% of `MASS::polr`; TOST is exact against `TOSTER`.

### Per-method versioning

`powerbench.METHOD_VERSIONS` gives each method its own version, bumped only when its
computed answers change, with `changes_since(method_id, version)` reporting what moved and
by how much. Downstream consumers should bind to `(method_id, method_version)` so that a
correction to one method does not invalidate work depending on another.

---

## 0.7.0 — 2026-08-03

**Six analytic formulas were producing wrong sample sizes.** All are corrected, each
confirmed against an independent R implementation. The engine had not been distributed, so
no published study plan is affected.

The defects were invisible because the test suite could not falsify a formula: every
sample-size function is a `while power < target: n += 1` search, so
`assert power >= target_power` is a tautology that holds regardless of whether the
mathematics is right. The full suite passed with all six present.

### Corrected

| Method | Was | Now | Confirmed by |
|---|---|---|---|
| `ordinal_regression` | N = 191 | **N = 614** | `MASS::polr` measured 0.34 power at 191 |
| `logistic_regression` | N = 910 | **N = 856** | `pwrss` returns 856; `glm` MC gives 0.805 |
| `meta_analysis_random` | hybrid t/normal | proper Hartung–Knapp | `metafor(test = "knha")` |
| `mediation_indirect` | 0.8024 | 0.7909 | MC truth 0.7877 |
| `group_sequential_t` | fixed-design power | true sequential power | α spent = 0.05000 exactly |
| `planned_contrast` | weights ignored | contract documented | weights provably cancel |

Detail on each:

- **Ordinal regression** used a flat `Var(beta) = 4/n`, independent of the declared number
  of categories — the schema validated `categories` and the formula then discarded it, so
  k = 3, 4, 5 and 6 all returned the same answer. Replaced with Whitehead (1993)
  proportional odds. **Required N moves from 191 to 614**; the previous sample delivered
  about a third of the promised power. The simulator was also wrong (it collapsed the
  outcome to binary and fitted a logistic model) and now fits a real proportional-odds
  model agreeing with `MASS::polr` to about 1e-5.
- **Logistic regression** evaluated the Fisher information only at the baseline
  probability, ignoring that the exposed arm sits at `expit(logit(p0) + beta)`. Now the
  Demidenko (2007) form. The old error changed sign near p₀ = 0.5, so some plans were
  under-powered rather than merely wasteful.
- **Random-effects meta-analysis** combined three errors that partially offset: `df = k−2`
  instead of `k−1`, no Hartung–Knapp variance rescaling, and a t critical value evaluated
  against a normal rejection probability. Fixing one alone made the answer worse.
- **Mediation** used the Fisher-z standard error for a *correlation* on both paths. Now the
  OLS regression-coefficient standard errors on residual degrees of freedom.
- **Group-sequential** reported the fixed-design power at an inflated N — not the operating
  characteristic of a sequential design — using a hardcoded five-entry inflation table
  insensitive to α, target power and alternative. Now Lan–DeMets O'Brien–Fleming spending
  with boundaries solved so cumulative type I error equals α exactly. The simulator's
  separate `z_crit/√t` boundary was also invalid, spending 0.05216 against a nominal 0.05.
  Designs beyond five looks now work.
- **Planned contrast** validated `contrast_weights` and never used them. Investigation
  showed the weights *cannot* affect power once `cohens_f` is declared as the contrast's own
  standardized effect — they cancel algebraically — so the contract is documented rather
  than a dependency faked. No previously returned sample size changes.

TOST needed no formula change; it matches `TOSTER::power_t_TOST` to four decimal places.
Dead code was removed. The log-rank accrual/censoring calculator, previously present with
zero call sites, is now wired in so `p_event` is derived from the declared follow-up plan.

### Regression proofing

- `tests/test_reference_simulation_alignment.py`: every scenario checked against the
  independent simulator across three fixed seeds at 12,000 replications, majority verdict.
  At the shipped 2,000 replications, agreement is a seed lottery.
- Documented divergences are structured entries carrying a direction and a maximum gap, and
  are still tested against that envelope. `test_allowlist_has_no_stale_entries` forces an
  entry out once the divergence resolves, so nothing gets permanent amnesty.
- Every external fixture in `data/benchmarks/` ships with the script that generated it, so
  a reviewer can re-derive each committed number rather than trusting a prose `source`
  field.
