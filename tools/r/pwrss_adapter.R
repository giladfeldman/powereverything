# R `pwrss` adapter.
#
# pwrss covers the generalized-outcome methods that `pwr` cannot reach: logistic, Poisson
# and ordinal regression. Those are exactly the paths where PowerBench's own formulas were
# wrong before 2026-08-03, so an independent second opinion matters most here.
#
# IMPORTANT -- predictor distribution. `pwrss.z.logreg` defaults to `dist = "normal"`,
# which powers a one-SD change in a continuous predictor. PowerBench's binary branch powers
# a contrast between two equally sized groups. Those are different estimands: for
# OR = 1.5, p0 = 0.30 the normal default returns N = 249 while the balanced-binary design
# needs 856, and direct glm Monte Carlo confirms 0.31 power at N = 249.
#
# This adapter therefore passes an explicit Bernoulli(0.5) predictor so the two tools are
# answering the same question. Calling pwrss with its defaults and reporting the gap as a
# disagreement would be a comparison error, not a finding.
#
# Usage: Rscript pwrss_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: pwrss_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("pwrss", quietly = TRUE)) {
  stop("The pwrss adapter requires jsonlite and pwrss")
}

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
power <- scenario$target_power
alternative <- scenario$decision_rule$alternative
pwrss_alternative <- if (identical(alternative, "two.sided")) "not equal" else "greater"
version <- as.character(utils::packageVersion("pwrss"))

if (!identical(alternative, "two.sided")) {
  stop("This pwrss adapter supports two.sided scenarios only")
}

if (scenario$model == "logistic_regression") {
  predictor_type <- if (is.null(scenario$design$predictor_type)) "binary" else scenario$design$predictor_type
  if (!identical(predictor_type, "binary")) {
    stop("This pwrss adapter supports the balanced binary predictor contract only")
  }
  answer <- pwrss::pwrss.z.logreg(
    p0 = scenario$effect$p_baseline,
    odds.ratio = scenario$effect$odds_ratio,
    power = power,
    alpha = alpha,
    alternative = pwrss_alternative,
    method = "demidenko",
    # Matched to PowerBench: a balanced binary exposure, not the pwrss normal default.
    dist = list(dist = "bernoulli", prob = 0.5)
  )
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "balanced binary predictor, Bernoulli(0.5)",
      "Demidenko (2007) Wald z on the logistic slope",
      "asymptotic normal reference"
    ),
    result = list(
      n_total = ceiling(answer$n),
      power = power,
      method = "pwrss.z.logreg(method='demidenko', dist=bernoulli(0.5))"
    )
  )
} else if (scenario$model == "poisson_regression") {
  answer <- pwrss::pwrss.z.poisson(
    exp.beta0 = scenario$design$baseline_rate,
    exp.beta1 = scenario$effect$rate_ratio,
    power = power,
    alpha = alpha,
    alternative = pwrss_alternative,
    dist = list(dist = "bernoulli", prob = 0.5)
  )
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "balanced binary predictor, Bernoulli(0.5)",
      "Wald z on the log rate ratio",
      "asymptotic normal reference"
    ),
    result = list(
      n_total = ceiling(answer$n),
      power = power,
      method = "pwrss.z.poisson(dist=bernoulli(0.5))"
    )
  )
} else {
  stop(paste("This pwrss adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
