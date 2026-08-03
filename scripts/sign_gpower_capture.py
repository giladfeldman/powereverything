"""Sign a G*Power capture, or verify every committed capture.

The signature is tamper-evidence, not authentication: anyone with the repository can
recompute it. Its job is to make a later silent edit visible -- a screenshot swapped
without updating the recorded numbers, or a number adjusted after the fact.

Usage:

    python scripts/sign_gpower_capture.py data/gpower_captures/<file>.json   # sign one
    python scripts/sign_gpower_capture.py --verify                           # check all
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from powerbench.adapters.manual_gpower import (  # noqa: E402
    CAPTURE_DIR,
    REQUIRED_FIELDS,
    capture_signature,
    scenario_hash,
)
from powerbench.schema import load_scenario  # noqa: E402

SCENARIO_DIR = REPO_ROOT / "data" / "scenarios"


def find_scenario(scenario_id: str):
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        if json.loads(path.read_text(encoding="utf-8"))["id"] == scenario_id:
            return load_scenario(path)
    return None


def sign(path: Path) -> int:
    capture = json.loads(path.read_text(encoding="utf-8"))

    missing = [field for field in REQUIRED_FIELDS if field not in capture]
    if missing:
        print(f"FAIL: {path.name} is missing required fields: {missing}", file=sys.stderr)
        return 1

    scenario = find_scenario(capture["scenario_id"])
    if scenario is None:
        print(f"FAIL: no committed scenario with id {capture['scenario_id']!r}", file=sys.stderr)
        return 1

    current = scenario_hash(scenario)
    if capture["scenario_hash_at_capture"] != current:
        print(
            f"FAIL: {path.name} records scenario hash {capture['scenario_hash_at_capture']} "
            f"but the scenario now hashes to {current}.\n"
            "      Re-run G*Power against the current scenario rather than editing the hash;\n"
            "      the recorded numbers answer a design that no longer exists.",
            file=sys.stderr,
        )
        return 1

    for relative in capture.get("screenshots", []):
        if not (REPO_ROOT / relative).exists():
            print(
                f"FAIL: {path.name} names screenshot {relative}, which does not exist.\n"
                "      A capture without its screenshot is not verifiable.",
                file=sys.stderr,
            )
            return 1

    capture["signature"] = capture_signature(capture)
    path.write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
    print(f"Signed {path.name}: {capture['signature']}")
    return 0


def verify_all() -> int:
    captures = sorted(CAPTURE_DIR.glob("*.json")) if CAPTURE_DIR.exists() else []
    if not captures:
        print("No G*Power captures committed yet. See docs/gpower_capture_protocol.md.")
        return 0

    failures = 0
    for path in captures:
        capture = json.loads(path.read_text(encoding="utf-8"))
        recorded = capture.get("signature")
        recomputed = capture_signature(capture)
        if recorded != recomputed:
            print(
                f"FAIL {path.name}: edited since signing (recorded {recorded}, "
                f"recomputed {recomputed})",
                file=sys.stderr,
            )
            failures += 1
            continue

        scenario = find_scenario(capture["scenario_id"])
        if scenario is None:
            print(f"FAIL {path.name}: scenario {capture['scenario_id']!r} no longer exists", file=sys.stderr)
            failures += 1
            continue

        current = scenario_hash(scenario)
        if capture["scenario_hash_at_capture"] != current:
            print(f"STALE {path.name}: scenario changed since capture; re-capture in G*Power")
            failures += 1
            continue

        print(f"OK   {path.name} ({capture['tool_version']}, captured {capture['captured_on']})")

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", nargs="?", help="capture JSON to sign")
    parser.add_argument("--verify", action="store_true", help="verify every committed capture")
    args = parser.parse_args()

    if args.verify:
        return verify_all()
    if not args.capture:
        parser.error("pass a capture file to sign, or --verify")
    return sign(Path(args.capture))


if __name__ == "__main__":
    raise SystemExit(main())
