# Contributing to PowerBench

PowerBench computes sample sizes that researchers use to plan real studies. A wrong number
here can cause a study to be designed at a third of the power its authors believe it has —
that is not hypothetical, it is what happened to the ordinal path before 2026-08-03.

So the most valuable contribution is **telling us a number is wrong**, and the bar for
changing a formula is correspondingly high.

## Reporting a suspected calculation error

This is the contribution we most want. Open an issue with:

1. **Method** — the planner model id (e.g. `ordinal_regression`) and its version from
   `/api/health` or `powerbench.method_version("ordinal_regression")`.
2. **Exact inputs** — effect size, alpha, target power, alternative, and every design
   field. A scenario JSON is ideal.
3. **What PowerBench returned.**
4. **What you expected**, and **what produced that expectation** — a named tool and
   version (G\*Power 3.1.9.7, R `pwr` 1.3.0, PASS, a textbook formula with a citation).

Point 4 is what makes a report actionable. Please also state the tool's own
parameterization if you know it: many apparent disagreements are estimand differences, not
errors. `pwrss.z.logreg` returns 249 where PowerBench returns 856 for what looks like the
same design, because pwrss defaults to a *normal* predictor while PowerBench's binary
branch contrasts two equally sized groups. Both are right for their own question. See
`docs/discrepancies/` for how these are recorded.

You do not need to be certain. A report that turns out to be an assumption difference is
still useful — it becomes a case study.

## Changing a formula

Every formula change must clear all of these:

1. **A published source.** Name the paper and the equation. "This looks more correct" is
   not enough; a real author's name attached to the wrong formula is worse than no
   attribution at all.
2. **The alignment gate passes.**
   ```bash
   pytest -m slow tests/test_reference_simulation_alignment.py
   ```
   This compares every analytic reference against an independent Monte Carlo simulator
   across three seeds at 12,000 replications. It is the only test here that can falsify a
   formula: every `required_n_*` is a `while power < target: n += 1` loop, so
   `assert power >= target_power` passes regardless of whether the maths is right.

   **Do not widen `GATE_TOLERANCE` to make a scenario pass.** If the analytic and simulated
   designs genuinely differ, write a case study in `docs/discrepancies/` and add a
   `DocumentedDivergence` entry with a direction and a maximum gap. Allowlisted scenarios
   are still tested against that envelope, and the entry expires automatically once the
   divergence resolves.
3. **An independent adjudicator.** Validate against R (or another established tool) and
   commit both the fixture in `data/benchmarks/` **and** the script that generates it in
   `scripts/benchmarks/`. A fixture whose provenance is only a prose string cannot be
   re-derived by a reviewer, which is the same problem as an uncited number.
4. **A version bump.** If the method's answers change for any input, bump its entry in
   `powerbench/versioning.py::METHOD_VERSIONS` and add a `METHOD_CHANGELOG` entry stating
   the **numeric impact** — what moved, and by how much. Downstream consumers and human
   validators bind to `(method_id, method_version)`; they are owed specifics, not "improved
   accuracy".
5. **Honest coverage status.** `data/coverage_matrix.json` statuses are public claims.
   `tests/test_coverage_matrix_evidence.py` refuses any `verified_*` status for a method
   that is allowlisted in the alignment gate.

## Adding a method

Beyond the above: add a scenario to `data/scenarios/` (the gate globs the directory, so it
enrols automatically), a simulator branch in `powerbench/simulation.py` that shares no code
with the analytic reference, a `METHOD_VERSIONS` entry, and a coverage-matrix row.

The simulator must be an *independent* implementation. If it embeds the same simplifying
assumption as the reference, the two will agree while both being wrong — which is precisely
how the ordinal and group-sequential defects survived.

Check the per-replication cost before adding a model fit: a per-observation Python loop
once put the gate at 64 minutes for a single scenario.

## Running the tests

```bash
pytest -q
```

```bash
pytest -q -m slow
```

The fast suite runs in a few minutes. The slow gate takes about 24 minutes and is excluded
by default; run it whenever you touch `references.py`, `specialist_extras.py`,
`simulation.py`, or `data/scenarios/`.

## What we will not merge

- A formula change without an independent adjudicator.
- A widened tolerance in place of an explanation.
- A new method whose simulator reuses the reference's assumptions.
- A coverage status that outruns its evidence.
