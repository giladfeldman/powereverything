"""Expected-retention recruitment policy: decimal arithmetic, rounding within arms/cells."""
from decimal import ROUND_CEILING, Decimal

RECRUITMENT_POLICY_VERSION = "1.2"

def recruitment_counts(result: dict, rate: float) -> dict:
    if isinstance(rate, bool) or not 0 <= rate < 1:
        raise ValueError("attrition_rate must lie in [0, 1)")
    retention = Decimal(1) - Decimal(str(rate))
    def inflate(n):
        return int((Decimal(int(n)) / retention).to_integral_value(rounding=ROUND_CEILING))
    if "n1" in result and "n2" in result:
        first, second = inflate(result["n1"]), inflate(result["n2"])
        return {"n1": first, "n2": second, "n_total": first + second}
    for key in ("n_per_group_per_study", "n_per_group", "n_per_cell"):
        if result.get(key):
            size = int(result[key]); units = int(result["n_total"]) // size
            if units * size != int(result["n_total"]):
                raise ValueError("Balanced-unit counts do not sum to the total")
            count = inflate(size)
            return {key: count, "n_total": count * units}
    return {"n_total": inflate(result["n_total"])}
