from .adapters import RPwrAdapter, RPwrssAdapter


def automated_adapters():
    """The only location that declares executable adapters for a benchmark run.

    Each adapter must declare its own `parameterization()` so that a numeric difference can
    be attributed to a difference of question rather than reported as a defect. An adapter
    that declares nothing can never explain away a gap -- see
    `powerbench/parameterization.py`.
    """
    return [RPwrAdapter(), RPwrssAdapter()]
