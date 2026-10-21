"""Runtime metadata and examples are package resources, never website-relative files."""
import json
from importlib.resources import files


def method_attribution(model: str) -> dict:
    resource = files("powerbench").joinpath("resources/method_attribution.json")
    return json.loads(resource.read_text(encoding="utf-8")).get("methods", {}).get(model, {})


def example(name: str) -> dict:
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("Use an example name, not a path")
    return json.loads(files("powerbench").joinpath("resources/scenarios/" + name + ".json").read_text(encoding="utf-8"))
