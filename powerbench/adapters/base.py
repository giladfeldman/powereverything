from __future__ import annotations

from abc import ABC, abstractmethod

from ..parameterization import Parameterization
from ..schema import Scenario


class Adapter(ABC):
    """A third-party power tool, wrapped so its answers can be compared.

    Status contract, preserved from the original implementation because the distinction
    carries real information:

    * ``ok``          -- the tool ran and produced a number.
    * ``unsupported`` -- the tool *cannot represent* this design. Declining is the correct
      answer; forcing a number would be worse than silence.
    * ``unavailable`` -- the environment failed (R missing, binary not found). Says nothing
      about the design.
    * ``error``       -- the tool ran and failed.
    * ``manual``      -- a human captured this from a GUI; see the capture record.

    ``unsupported`` and ``unavailable`` must never be collapsed: one is a statement about
    the design, the other about the machine.
    """

    id: str
    language: str
    #: Version of the wrapped tool, filled in by the adapter where it can be detected.
    version: str = "unknown"

    @abstractmethod
    def supports(self, scenario: Scenario) -> bool: ...

    @abstractmethod
    def run(self, scenario: Scenario) -> dict: ...

    def parameterization(self, method_id: str) -> Parameterization:
        """Declare how *this tool* defines what it computes for `method_id`.

        Differences between tools are only attributable when each declares its own
        semantics. Without this, a numeric gap is uninterpretable and the comparison
        degenerates into "these numbers differ, shrug" -- or worse, into accusing a correct
        tool of a defect because it answers a different question.

        The default returns an empty declaration, which is deliberately treated as
        *unknown* rather than as agreement: an undeclared field can never be used to
        explain away a difference.
        """
        return Parameterization()
