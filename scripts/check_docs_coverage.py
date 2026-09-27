"""Documentation-drift gate: the public surface in the CODE must appear in README.md.

    python scripts/check_docs_coverage.py

Exit 0 = every public export, every registered method id, and every DOI-bearing citation
registry row is documented; exit 1 = drift, with every missing item listed. Pinned two-sided
by tests/test_docs_coverage_gate.py.

WHY THIS EXISTS (2026-09-27). PowerBench already derives its OWN calculation correctness from
independent checks (the alignment gate, the citation registry verified against Crossref) --
this gate applies the same discipline to the README's coverage claims. The surface is DERIVED
from code, never hand-kept:

- `powerbench.__all__` (the package's declared public API)
- `powerbench.all_methods()` (every registered design/method id)
- every row of `data/citation_registry.csv` whose scope is a primary_literature source
  (a "maintained_official_documentation" row documents a library, not a design, and is not
  required to appear verbatim -- see README's Statistical basis section for the rationale)

"Documented" means the literal string appears anywhere in README.md.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _import_working_tree():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import powerbench

    return powerbench


def check_docs_coverage(root: Path = ROOT) -> list[str]:
    missing: list[str] = []
    readme = (root / "README.md").read_text(encoding="utf-8")

    powerbench = _import_working_tree()

    for name in powerbench.__all__:
        if name not in readme:
            missing.append(f"public export `{name}` (powerbench.__all__) not mentioned in README.md")

    for method_id in powerbench.all_methods():
        if method_id not in readme:
            missing.append(f"method id `{method_id}` (powerbench.all_methods()) not mentioned in README.md")

    registry_path = root / "data" / "citation_registry.csv"
    with registry_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["source_type"] != "primary_literature":
                continue
            citation_id = row["citation_id"]
            # A citation is documented if either its registry id or its DOI appears --
            # the README table above cites by author/year/DOI, not by the internal id.
            doi = row["source_url"].removeprefix("https://doi.org/")
            if citation_id not in readme and doi not in readme:
                missing.append(
                    f"citation `{citation_id}` ({row['citation']}) not mentioned in README.md "
                    f"(checked for id or DOI {doi})"
                )

    return missing


def main() -> int:
    missing = check_docs_coverage()
    if not missing:
        print(
            "PASS: every powerbench.__all__ export, every registered method id, and every "
            "primary-literature citation is documented in README.md"
        )
        return 0
    print(f"FAIL: {len(missing)} undocumented item(s):")
    for item in missing:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
