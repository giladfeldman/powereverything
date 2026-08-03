"""Every committed benchmark fixture must be re-derivable by a reviewer.

A fixture asserting "R 4.4.0 produced 0.800198984625495" is only evidence if someone else
can run the same computation and get the same number. Two fixtures originally shipped with
a `source` string and no script, which is the same trust problem as an uncited value
(PM-010 in project lessons). These checks are structural and fast -- they do not require R.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = REPO_ROOT / "data" / "benchmarks"

REQUIRED_FIELDS = ("source", "generated_on", "generator", "cases")


def fixture_paths() -> list[Path]:
    return sorted(BENCHMARK_DIR.glob("*.json"))


def test_benchmark_directory_is_not_empty() -> None:
    assert fixture_paths(), "no benchmark fixtures found; external adjudication is unbacked"


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_fixture_declares_provenance_and_a_committed_generator(path: Path) -> None:
    fixture = json.loads(path.read_text(encoding="utf-8"))

    for field in REQUIRED_FIELDS:
        assert field in fixture, f"{path.name} is missing required field {field!r}"

    generator = REPO_ROOT / fixture["generator"]
    assert generator.exists(), (
        f"{path.name} names generator {fixture['generator']!r}, which does not exist. "
        "A fixture whose provenance is only a prose string cannot be re-derived by a "
        "reviewer -- commit the script that produces it."
    )

    assert fixture["cases"], f"{path.name} declares no cases"
    for index, case in enumerate(fixture["cases"]):
        assert "inputs" in case, f"{path.name} case {index} has no inputs"
        assert "expected" in case, f"{path.name} case {index} has no expected values"


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_monte_carlo_fixtures_declare_a_tolerance(path: Path) -> None:
    """A simulated expectation without a tolerance cannot be compared honestly."""
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if "monte_carlo" not in fixture:
        return
    monte_carlo = fixture["monte_carlo"]
    assert "replications" in monte_carlo and "seed" in monte_carlo, (
        f"{path.name} records Monte Carlo expectations but not the replications and seed "
        "needed to reproduce them"
    )
    for index, case in enumerate(fixture["cases"]):
        assert "tolerance" in case, (
            f"{path.name} case {index} comes from simulation but declares no tolerance; "
            "an exact-equality comparison against a Monte Carlo estimate is not meaningful"
        )
