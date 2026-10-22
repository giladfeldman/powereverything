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
