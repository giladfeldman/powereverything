"""Verify every DOI in data/citation_registry.csv against Crossref.

The registry's `status` column was hand-asserted until 2026-08-03: nothing checked that a
registered source actually resolves, or that its title and year match what the row claims.
That is the same trust problem as an uncited number, one level up.

This script does what `scripts/resolve_legacy_links.py` already does for guide links: asks
Crossref, and reports a mismatch rather than assuming.

    python scripts/verify_citations.py
    python scripts/verify_citations.py --strict   # exit non-zero on any problem
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "data" / "citation_registry.csv"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+")
USER_AGENT = "PowerBench-citation-audit/1.0 (mailto:giladfel@gmail.com)"


def crossref(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)["message"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any problem")
    args = parser.parse_args()

    rows = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    problems = 0
    checked = 0
    skipped: list[str] = []

    for row in rows:
        match = DOI_PATTERN.search(row.get("source_url", ""))
        if not match:
            # Documentation URLs have no DOI, so Crossref cannot adjudicate them. Report
            # them explicitly rather than passing over them: a summary of "checked 14"
            # against an 18-row registry reads as full coverage when it is not.
            skipped.append(row["citation_id"])
            continue
        checked += 1
        doi = match.group(0).rstrip(".,);")
        try:
            record = crossref(doi)
        except Exception as error:  # noqa: BLE001 - report rather than abort the sweep
            print(f"FAIL  {row['citation_id']}: {type(error).__name__}")
            problems += 1
            continue

        title = (record.get("title") or ["(untitled)"])[0]
        year = (record.get("issued", {}).get("date-parts") or [[None]])[0][0]
        claimed = re.search(r"\((\d{4})\)", row["citation"])
        claimed_year = int(claimed.group(1)) if claimed else None

        # A reissue legitimately carries a later date than the edition being cited, so a
        # year gap is reported for a human to read rather than failed automatically.
        note = ""
        if claimed_year and year and abs(year - claimed_year) > 1:
            note = f"  [registry says {claimed_year}, Crossref says {year}]"
        safe_title = title.encode("ascii", "replace").decode()
        print(f"OK    {row['citation_id']:<26} {year} {safe_title[:60]}{note}")

    print(f"\nchecked {checked} of {len(rows)} registry rows against Crossref, {problems} unresolvable")
    if skipped:
        print(f"not checkable by DOI ({len(skipped)}): {', '.join(skipped)}")
        print("  These are documentation URLs, which Crossref cannot adjudicate. Verify")
        print("  their reachability separately rather than reading this run as full coverage.")
    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
