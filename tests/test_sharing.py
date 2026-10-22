import json

from powerbench.api import analyze
from powerbench.schema import load_scenario
from powerbench.sharing import anonymous_snapshot


def test_anonymous_allowlist_strips_identifying_metadata_and_generated_code():
    s=load_scenario("data/scenarios/two_sample_t_balanced.json").to_dict()
    marker="IDENTITY_SECRET_MARKER_Orcid_Email_Filename"
    s.update(id=marker,title=marker,assumptions=[marker])
    result=analyze({"operation":"plan","scenario":s})
    result["normalized_request"]["scenario"]["effect"]["private_note"]=marker
    result["normalized_request"]["scenario"]["design"]["owner"]=marker
    result["owner"]=marker
    result["reporting"]={"apa":marker}
    public=anonymous_snapshot(result)
    assert marker not in json.dumps(public)
    assert public["result"]["n_total"]==result["result"]["n_total"]
    assert public["provenance"]["engine_version"]==result["provenance"]["engine_version"]
    assert public["provenance"]["input_sha256"]!=result["provenance"]["input_sha256"]
    replay=analyze(public["normalized_request"])
    assert replay["result"]["n_total"]==public["result"]["n_total"]


def test_sensitivity_snapshot_replays_without_an_invented_effect():
    s=load_scenario("data/scenarios/two_sample_t_balanced.json").to_dict()
    s["goal"]="sensitivity";s["effect"].pop("cohens_d")
    result=analyze({"operation":"detectable_effect","scenario":s,"sample":{"n1":"100","n2":"100"}})
    public=anonymous_snapshot(result)
    assert "cohens_d" not in public["normalized_request"]["scenario"]["effect"]
    assert analyze(public["normalized_request"])["result"]["detectable_effect"]==result["result"]["detectable_effect"]

    assert public["normalized_request"]["sample"] == {"n1":100,"n2":100,"n_total":200}


def test_anonymous_snapshot_retains_only_neutral_reproduction_runtime():
    scenario=load_scenario("data/scenarios/two_sample_t_balanced.json").to_dict()
    result=analyze({"operation":"plan","scenario":scenario})
    result["provenance"]["runtime"]["platform"]="IDENTITY_PLATFORM_MARKER"
    result["provenance"]["dependencies"]["private-package"]="IDENTITY_DEPENDENCY_MARKER"
    public=anonymous_snapshot(result)
    assert public["provenance"]["dependencies"]=={name:result["provenance"]["dependencies"][name] for name in ("numpy","scipy")}
    assert public["provenance"]["runtime"]=={"python":result["provenance"]["runtime"]["python"]}
    assert "IDENTITY_" not in json.dumps(public)
    assert "execution" not in public["provenance"]
