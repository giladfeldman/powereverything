# Engineering lessons

## 2026-10-22 — Run quality tools from the package root

Import sorting can classify the package differently when invoked from a consuming application. Run `python -m ruff check powerbench tests` from this repository, then validate the built wheel in a consumer environment. Record the working directory with quality evidence.

## 2026-10-22 — Source fingerprints include cosmetic changes

The AI review contract fingerprints exact normalized source bytes. Import formatting and equivalent regex aliases change that fingerprint even when executable statements retain their meaning. Preserve previous benchmark provenance and require a matching fingerprint before routing; do not reuse an old qualification implicitly.

## 2026-10-22 — Keep independent numerical checks distinct from compatibility

A candidate producing matching values across Python dependency versions shows compatibility for those inputs. It is not an independent numerical oracle. Keep separate R comparisons, high-precision integration and simulation calibration evidence, including unresolved disagreements and approximation limits.

## 2026-10-22 - Validate sample units and every export surface

Canonical sample counts must use the same bounds whether supplied or derived. Paired and other single-sample models must reject independent-arm counts; independent arms must yield a consistent total. Framework labels and integer wizard fields are scientific contracts, not display hints. Recompute all bundle presentation artifacts from the verified request: checking numeric results alone does not authenticate saved code, prose or citations. Regression controls reproduced these failures before the fixes.

## 2026-10-22 - Keep legacy exports explicit

The planner stores its numeric calculation under reference rather than result. Compatibility export must compare that dictionary with a canonical plan replay, retaining all version guards. A present falsey result must not trigger fallback. Regenerate all bundle artifacts and disclose that the calculation bundle excludes legacy simulations/sweeps; full wizard reproduction remains separate. A watched-red legacy planner regression covers the real caller.

## 2026-10-22 - Reject unused scientific fields

Unknown model-specific effect/design fields can appear in deterministic paragraphs without affecting the calculation. Explicit allowlists now reject them and are exposed in capabilities. Supplied GOF w must agree with the probability vectors. Preserve genuinely supported variants such as binary logistic allocation; its independent R adapter regression detected an initially incomplete allowlist.

## 2026-10-22 - Keep multiplicity declarations consistent

Unadjusted multiple primary tests must not silently disappear from wizard metadata. Family alpha must match the per-test rule, and explicit invalid counts never default to one. Contract and wizard regressions cover both paths.

## 2026-10-22 - Report the criterion actually computed

Case-insensitive BIC selection and default ROPE thresholds must be reflected in manuscript text. Sensitivity output must describe the solved effect rather than the temporary internal placeholder. Template 1.4 fixes reproduced controls without changing numerical kernels.

## 2026-10-22 - Require complete snapshot quantities

Empty/null stored result dictionaries could yield an apparently complete anonymous snapshot or an AttributeError. Require a numeric dictionary with the same scientific quantity keys as the replay before comparison.

## 2026-10-22 - Bind export inputs to their saved hash

A request change that leaves analytic N unchanged can still change recruitment. Verify the stored input hash before exporting, reconstruct all artifacts, and generate a substantive canonical report.md instead of hashing an empty report.

## 2026-10-22 - Bound AI numeric conversion

Representable JSON integers can exceed floating-point range; percentage scaling can overflow even when the unscaled integer is finite. Withhold unsupported proposals and raise validation errors for invalid confirmed inputs. Four watched-red controls cover extraction, static code inspection and rewrite confirmation.

## 2026-10-22 - Bind rewrite design and evidence claims

Keeping a confirmed JSON record unchanged does not keep the paragraph true. Five watched-red mutations changed independent samples into pairs, doubled per-group units, asserted a different test, invented a prior-evidence rationale or removed the hypothetical-effect caveat. Bounded model/unit/claim screens now reject those mutations. They remain conservative lexical controls, not semantic certification; proposals still require source and author confirmation.

## 2026-10-22 - Validate supported parameter combinations and disclose defaults

Requested Opus 5.5 source review identified missing positive allocation checks for logistic/ordinal models, ignored allocation for continuous predictors, partial event models, and numeric-string inconsistency. Twenty-one watched-red controls also exposed uppercase-BIC sharing, stale snapshot input/method identity, silently discarded wizard sample counts, inferred review assumptions, hidden prior defaults and swapped rewrite count/sidedness claims. Validate these combinations, bind snapshot identity before anonymizing, disclose actual priors and keep bounded rewrite proposals subject to human confirmation. Replay agreement does not establish scientific validity. The historical privacy-stripping fixture must carry its intentionally constructed saved input hash; separate mutation tests require rejection when it changes.

## 2026-10-22 - Pair rejection controls with valid boundary designs

The requested Opus follow-up reproduced an over-restriction in a new survival guard: zero additional follow-up remains valid with positive accrual. Sonnet and Opus also identified malformed snapshot shapes, non-scalar numeric fields and further silent design defaults. Preserve the valid boundary and require scalar scientific parameters, validate malformed snapshots before dereference, disclose consumed defaults in a structured ledger/manuscript draft, and pair rewrite mutations with acceptance of the exact unmutated paragraph. Replay/hashes prove consistency and accidental-drift detection, not authenticity or universal mathematical validity. Ten more watched-red controls cover these defects including TOST default zero and huge deterministic reported values; explicit binary/continuous logistic and review positive controls prevent blanket rejection.

## 2026-10-23 - Round allocations with exact decimals, and check every caller of a new raise

Floating `ceil(100 * 1.1)` is 111 and banker's rounding split 67 at ratio .072 as 62+5; exact decimal half-up arithmetic gives 110 and 63+4, which moved required N at boundaries (two_sample_t 211 to 210). Declared ratios are decimals, so integer arm counts must come from exact arithmetic, and each affected method version is bumped with its numeric impact. Separately, making `jzs_bf10_from_t` raise above exp(709) was correct for the analytic path but aborted every Bayes simulation with one huge replicate, because the simulator called it unguarded; a new raise needs a pass over all unchanged callers, and a decisive-but-unrepresentable value is counted, never dropped or replaced by a finite number.

## 2026-10-23 - Disclose substituted inputs where the reader will look, and keep the disclosure when sharing

A takeover cross-model review found the field parser silently filled log-rank follow-up/hazards (changing N) and target power .95 / attrition 0. The disclosure is now a structured assumption line checked against the scenario value, so it cannot be forged or go stale, and shared snapshots keep exactly those lines. A string-presence test of planner.js stayed green while the browser planner had lost its sensitivity table; a test that submits every method's own example values found two pages whose default example never computed.

## 2026-10-24 - Release metadata drifts silently: sync CITATION.cff with the package version

CITATION.cff still said 0.8.2 / 2026-09-27 while the package, CHANGELOG and docs were 0.9.0, and the README's `__version__` example was stale. No test compared them. Cleanup now greps every version-bearing file (pyproject, `__init__`, CITATION.cff, README, CHANGELOG) before a release; scripts/ had also drifted from the ruff baseline (unused imports, dead `noqa`), fixed by `ruff --fix`.
