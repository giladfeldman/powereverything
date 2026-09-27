"""Two-sided pin for scripts/check_docs_coverage.py.

PASS side: the real repo must currently report zero missing items.
FAIL side: a planted, undocumented method id must be caught.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_docs_coverage.py"

spec = importlib.util.spec_from_file_location("check_docs_coverage", SCRIPT)
check_docs_coverage_module = importlib.util.module_from_spec(spec)
sys.modules["check_docs_coverage"] = check_docs_coverage_module
spec.loader.exec_module(check_docs_coverage_module)
check_docs_coverage = check_docs_coverage_module.check_docs_coverage


def test_real_repo_has_no_drift():
    missing = check_docs_coverage(ROOT)
    assert missing == [], f"real repo should have zero doc drift, got: {missing}"


def test_planted_undocumented_method_id_is_caught(tmp_path, monkeypatch):
    import powerbench

    fake_id = "totally_planted_fake_method_id"
    real_methods = powerbench.all_methods()
    monkeypatch.setattr(powerbench, "all_methods", lambda: {**real_methods, fake_id: "1.0.0"})

    # Same README/registry, but README obviously does not mention the fake id.
    (tmp_path / "README.md").write_text((ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "citation_registry.csv").write_text(
        (ROOT / "data" / "citation_registry.csv").read_text(encoding="utf-8"), encoding="utf-8"
    )

    missing = check_docs_coverage(tmp_path)
    assert any(fake_id in item for item in missing), f"planted id should be caught, got: {missing}"
