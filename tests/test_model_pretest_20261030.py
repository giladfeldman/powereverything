"""Regression controls for review-assistance defects found by the 2026-10-30 cheapest-model
pretest (Claude Haiku and Codex gpt-6-luna on synthetic power-review tasks).

Each test was observed failing on 0.9.0 (f265053) before its repair.
"""
from __future__ import annotations

from powerbench.review.assistant import assistant_prompt, validate_assistance
from powerbench.review.evidence import finding_supported, labeled_numbers


def _instructions(task, text, confirmed=None):
    """The task instructions alone: the prompt also echoes the confirmed record and source."""
    return assistant_prompt(task, text, confirmed)["prompt"].split("\nCONFIRMED_SHA256")[0]

CANONICAL = ("Under the stated planning assumptions for a two-sample t test, an analysable sample of "
             "148 participants (74 per group) was required. The target effect (Cohen's d = 0.5) is a planning "
             "assumption. Target power was 85%; the calculated value at the integer sample size was 0.8538.")
CONFIRMED = {"canonical_paragraph": CANONICAL, "target_power": 0.85, "alpha": 0.05, "effect": 0.5,
             "canonical_result": {"power": 0.8538, "n_per_group": 74, "n_total": 148},
             "chronology": "unknown", "effect_rationale": None}


def test_calculated_power_is_not_read_as_target_power():
    # Defect 1: "calculated power 0.8538" was captured as target power and the faithful
    # rewrite was rejected as "changed a labeled scientific quantity".
    assert labeled_numbers("target_power", "the calculated power was 0.8538") == []
    assert labeled_numbers("target_power", "target power was 0.85") == [0.85]
    paragraph = CANONICAL.replace("calculated value", "calculated power") + " [effect rationale needed]"
    out = validate_assistance("rewrite", "Selected paragraph.", {"paragraph": paragraph, "confirmed": CONFIRMED}, CONFIRMED)
    assert out["paragraph"] == paragraph


def test_rewrite_prompt_discloses_the_planning_assumption_wording_it_enforces():
    # Defect 2: the validator rejects a rewrite that drops "planning assumption", but the
    # prompt never said so.
    prompt = _instructions("rewrite", "A draft.", CONFIRMED)
    assert '"planning assumption"' in prompt


def test_code_prompt_names_every_goal_label():
    # Defect 3: gold for n=NULL calls is required_sample_size, never named in the prompt.
    prompt = _instructions("code", "pwr.t.test(d=0.5, power=0.8)")
    for goal in ("achieved_power", "required_sample_size", "sensitivity"):
        assert goal in prompt


def test_audit_prompt_says_what_to_quote_for_an_absent_item():
    # Defect 4: "every finding requires an exact supporting source quote" with no rule for
    # absences; Luna returned no missing-item findings at all.
    prompt = _instructions("audit", "A draft.")
    assert "missing_" in prompt and "quote the sentence" in prompt.lower()


def test_an_unjustified_smallest_effect_of_interest_is_a_missing_rationale():
    # Defect 5, owner ruling 2026-10-30 ("No, flag it"): naming a SESOI is not a rationale.
    bare = "We planned for the smallest effect of interest, d = 0.4, with alpha = .05."
    assert finding_supported("missing_effect_rationale", "the smallest effect of interest", bare)
    for justified in (
        "The smallest effect of interest, d = 0.4, followed prior evidence from a pilot.",
        "The smallest effect of interest (d = 0.4) was based on a cost-benefit analysis.",
        "The effect rationale was a published meta-analysis.",
    ):
        assert not finding_supported("missing_effect_rationale", "the smallest effect of interest", justified), justified


def test_code_prompt_says_simulation_code_has_no_analytic_fields():
    # Defect 6: gold sets every field null for simulation code; the prompt never said so.
    prompt = _instructions("code", "replicate(500, t.test(rnorm(40, 0.6), rnorm(40))$p.value < 0.025)")
    assert "simulation-based power code" in prompt and "every field null" in prompt


# Cross-model review (Sonnet, 2026-10-30) of the first 0.9.1 draft: counter-examples it ran.
def test_a_qualified_target_power_is_still_a_target():
    assert labeled_numbers("target_power", "estimated target power of 0.8") == [0.8]
    assert labeled_numbers("target_power", "The actual target power was 0.9") == [0.9]
    for result in ("calculated power 0.8538", "achieved power of 0.85", "resulting power was 0.81"):
        assert labeled_numbers("target_power", result) == [], result


_SESOI = "The smallest effect of interest was d = 0.30"
_GIVEN = (
    _SESOI + ", taken from earlier studies of this intervention.",
    _SESOI + ", since smaller effects would not be clinically meaningful.",
    _SESOI + " because below it the intervention costs outweigh its benefits.",
    _SESOI + ", consistent with the literature.",
    _SESOI + ", the effect reported in the original study.",
    _SESOI + ", set on the basis of earlier work.",
    _SESOI + ", as established by Smith (2019).",
    "We justify the smallest effect of interest d=0.30 as the minimum difference patients notice.",
)
_INCIDENTAL = (
    "Power was based on a two-sided test with alpha .05.",
    "Sample size was derived from the noncentral t formula.",
    "A pilot of the procedure checked the instructions.",
    "Analysis uses meta-analytic pooling of sites.",
    "N=200 based on 80% power.",
    "Practical significance will be assessed separately.",
    "Prior studies used different outcome measures.",
    "The test was chosen because data are normal.",
    "Participants were informed by email.",
    "The minimal important difference is not defined.",
)


def test_a_stated_basis_suppresses_missing_effect_rationale():
    for text in _GIVEN:
        assert not finding_supported("missing_effect_rationale", _SESOI, text), text


def test_incidental_wording_is_not_a_basis():
    for extra in _INCIDENTAL:
        text = _SESOI + ". " + extra
        assert finding_supported("missing_effect_rationale", _SESOI, text), extra
    assert finding_supported("missing_effect_rationale", _SESOI, "d = 0.30 is the SESOI; prior work is not cited.")


def test_rewrite_prompt_does_not_forbid_the_canonical_target_effect_wording():
    prompt = _instructions("rewrite", "A draft.", CONFIRMED)
    assert "may not become a target" not in prompt and "verbatim" in prompt


def test_code_prompt_says_what_to_quote_for_a_missing_seed():
    assert "quote the simulation line" in _instructions("code", "replicate(500, mean(rnorm(10)))")
