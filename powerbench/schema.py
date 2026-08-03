"""Canonical, intentionally strict scenario contract used by every adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Literal

Goal = Literal["required_sample_size", "achieved_power", "sensitivity"]
Model = Literal[
    "two_sample_t",
    "welch_t",
    "paired_t",
    "one_sample_proportion",
    "two_sample_proportion",
    "chi_square_gof",
    "chi_square_independence",
    "one_way_anova",
    "factorial_anova",
    "ancova",
    "planned_contrast",
    "linear_regression",
    "incremental_regression",
    "moderation",
    "logistic_regression",
    "poisson_regression",
    "correlation",
    "tost_equivalence",
    "mediation_indirect",
    "meta_analysis_fixed",
    "meta_analysis_random",
    "noninferiority_t",
    "ordinal_regression",
    "bayes_factor_t",
    "group_sequential_t",
    "logrank_two_arm",
    "rope_equivalence_t",
]
Framework = Literal["frequentist", "equivalence", "bayesian"]


@dataclass(frozen=True)
class DecisionRule:
    alpha: float = 0.05
    alternative: Literal["two.sided", "greater", "less"] = "two.sided"
    multiplicity_method: str = "none"

    def validate(self) -> None:
        if not 0 < self.alpha < 1:
            raise ValueError("decision_rule.alpha must lie strictly between 0 and 1")
        if self.alternative not in {"two.sided", "greater", "less"}:
            raise ValueError("alternative must be two.sided, greater, or less")
        if self.multiplicity_method not in {"none", "bonferroni", "hochberg"}:
            raise ValueError("multiplicity_method must be none, bonferroni, or hochberg")


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    framework: Framework
    goal: Goal
    model: Model
    target_power: float | None
    effect: dict[str, Any]
    design: dict[str, Any]
    decision_rule: DecisionRule = field(default_factory=DecisionRule)
    simulation: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    status: Literal["certification", "smoke", "draft"] = "draft"

    def validate(self) -> None:
        if not self.id or not self.title:
            raise ValueError("scenario id and title are required")
        self.decision_rule.validate()
        if self.goal == "required_sample_size" and not (self.target_power and 0 < self.target_power < 1):
            raise ValueError("required_sample_size scenarios need target_power in (0, 1)")
        if self.model == "two_sample_t":
            if "cohens_d" not in self.effect or self.effect["cohens_d"] == 0:
                raise ValueError("two_sample_t requires a non-zero cohens_d")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
        if self.model == "welch_t":
            difference = self.effect.get("mean_difference")
            sd1, sd2 = self.effect.get("sd_group1"), self.effect.get("sd_group2")
            if difference is None or difference == 0:
                raise ValueError("welch_t requires a non-zero raw mean_difference")
            if sd1 is None or sd2 is None or float(sd1) <= 0 or float(sd2) <= 0:
                raise ValueError("welch_t requires positive sd_group1 and sd_group2")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
            if self.design.get("equal_variance") is True:
                raise ValueError("welch_t must not declare equal_variance=true")
        if self.model == "paired_t" and ("cohens_dz" not in self.effect or self.effect["cohens_dz"] == 0):
            raise ValueError("paired_t requires a non-zero cohens_dz (standardized mean change)")
        if self.model == "one_sample_proportion":
            p0, p1 = self.effect.get("p_null"), self.effect.get("p_alternative")
            if p0 is None or p1 is None or not 0 < p0 < 1 or not 0 < p1 < 1 or p0 == p1:
                raise ValueError("one_sample_proportion requires distinct p_null and p_alternative in (0, 1)")
        if self.model == "two_sample_proportion":
            p1, p2 = self.effect.get("p_group1"), self.effect.get("p_group2")
            if p1 is None or p2 is None or not 0 < p1 < 1 or not 0 < p2 < 1 or p1 == p2:
                raise ValueError("two_sample_proportion requires distinct p_group1 and p_group2 in (0, 1)")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
        if self.model == "chi_square_gof":
            self._validate_probability_vectors("chi_square_gof")
            if int(self.design.get("categories", 0)) != len(self.effect["p_null"]) or float(self.design.get("min_expected_count", 5)) <= 0:
                raise ValueError("chi_square_gof requires matching categories and a positive min_expected_count")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("chi_square_gof uses an omnibus chi-square test and requires a two-sided decision rule")
        if self.model == "chi_square_independence":
            rows, cols = int(self.design.get("rows", 0)), int(self.design.get("cols", 0))
            if rows < 2 or cols < 2:
                raise ValueError("chi_square_independence requires at least a 2x2 table")
            joint = self.effect.get("joint_probabilities")
            if not isinstance(joint, list) or len(joint) != rows or any(not isinstance(row, list) or len(row) != cols for row in joint):
                raise ValueError("chi_square_independence requires a rows×cols joint_probabilities matrix")
            try:
                values = [float(cell) for row in joint for cell in row]
            except (TypeError, ValueError) as error:
                raise ValueError("chi_square_independence probabilities must be numeric") from error
            if any(value <= 0 or value >= 1 for value in values) or abs(sum(values) - 1) > 1e-10:
                raise ValueError("chi_square_independence joint probabilities must lie in (0,1) and sum to 1")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("chi_square_independence is an omnibus test and requires a two-sided decision rule")
        if self.model == "one_way_anova":
            if self.effect.get("cohens_f", 0) <= 0 or int(self.design.get("groups", 0)) < 2:
                raise ValueError("one_way_anova requires positive cohens_f and at least two groups")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("one_way_anova uses an omnibus F test and requires a two-sided decision rule")
        if self.model == "factorial_anova":
            if self.effect.get("cohens_f", 0) <= 0:
                raise ValueError("factorial_anova requires positive cohens_f for the tested term")
            levels_a, levels_b = int(self.design.get("levels_a", 0)), int(self.design.get("levels_b", 0))
            term = self.design.get("tested_term")
            if levels_a < 2 or levels_b < 2 or term not in {"A", "B", "AB"}:
                raise ValueError("factorial_anova requires levels_a/levels_b >= 2 and tested_term in {A,B,AB}")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("factorial_anova uses an F test and requires a two-sided decision rule")
        if self.model == "ancova":
            if self.effect.get("cohens_f", 0) <= 0:
                raise ValueError("ancova requires positive cohens_f for the adjusted treatment effect")
            if int(self.design.get("groups", 0)) < 2:
                raise ValueError("ancova requires at least two groups")
            r2 = float(self.design.get("covariate_r2", -1))
            if not 0 <= r2 < 1:
                raise ValueError("ancova requires covariate_r2 in [0, 1)")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("ancova uses an F test and requires a two-sided decision rule")
        if self.model == "planned_contrast":
            if self.effect.get("cohens_f", 0) <= 0:
                raise ValueError("planned_contrast requires positive cohens_f")
            weights = self.design.get("contrast_weights")
            groups = int(self.design.get("groups", 0))
            if not isinstance(weights, list) or groups < 2 or len(weights) != groups:
                raise ValueError("planned_contrast requires contrast_weights matching groups")
            try:
                numeric = [float(weight) for weight in weights]
            except (TypeError, ValueError) as error:
                raise ValueError("planned_contrast weights must be numeric") from error
            if abs(sum(numeric)) > 1e-10:
                raise ValueError("planned_contrast weights must sum to zero")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("planned_contrast currently supports a two-sided contrast F/t test")
        if self.model == "linear_regression":
            if self.effect.get("cohens_f2", 0) <= 0 or int(self.design.get("predictors", 0)) < 1:
                raise ValueError("linear_regression requires positive cohens_f2 and at least one predictor")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("linear_regression uses an omnibus F test and requires a two-sided decision rule")
        if self.model == "incremental_regression":
            total, tested = int(self.design.get("total_predictors", 0)), int(self.design.get("tested_predictors", 0))
            if self.effect.get("cohens_f2", 0) <= 0 or tested < 1 or total < tested:
                raise ValueError("incremental_regression requires positive cohens_f2 and valid tested/total predictor counts")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("incremental_regression uses an F test and requires a two-sided decision rule")
        if self.model == "moderation":
            if self.effect.get("cohens_f2", 0) <= 0:
                raise ValueError("moderation requires positive incremental cohens_f2 for the interaction")
            total = int(self.design.get("total_predictors", 0))
            if total < 3:
                raise ValueError("moderation requires total_predictors >= 3 (focal, moderator, interaction)")
            if self.decision_rule.alternative != "two.sided":
                raise ValueError("moderation uses an F test for the interaction and requires a two-sided decision rule")
        if self.model == "logistic_regression":
            odds_ratio = self.effect.get("odds_ratio")
            p0 = self.effect.get("p_baseline")
            if odds_ratio is None or float(odds_ratio) <= 0 or float(odds_ratio) == 1:
                raise ValueError("logistic_regression requires a positive odds_ratio different from 1")
            if p0 is None or not 0 < float(p0) < 1:
                raise ValueError("logistic_regression requires p_baseline in (0, 1)")
            if self.design.get("predictor_type", "binary") not in {"binary", "continuous"}:
                raise ValueError("logistic_regression predictor_type must be binary or continuous")
        if self.model == "poisson_regression":
            rate_ratio = self.effect.get("rate_ratio")
            if rate_ratio is None or float(rate_ratio) <= 0 or float(rate_ratio) == 1:
                raise ValueError("poisson_regression requires a positive rate_ratio different from 1")
            if float(self.design.get("baseline_rate", 0)) <= 0:
                raise ValueError("poisson_regression requires a positive baseline_rate (events per unit exposure)")
            if float(self.design.get("exposure", 1)) <= 0:
                raise ValueError("poisson_regression requires positive exposure")
        if self.model == "correlation":
            r = self.effect.get("rho")
            if r is None or not -1 < r < 1 or r == 0:
                raise ValueError("correlation requires a non-zero rho strictly between -1 and 1")
        if self.model == "tost_equivalence":
            if self.framework != "equivalence":
                raise ValueError("tost_equivalence requires framework='equivalence'")
            low, high = self.effect.get("lower_bound"), self.effect.get("upper_bound")
            if low is None or high is None or float(low) >= 0 or float(high) <= 0:
                raise ValueError("tost_equivalence requires lower_bound < 0 < upper_bound in raw mean units")
            if float(self.effect.get("true_difference", 1)) != 0:
                # Planning under exact equivalence at the null difference of zero is the default;
                # non-zero true differences are allowed for sensitivity but must be inside bounds.
                true_diff = float(self.effect["true_difference"])
                if not (float(low) < true_diff < float(high)):
                    raise ValueError("tost_equivalence true_difference must lie strictly inside the equivalence bounds")
            if float(self.effect.get("sd", 0)) <= 0:
                raise ValueError("tost_equivalence requires a positive common sd")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
        if self.model == "mediation_indirect":
            a, b = self.effect.get("a_path"), self.effect.get("b_path")
            if a is None or b is None or float(a) == 0 or float(b) == 0:
                raise ValueError("mediation_indirect requires non-zero a_path and b_path standardized coefficients")
            if float(self.design.get("residual_sd_m", 1)) <= 0 or float(self.design.get("residual_sd_y", 1)) <= 0:
                raise ValueError("mediation_indirect requires positive residual SDs")
        if self.model == "meta_analysis_fixed":
            if self.effect.get("cohens_d", 0) == 0:
                raise ValueError("meta_analysis_fixed requires a non-zero average cohens_d")
            if int(self.design.get("studies", 0)) < 2:
                raise ValueError("meta_analysis_fixed requires at least two studies")
            if int(self.design.get("n_per_group_per_study", 0)) < 2 and self.goal != "required_sample_size":
                raise ValueError("meta_analysis_fixed needs n_per_group_per_study for achieved-power checks")
        if self.model == "meta_analysis_random":
            if self.effect.get("cohens_d", 0) == 0:
                raise ValueError("meta_analysis_random requires a non-zero average cohens_d")
            if int(self.design.get("studies", 0)) < 2:
                raise ValueError("meta_analysis_random requires at least two studies")
            if float(self.design.get("tau", 0)) < 0:
                raise ValueError("meta_analysis_random requires tau >= 0 (between-study SD on the SMD scale)")
            if int(self.design.get("n_per_group_per_study", 0)) < 2 and self.goal != "required_sample_size":
                raise ValueError("meta_analysis_random needs n_per_group_per_study for achieved-power checks")
        if self.model == "noninferiority_t":
            if float(self.effect.get("margin", 0)) <= 0:
                raise ValueError("noninferiority_t requires a positive margin")
            if float(self.effect.get("sd", 0)) <= 0:
                raise ValueError("noninferiority_t requires a positive common sd")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
        if self.model == "ordinal_regression":
            odds_ratio = self.effect.get("odds_ratio")
            categories = int(self.design.get("categories", 0))
            if odds_ratio is None or float(odds_ratio) <= 0 or float(odds_ratio) == 1:
                raise ValueError("ordinal_regression requires a positive odds_ratio different from 1")
            if categories < 3:
                raise ValueError("ordinal_regression requires at least three ordered categories")
        if self.model == "bayes_factor_t":
            if self.framework != "bayesian":
                raise ValueError("bayes_factor_t requires framework='bayesian'")
            if self.effect.get("cohens_d", 0) == 0:
                raise ValueError("bayes_factor_t requires a non-zero cohens_d")
            if float(self.design.get("bf_threshold", 0)) <= 1:
                raise ValueError("bayes_factor_t requires bf_threshold > 1")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
            method = str(self.design.get("bf_method", "jzs")).lower()
            if method not in {"jzs", "bic"}:
                raise ValueError("bayes_factor_t bf_method must be 'jzs' or 'bic'")
            if float(self.design.get("r_scale", 0.7071)) <= 0:
                raise ValueError("bayes_factor_t r_scale must be positive")
        if self.model == "group_sequential_t":
            if self.effect.get("cohens_d", 0) == 0:
                raise ValueError("group_sequential_t requires a non-zero cohens_d")
            looks = int(self.design.get("looks", 0))
            if looks < 1 or looks > 5:
                raise ValueError("group_sequential_t supports 1-5 equally spaced looks")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
        if self.model == "logrank_two_arm":
            hr = self.effect.get("hazard_ratio")
            if hr is None or float(hr) <= 0 or float(hr) == 1:
                raise ValueError("logrank_two_arm requires hazard_ratio > 0 and != 1")
            p_event = self.effect.get("p_event")
            if p_event is None or not 0 < float(p_event) <= 1:
                raise ValueError("logrank_two_arm requires p_event in (0, 1]")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
            if float(self.design.get("accrual_years", 0.0)) < 0:
                raise ValueError("logrank_two_arm accrual_years must be >= 0")
            if float(self.design.get("followup_years", 0.0)) < 0:
                raise ValueError("logrank_two_arm followup_years must be >= 0")
            if float(self.design.get("dropout_hazard", 0.0)) < 0:
                raise ValueError("logrank_two_arm dropout_hazard must be >= 0")
        if self.model == "rope_equivalence_t":
            if self.framework != "bayesian":
                raise ValueError("rope_equivalence_t requires framework='bayesian'")
            low, high = self.effect.get("lower_bound"), self.effect.get("upper_bound")
            if low is None or high is None or float(low) >= float(high):
                raise ValueError("rope_equivalence_t requires lower_bound < upper_bound")
            if float(self.effect.get("sd", 0)) <= 0:
                raise ValueError("rope_equivalence_t requires a positive common sd")
            true_diff = float(self.effect.get("true_difference", 0.0))
            if not (float(low) < true_diff < float(high)):
                raise ValueError("rope_equivalence_t true_difference must lie strictly inside the ROPE")
            if self.design.get("allocation_ratio", 1.0) <= 0:
                raise ValueError("allocation_ratio must be positive")
            if float(self.design.get("prior_sd", 10.0)) <= 0:
                raise ValueError("rope_equivalence_t prior_sd must be positive")
            threshold = float(self.design.get("rope_threshold", 0.95))
            if not 0.5 < threshold < 1:
                raise ValueError("rope_equivalence_t rope_threshold must lie in (0.5, 1)")

    def _validate_probability_vectors(self, label: str) -> None:
        p_null, p_alternative = self.effect.get("p_null"), self.effect.get("p_alternative")
        if not isinstance(p_null, list) or not isinstance(p_alternative, list) or len(p_null) < 2 or len(p_null) != len(p_alternative):
            raise ValueError(f"{label} requires equally long p_null and p_alternative arrays with at least two categories")
        try:
            null_values, alternative_values = [float(value) for value in p_null], [float(value) for value in p_alternative]
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} probabilities must be numeric") from error
        if any(value <= 0 or value >= 1 for value in null_values + alternative_values):
            raise ValueError(f"{label} probabilities must lie strictly between 0 and 1")
        if abs(sum(null_values) - 1) > 1e-10 or abs(sum(alternative_values) - 1) > 1e-10 or null_values == alternative_values:
            raise ValueError(f"{label} probability arrays must each sum to 1 and differ")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_scenario(path: str | Path) -> Scenario:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rule = DecisionRule(**raw.pop("decision_rule", {}))
    scenario = Scenario(decision_rule=rule, **raw)
    scenario.validate()
    return scenario
