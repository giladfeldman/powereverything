"""Per-method versioning is the identity human validations bind to.

If this contract is wrong, validation records point at the wrong thing -- silently. These
checks are cheap and structural; they exist because the failure mode is invisible at
runtime and only shows up when someone tries to interpret an old attestation.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from powerbench.schema import Model
from powerbench.versioning import (
    METHOD_CHANGELOG,
    METHOD_VERSIONS,
    all_methods,
    changes_since,
    method_fingerprint,
    method_version,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_registry_covers_exactly_the_planner_models():
    assert set(METHOD_VERSIONS) == set(get_args(Model))


def test_versions_are_semantic_triples():
    for method_id, version in METHOD_VERSIONS.items():
        parts = version.split(".")
        assert len(parts) == 3, f"{method_id} version {version!r} is not major.minor.patch"
        assert all(part.isdigit() for part in parts), f"{method_id} version {version!r} is not numeric"


def test_fingerprint_is_stable_and_specific():
    assert method_fingerprint("ordinal_regression") == f"ordinal_regression@{method_version('ordinal_regression')}"
    assert method_fingerprint("two_sample_t") != method_fingerprint("ordinal_regression")


def test_changes_since_current_version_is_empty():
    """A validation against the current version is never stale."""
    for method_id, version in all_methods().items():
        assert changes_since(method_id, version) == [], (
            f"{method_id} reports changes after its own current version {version}"
        )


def test_changes_since_reports_only_that_method():
    """A fix to one method must not invalidate validations of another.

    This is the whole reason methods are versioned individually rather than inheriting the
    package version.
    """
    ordinal_changes = changes_since("ordinal_regression", "1.0.0")
    assert ordinal_changes, "the 2026-08-03 ordinal correction is missing from the changelog"
    assert all(change.method_id == "ordinal_regression" for change in ordinal_changes)
    assert changes_since("two_sample_t", "1.0.0") == []


def test_changelog_entries_state_a_numeric_impact():
    """A validator whose attestation went stale is owed specifics, not a vague note."""
    vague = {"improved", "more accurate", "better", "fixed", "corrected"}
    for change in METHOD_CHANGELOG:
        assert change.method_id in METHOD_VERSIONS, f"changelog names unknown method {change.method_id!r}"
        assert len(change.numeric_impact) >= 60, (
            f"{change.method_id}@{change.version} numeric_impact is too thin to act on: "
            f"{change.numeric_impact!r}"
        )
        lowered = change.numeric_impact.lower()
        assert not (set(lowered.split()) <= vague), f"{change.method_id} impact is vague"


def test_changelog_versions_exist_and_are_not_ahead_of_the_registry():
    for change in METHOD_CHANGELOG:
        current = METHOD_VERSIONS[change.method_id]
        current_parts = tuple(int(p) for p in current.split("."))
        change_parts = tuple(int(p) for p in change.version.split("."))
        assert change_parts <= current_parts, (
            f"{change.method_id} changelog records {change.version} but the registry says "
            f"{current}; bump METHOD_VERSIONS in the same commit as the changelog entry."
        )


def test_no_duplicate_changelog_entries():
    seen = set()
    for change in METHOD_CHANGELOG:
        key = (change.method_id, change.version)
        assert key not in seen, f"duplicate changelog entry for {key}"
        seen.add(key)


def test_methods_corrected_this_release_were_version_bumped():
    """Every method whose answers changed on 2026-08-03 must carry a new major version.

    Guards against the specific failure of fixing a formula and leaving the version alone,
    which would leave prior validations looking current against different numbers.
    """
    corrected = {
        "ordinal_regression",
        "logistic_regression",
        "meta_analysis_random",
        "group_sequential_t",
        "mediation_indirect",
    }
    for method_id in corrected:
        assert METHOD_VERSIONS[method_id].startswith("2."), (
            f"{method_id} had its answers changed but is still at "
            f"{METHOD_VERSIONS[method_id]}"
        )
        assert any(c.method_id == method_id for c in METHOD_CHANGELOG), (
            f"{method_id} changed but has no changelog entry explaining the impact"
        )


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        method_version("not_a_real_method")
    with pytest.raises(ValueError):
        changes_since("not_a_real_method", "1.0.0")


def test_package_exposes_version_and_method_registry():
    import powerbench

    assert powerbench.__version__
    assert powerbench.METHOD_VERSION
    assert powerbench.all_methods() == METHOD_VERSIONS


def test_package_version_matches_pyproject_and_requirements():
    """Three places declare dependency and version facts; drift between them is a deploy bug."""
    import powerbench

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{powerbench.__version__}"' in pyproject, (
        "powerbench.__version__ and pyproject.toml [project].version disagree"
    )

    for dependency in ("scipy", "numpy"):
        assert dependency in pyproject, f"{dependency} missing from pyproject dependencies"

    # requirements.txt is a deploy artifact of a consuming application, not of this
    # package, so it is only checked where one exists.
    requirements_path = REPO_ROOT / "requirements.txt"
    if requirements_path.exists():
        requirements = requirements_path.read_text(encoding="utf-8")
        for dependency in ("scipy", "numpy"):
            assert dependency in requirements, (
                f"{dependency} is a runtime import but is missing from requirements.txt"
            )
