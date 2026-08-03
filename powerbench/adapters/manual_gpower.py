"""G*Power comparisons, captured by a human and committed to the repository.

G*Power is a desktop GUI with no scriptable interface, so it can never be run by an
adapter. It is also the tool most psychology and social-science researchers actually use,
which makes it the most valuable external comparison this project can carry and the one it
cannot automate.

The compromise is a recorded capture: a person runs G*Power, records the inputs they typed
and the numbers it produced, saves a screenshot, and commits the record. This adapter reads
those records and **never executes anything**.

Two honesty problems follow from putting a human in the loop, and both are handled here:

* A capture can drift from the scenario it claims to describe. If the scenario JSON changes
  after capture, the recorded numbers silently become a comparison against a design that no
  longer exists. Each capture stores the scenario hash it was taken against, and a mismatch
  is reported as `stale_capture` rather than as a result.
* A capture is only as trustworthy as its provenance. Each record names who captured it,
  when, with which G*Power version and on which OS, and carries a signature over its own
  contents. The signature is tamper-*evidence*, not authentication -- anyone with the repo
  can recompute it. Its job is to make a silent edit visible, not to prove identity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .base import Adapter
from ..parameterization import Parameterization
from ..schema import Scenario

CAPTURE_DIR = Path(__file__).parents[2] / "data" / "gpower_captures"

#: Fields that must be present for a capture to be usable at all.
REQUIRED_FIELDS = (
    "scenario_id",
    "method_id",
    "tool_version",
    "operating_system",
    "captured_on",
    "captured_by",
    "gui_test_family",
    "gui_inputs",
    "gui_outputs",
    "scenario_hash_at_capture",
)


def scenario_hash(scenario: Scenario) -> str:
    """Stable hash of the parts of a scenario a G*Power capture is answering.

    Deliberately excludes the simulation block: replication count and seed change what the
    *simulator* does, not what G*Power was asked. Including them would invalidate every
    capture whenever a scenario's Monte Carlo settings were tuned, which would train people
    to ignore staleness warnings.
    """
    payload = scenario.to_dict()
    material = {
        "model": payload["model"],
        "goal": payload["goal"],
        "target_power": payload["target_power"],
        "effect": payload["effect"],
        "design": payload["design"],
        "decision_rule": payload["decision_rule"],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def capture_signature(capture: dict[str, Any]) -> str:
    """Tamper-evidence over a capture's own contents.

    Recomputable by anyone with the repository, which is the point: it detects a screenshot
    swapped without updating the recorded numbers, or a number edited after the fact. It
    proves nothing about who ran G*Power.
    """
    material = {key: capture[key] for key in REQUIRED_FIELDS if key in capture}
    material["screenshots"] = sorted(capture.get("screenshots", []))
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def load_captures(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Every committed capture, keyed by scenario id."""
    root = directory or CAPTURE_DIR
    captures: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return captures
    for path in sorted(root.glob("*.json")):
        capture = json.loads(path.read_text(encoding="utf-8"))
        capture["_source"] = str(path.relative_to(root.parents[1]))
        captures[capture["scenario_id"]] = capture
    return captures


class ManualGPowerAdapter(Adapter):
    """Reads committed G*Power captures. Never launches anything."""

    id = "desktop.gpower"
    language = "gui"
    version = "captured per record"

    def __init__(self, directory: Path | None = None):
        self.directory = directory or CAPTURE_DIR
        self._captures = load_captures(self.directory)

    def parameterization(self, method_id: str) -> Parameterization:
        # G*Power's parameterization is recorded per capture, because it varies by the test
        # family the operator selected -- there is no single declaration for the tool.
        for capture in self._captures.values():
            if capture.get("method_id") == method_id:
                declared = capture.get("parameterization") or {}
                return Parameterization(**{
                    key: value for key, value in declared.items()
                    if key in Parameterization.__dataclass_fields__
                })
        return Parameterization()

    def supports(self, scenario: Scenario) -> bool:
        return scenario.id in self._captures

    def run(self, scenario: Scenario) -> dict:
        capture = self._captures.get(scenario.id)
        if capture is None:
            return {
                "status": "unsupported",
                "adapter": self.id,
                "reason": (
                    "G*Power cannot be scripted, so this comparison needs a human capture. "
                    "See docs/gpower_capture_protocol.md."
                ),
            }

        missing = [field for field in REQUIRED_FIELDS if field not in capture]
        if missing:
            return {
                "status": "error",
                "adapter": self.id,
                "reason": f"capture {capture['_source']} is missing required fields: {missing}",
            }

        recorded = capture.get("signature")
        recomputed = capture_signature(capture)
        if recorded and recorded != recomputed:
            return {
                "status": "error",
                "adapter": self.id,
                "reason": (
                    f"capture {capture['_source']} has been edited since it was signed "
                    f"(recorded {recorded}, recomputed {recomputed}). Re-capture rather "
                    "than re-signing: the numbers and the screenshot must agree."
                ),
            }

        current = scenario_hash(scenario)
        if capture["scenario_hash_at_capture"] != current:
            return {
                "status": "unavailable",
                "adapter": self.id,
                "reason": (
                    f"the scenario changed since this capture was taken "
                    f"(captured against {capture['scenario_hash_at_capture']}, now {current}). "
                    "The recorded numbers answer a design that no longer exists; re-capture "
                    "in G*Power before relying on them."
                ),
                "stale_capture": True,
            }

        return {
            "status": "ok",
            "adapter": self.id,
            "language": self.language,
            "package": "G*Power",
            "package_version": capture["tool_version"],
            "captured_by": capture["captured_by"],
            "captured_on": capture["captured_on"],
            "screenshots": capture.get("screenshots", []),
            "assumptions": capture.get("assumptions", []),
            "result": {
                "n_total": capture["gui_outputs"].get("total_sample_size"),
                "power": capture["gui_outputs"].get("actual_power"),
                "method": f"G*Power {capture['tool_version']} — {capture['gui_test_family']}",
            },
        }
