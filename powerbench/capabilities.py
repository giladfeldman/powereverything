"""Conservative capabilities: unsupported goals are never silently substituted."""
from typing import get_args

from .schema import Model

DEFAULT_TARGET_POWER = 0.95
FIXED_MODELS = {
    "two_sample_t": "cohens_d", "welch_t": "mean_difference", "paired_t": "cohens_dz",
    "correlation": "rho", "one_way_anova": "cohens_f",
    "linear_regression": "cohens_f2", "incremental_regression": "cohens_f2",
    "moderation": "cohens_f2", "factorial_anova": "cohens_f", "ancova": "cohens_f",
    "planned_contrast": "cohens_f",
}
R_MODELS = {"two_sample_t", "welch_t", "paired_t", "one_way_anova", "linear_regression", "incremental_regression", "moderation", "correlation"}


def capabilities() -> dict:
    return {"schema_version": "1.0", "default_target_power": DEFAULT_TARGET_POWER, "methods": [
        {"model": model, "goals": ["required_sample_size"] + (["achieved_power", "sensitivity"] if model in FIXED_MODELS else []),
         "python": True, "r": model in R_MODELS, "webr": model in R_MODELS,
         "fixed_sample_limitation": None if model in FIXED_MODELS else "A validated fixed-sample inversion has not yet been implemented.",
         "webr_status": "validated_representative_cases_webr_0.6.0" if model in R_MODELS else "unavailable"}
        for model in get_args(Model)
    ]}
