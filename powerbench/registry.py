from .adapters import (
    RGsDesignAdapter,
    RPowerSurvEpiAdapter,
    RPwrAdapter,
    RPwrssAdapter,
    RRpactAdapter,
    RWebPowerAdapter,
)


def automated_adapters():
    """The only location that declares executable adapters for a benchmark run.

    Each adapter must declare its own `parameterization()` so that a numeric difference can
    be attributed to a difference of question rather than reported as a defect. An adapter
    that declares nothing can never explain away a gap -- see
    `powerbench/parameterization.py`.

    The Monte Carlo specialist adapter (`r.specialist`) is appended by the matrix refresh
    script rather than listed here, because it is minutes-slow and must remain excludable
    by `--skip-slow`.
    """
    return [
        RPwrAdapter(),
        RPwrssAdapter(),
        RGsDesignAdapter(),
        RRpactAdapter(),
        RWebPowerAdapter(),
        RPowerSurvEpiAdapter(),
    ]
