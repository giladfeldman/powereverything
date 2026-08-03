# PowerBench

**Statistical power analysis that shows its work.**

PowerBench computes required sample sizes for 27 study designs. What distinguishes it is
not the calculations — those are standard — but that every number is checked three ways and
the checks are published:

1. an **analytic reference** implementing a named published formula,
2. an **independent Monte Carlo simulation** that shares no code with the reference,
3. **external tools** (R `pwr`, `pwrss`, `metafor`, `TOSTER`, `MASS`) where they can
   represent the same design.

When those disagree, PowerBench says so and explains why, rather than presenting one
confident number.

This package is the calculation engine behind [PowerMate](https://powerrmate.vercel.app).
It is published separately so the mathematics can be audited, cited, and reported against
without running the web application.

---

## Why this exists

On 2026-08-03 an audit of this engine found **six analytic formulas producing wrong sample
sizes**. The worst recommended **191 participants for a design needing about 614** — a study
designed at roughly a third of the power its authors would believe it had. `MASS::polr`
measured 0.34 power where the tool promised 0.80.

Every one of those defects passed the entire test suite.

The reason is worth stating plainly, because it generalises to any power tool: each
sample-size function is a search loop of the form

```python
while power(n) < target:
    n += 1
```

so `assert power >= target_power` is **a tautology**. It holds no matter how wrong
`power()` is. A test suite built on that assertion cannot fail.

What can falsify a formula is an independent implementation of the same design. That is
what the simulation layer and the external adapters are for, and why their agreement is
tested rather than merely displayed.

All six defects are fixed, each confirmed against an independent R implementation. See
[`CHANGELOG.md`](CHANGELOG.md).

---

## Install

```bash
pip install powerbench
```

Requires Python 3.11+. Runtime dependencies are SciPy and NumPy. R is optional and needed
only to regenerate external-tool comparisons.

---

## Quick start

```python
from powerbench.schema import Scenario, DecisionRule
from powerbench.references import analytic_reference
from powerbench.simulation import simulate

scenario = Scenario(
    id="my-study",
    title="Two independent groups, d = 0.4",
    framework="frequentist",
    goal="required_sample_size",
    model="two_sample_t",
    target_power=0.80,
    effect={"cohens_d": 0.4},
    design={},
    decision_rule=DecisionRule(alpha=0.05, alternative="two.sided"),
    simulation={"replications": 5000, "seed": 20260803},
    assumptions=["Independent observations", "Equal variances"],
)
scenario.validate()

reference = analytic_reference(scenario)
print(reference["n_total"], reference["method"])
# 200 noncentral_t

check = simulate(scenario, n1=reference["n1"], n2=reference["n2"])
print(check["power"], check["mc_ci95"])
# 0.8092 (0.7983, 0.8201)   <- independent confirmation, not the same code path
```

The second call is the point. If the analytic answer falls outside the simulation's Monte
Carlo interval, one of them is wrong, and you have learned something the single number
would never have told you.

---

## What it covers

27 designs, each with a declared estimand:

| Family | Designs |
|---|---|
| **t tests** | pooled two-sample, Welch unequal-variance, paired |
| **Proportions** | one-sample (exact binomial), two-sample |
| **Chi-square** | goodness-of-fit, independence |
| **ANOVA** | one-way, factorial, ANCOVA, planned contrast |
| **Regression** | overall, incremental block, moderation, logistic, Poisson, ordinal |
| **Association** | Pearson correlation |
| **Mediation** | indirect effect via joint significance |
| **Equivalence** | TOST, non-inferiority, Bayesian ROPE |
| **Meta-analysis** | fixed-effect, random-effects (Hartung–Knapp) |
| **Sequential** | group-sequential t with Lan–DeMets O'Brien–Fleming boundaries |
| **Survival** | two-arm log-rank (Schoenfeld) |
| **Bayesian** | JZS Bayes-factor design analysis |

Coverage is not the same as verification. See
[Verification status](#verification-status) below for which designs have been checked
against what.

---

## Verification status

### The alignment gate

`tests/test_reference_simulation_alignment.py` runs every committed scenario through both
the analytic reference and the independent simulator, across **three fixed seeds at 12,000
replications**, and requires agreement on a majority.

```bash
pytest -m slow tests/test_reference_simulation_alignment.py
```

Latest full run: **29 passed, 0 failed**.

Multiple seeds are not decoration. At the 2,000 replications the scenarios ship with,
agreement is a seed lottery: one method read as broken on one seed and agreed comfortably
at 12,000, while another looked fine at 2,000 and was genuinely wrong.

Two scenarios carry documented divergences with written case studies in
[`docs/discrepancies/`](docs/discrepancies/). They are still tested — against a declared
envelope with an expected direction and a maximum gap — so a sign flip or a widening gap
still fails. An entry that stops being needed is forced out by
`test_allowlist_has_no_stale_entries`, so nothing gets permanent amnesty.

### External tools

12 of 28 scenarios have been checked against an external implementation:

| Design | PowerBench | External | Tool |
|---|---|---|---|
| Two-sample t | 200 | 200 | R `pwr` |
| Paired t | 52 | 52 | R `pwr` |
| Chi-square GOF | 181 | 181 | R `pwr` |
| One-way ANOVA | 159 | 159 | R `pwr` |
| Linear regression | 77 | 77 | R `pwr` |
| Incremental regression | 58 | 58 | R `pwr` |
| Correlation | 194 | 194 | R `pwr` |
| Logistic regression | 856 | 856 | R `pwrss` |
| Poisson regression | 796 | 787 | R `pwrss` |
| TOST equivalence | 140 | 140 | `TOSTER` |
| Ordinal regression | 614 | 624 | `MASS::polr` |
| Random-effects meta | 6,504 | 5,088 | `metafor` — [investigated](docs/discrepancies/meta_analysis_random_flat_power.md) |

The remaining 16 have no external coverage, and the tooling reports that honestly rather
than implying agreement.

### Disagreements are attributed, not scored

A comparison that only compares numbers cannot distinguish *"these tools disagree"* from
*"these tools are answering different questions"*.

Concretely: `pwrss.z.logreg` returns **N = 249** where PowerBench returns **856** for what
looks like the same logistic design — a 3.4× gap that reads as catastrophic. It is not a
defect. `pwrss` defaults to a standard-normal predictor, so it powers a one-standard-deviation
change, while PowerBench's binary branch contrasts two equally sized groups. Direct `glm`
Monte Carlo measures 0.31 power at N = 249 for a balanced binary design. Called with a
matched Bernoulli predictor, `pwrss` returns **856 exactly**.

So every adapter declares its own effect definition, predictor distribution, test variant,
degrees-of-freedom convention, allocation and tails
([`powerbench/parameterization.py`](powerbench/parameterization.py)), and declarations are
compared **before** the numbers. Two tools answering different questions cannot launder a
coincidental agreement into "compatible".

`probable_defect` is **never assigned automatically**. An unexplained gap becomes
`needs_review` for a human, because asserting that a named third-party tool is wrong is a
claim a person should make after looking. An undeclared field is treated as unknown, so a
silent adapter can never explain away a gap it never accounted for.

---

## Versioning

Two levels, because they answer different questions:

- **`powerbench.__version__`** — the package release.
- **`powerbench.METHOD_VERSIONS[method_id]`** — that method's *answers*, bumped only when
  a computed number changes for some input.

```python
import powerbench

powerbench.method_fingerprint("ordinal_regression")
# 'ordinal_regression@2.0.0'

for change in powerbench.changes_since("ordinal_regression", "1.0.0"):
    print(change.numeric_impact)
# Required N for OR=1.5, k=4, 80% power moves from 191 to 614...

powerbench.changes_since("two_sample_t", "1.0.0")
# []   <- the ordinal correction did not touch the t test
```

Cache keys, published study plans and validation records should bind to
`(method_id, method_version)`. A correction to one method must not invalidate work that
depended on another, and `changes_since` reports the **numeric impact** so a stale result is
actionable rather than merely void.

---

## Reproducing the checks

```bash
pytest -q                                                  # fast suite
pytest -m slow tests/test_reference_simulation_alignment.py # the correctness gate (~11 min)
```

External-tool fixtures in `data/benchmarks/` each ship with the script that generated them
in [`scripts/benchmarks/`](scripts/benchmarks/), so a reviewer can re-derive every committed
number rather than trusting a prose `source` field:

```bash
Rscript scripts/benchmarks/ordinal_regression_polr.R
```

Requires R with `pwr`, `pwrss`, `TOSTER`, `metafor` and `MASS`. Tests that need R skip
cleanly where it is absent rather than failing for an environment reason.

---

## Reporting a suspected error

**This is the contribution we most want.** If a number here disagrees with a tool you
trust, please open an issue using the
[calculation error template](.github/ISSUE_TEMPLATE/calculation-error.yml), which asks for
the method version, exact inputs, both numbers, and what produced your expectation.

You do not need to be certain. Many apparent disagreements turn out to be estimand
differences — and those still become useful case studies. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the bar a formula change has to clear.

---

## Status and limits

Beta. The engine is used in production by PowerMate, the alignment gate passes on every
committed scenario, and the corrections above are confirmed against independent R
implementations. It has not yet been reviewed by anyone outside the project — which is
precisely why it is public.

Known boundaries, stated rather than buried:

- **Mixed, clustered and longitudinal models** are not covered by closed-form paths.
- **Effect-size choice is yours.** No power tool can tell you the smallest effect worth
  detecting, and planning from a small pilot's observed effect systematically under-powers
  studies.
- **Random-effects meta-analysis** has a nearly flat power curve once between-study
  heterogeneity dominates; the required N is only weakly identified there, which the
  [case study](docs/discrepancies/meta_analysis_random_flat_power.md) explains.

## Licence

MIT. See [`LICENSE`](LICENSE).

## Citation

If PowerBench contributes to published work, please cite the repository and record the
method version you used (`powerbench.method_fingerprint(...)`), so the calculation can be
reproduced exactly.
