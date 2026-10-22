# Engineering lessons

## 2026-10-22 — Run quality tools from the package root

Import sorting can classify the package differently when invoked from a consuming application. Run `python -m ruff check powerbench tests` from this repository, then validate the built wheel in a consumer environment. Record the working directory with quality evidence.

## 2026-10-22 — Source fingerprints include cosmetic changes

The AI review contract fingerprints exact normalized source bytes. Import formatting and equivalent regex aliases change that fingerprint even when executable statements retain their meaning. Preserve previous benchmark provenance and require a matching fingerprint before routing; do not reuse an old qualification implicitly.

## 2026-10-22 — Keep independent numerical checks distinct from compatibility

A candidate producing matching values across Python dependency versions shows compatibility for those inputs. It is not an independent numerical oracle. Keep separate R comparisons, high-precision integration and simulation calibration evidence, including unresolved disagreements and approximation limits.
