"""PowerBench: reproducible, assumption-aware power-analysis benchmarking.

Public surface. Alongside the package version, each planning method carries its own
version (`powerbench.versioning`), bumped only when that method's computed answers
change. Downstream consumers -- caches, validation ledgers, published study plans -- should
bind to `(method_id, method_version)` rather than to the package version, so an unrelated
fix does not invalidate everything at once.
"""

from .schema import Scenario, load_scenario
from .versioning import (
    METHOD_CHANGELOG,
    METHOD_VERSION,
    METHOD_VERSIONS,
    MethodChange,
    all_methods,
    changes_since,
    method_fingerprint,
    method_version,
)

__version__ = "0.8.2"

__all__ = [
    "Scenario",
    "load_scenario",
    "METHOD_CHANGELOG",
    "METHOD_VERSION",
    "METHOD_VERSIONS",
    "MethodChange",
    "all_methods",
    "changes_since",
    "method_fingerprint",
    "method_version",
    "__version__",
]

