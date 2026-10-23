"""Stable scientific input identity, separate from run timestamps and accounts."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from typing import Any

INPUT_HASH_POLICY_VERSION = "1.1"


def _canonical_numbers(value: Any) -> Any:
    # JSON has one number type. Browsers drop redundant .0 and negative-zero
    # spellings; those spellings must not change scientific input identity.
    if isinstance(value,float) and value.is_integer():
        return int(value)
    if isinstance(value,list):
        return [_canonical_numbers(item) for item in value]
    if isinstance(value,tuple):
        return [_canonical_numbers(item) for item in value]
    if isinstance(value,dict):
        return {key:_canonical_numbers(item) for key,item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical_numbers(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def input_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def provenance(model: str, request: dict, method_version_override: str | None = None) -> dict:
    from . import __version__, method_version

    return {
        "engine_version": __version__, "method_id": model,
        "method_version": method_version_override or method_version(model), "input_hash_policy_version": INPUT_HASH_POLICY_VERSION, "input_sha256": input_hash(request),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")},
        "execution": {"created_at": datetime.now(UTC).isoformat()},
    }
