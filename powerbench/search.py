"""Bounded planning work; exhaustion is distinct from mathematical unreachability."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic


class SearchBudgetExceeded(ValueError):
    pass

_budget = ContextVar("powerbench_search_budget", default=None)

@contextmanager
def search_budget():
    existing = _budget.get()
    token = _budget.set(existing or {"deadline": monotonic() + 30, "iterations": 0})
    try:
        yield
    finally:
        _budget.reset(token)

def check_search_budget():
    state = _budget.get()
    if state is not None:
        state["iterations"] += 1
        if state["iterations"] > 100_000 or monotonic() > state["deadline"]:
            raise SearchBudgetExceeded("Planning search exceeded its 30-second or 100,000-iteration budget; no sample size was accepted")
