"""Integer arm allocation from the declared decimal ratio, without float ceilings."""
from fractions import Fraction
from math import isfinite


def allocated_arm_count(first: int, ratio: float | Fraction, minimum: int = 2) -> int:
    """Return max(minimum, ceil(first * decimal ratio)) using exact integers.

    The shortest decimal representation of a validated numeric input defines its
    ratio. No tolerance is subtracted: a genuinely greater product still rounds up.
    """
    if isinstance(first, bool) or not isinstance(first, int) or first < 1:
        raise ValueError("First-arm count must be a positive integer")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError("Minimum arm count must be a positive integer")
    if isinstance(ratio, bool) or not isinstance(ratio,(int,float,Fraction)) or not isfinite(ratio) or ratio <= 0:
        raise ValueError("Allocation ratio must be finite and positive")
    exact = Fraction(str(ratio))
    return max(minimum, (first * exact.numerator + exact.denominator - 1) // exact.denominator)


def declared_allocation_ratio(design: dict) -> Fraction:
    """An explicit integer n2:n1 pair takes precedence over a matching float alias."""
    pair=(design.get("allocation_numerator"),design.get("allocation_denominator"))
    if pair != (None,None):
        if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not float(value).is_integer() or not 1 <= value <= 1_000_000_000 for value in pair):
            raise ValueError("Allocation numerator and denominator must both be positive integers at most 1,000,000,000")
        ratio=Fraction(int(pair[0]),int(pair[1]))
        if "allocation_ratio" in design and design["allocation_ratio"] != float(ratio):
            raise ValueError("Conflicting decimal allocation ratio and exact integer pair")
        return ratio
    ratio=design.get("allocation_ratio",1.0)
    if isinstance(ratio,bool) or not isinstance(ratio,(int,float)) or not isfinite(ratio) or ratio <= 0:
        raise ValueError("Allocation ratio must be finite and positive")
    return Fraction(str(ratio))


def rounded_control_arm(total: int, ratio: Fraction) -> int:
    """Nearest control-arm count, exact half-up; retain two observations per arm."""
    if isinstance(total,bool) or not isinstance(total,int) or total < 4:
        raise ValueError("Total allocation requires an integer of at least four")
    if not isinstance(ratio,Fraction) or ratio <= 0:
        raise ValueError("Rounded allocation requires a positive declared rational ratio")
    first=Fraction(total,1)/(1+ratio)
    rounded=(2*first.numerator+first.denominator)//(2*first.denominator)
    return max(2,min(total-2,rounded))
