"""Convert generated scientific values to finite ordinary JSON-compatible values."""
from math import isfinite
from typing import Any

import numpy as np


def json_values(value: Any) -> Any:
    if isinstance(value,np.ma.MaskedArray) and np.any(np.ma.getmaskarray(value)):
        raise ValueError("Masked scientific values require explicit missing-data handling")
    if isinstance(value,np.generic):
        ordinary=value.item()
        if isinstance(ordinary,np.generic):
            raise ValueError("Extended precision scalar cannot be represented as ordinary JSON")  # noqa: TRY004 -- portable scientific JSON uses ValueError for unsupported representations
        return json_values(ordinary)
    if isinstance(value,np.ndarray):
        return json_values(value.tolist())
    if isinstance(value,dict):
        if any(not isinstance(key,str) for key in value):
            raise ValueError("Scientific JSON object keys must be strings")
        return {key:json_values(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [json_values(item) for item in value]
    if isinstance(value,float) and not isfinite(value):
        raise ValueError("Scientific JSON results require finite numbers")
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    raise ValueError("Scientific result contains an unsupported JSON value")
