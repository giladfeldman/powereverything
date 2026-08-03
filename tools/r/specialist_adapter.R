# R adapter for specialist methods: TOSTER (equivalence), metafor (random-effects
# meta-analysis), and MASS::polr (ordinal proportional odds).
#
# These are methods `pwr` and `pwrss` cannot reach, and three of them are paths where
# PowerBench's own formulas were wrong before 2026-08-03. An independent second opinion
# matters most exactly where the internal implementation was weakest.
#
# Each branch is called with assumptions matched to PowerBench's declared contract. Where
# a tool cannot be matched, the branch stops with a message rather than returning a number
# under different assumptions -- a forced comparison is worse than an honest decline.
#
# Usage: Rscript specialist_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: specialist_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("The specialist adapter requires jsonlite")

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
target_power <- scenario$target_power
alternative <- scenario$decision_rule$alternative

if (scenario$model == "tost_equivalence") {
  if (!requireNamespace("TOSTER", quietly = TRUE)) stop("tost_equivalence requires TOSTER")
  lower <- scenario$effect$lower_bound
  upper <- scenario$effect$upper_bound
  sd <- scenario$effect$sd
  true_difference <- if (is.null(scenario$effect$true_difference)) 0 else scenario$effect$true_difference
  if (abs(lower + upper) > 1e-9) stop("This adapter matches symmetric equivalence bounds only")

  # power_t_TOST solves for n per group given power. Bounds are on the raw mean
  # difference, matching PowerBench's parameterization.
  answer <- TOSTER::power_t_TOST(
    power = target_power,
    delta = true_difference,
    sd = sd,
    eqb = upper,
    alpha = alpha,
    type = "two.sample"
  )
  per_group <- ceiling(answer$n)
  result <- list(
    package = "TOSTER",
    package_version = as.character(utils::packageVersion("TOSTER")),
    assumptions = list(
      "two one-sided t tests on the raw mean difference",
      "symmetric equivalence bounds",
      "equal variances, balanced allocation"
    ),
    result = list(
      n1 = per_group, n2 = per_group, n_total = 2 * per_group,
      power = target_power,
      method = "TOSTER::power_t_TOST"
    )
  )
} else if (scenario$model == "meta_analysis_random") {
  if (!requireNamespace("metafor", quietly = TRUE)) stop("meta_analysis_random requires metafor")
  studies <- scenario$design$studies
  tau <- if (is.null(scenario$design$tau)) 0.2 else scenario$design$tau
  d <- scenario$effect$cohens_d
  if (studies <= 2) stop("Hartung-Knapp requires more than two studies")

  # metafor has no closed-form power solver, so this is a Monte Carlo evaluation of the
  # Hartung-Knapp test at increasing per-group N -- the same design PowerBench plans,
  # adjudicated by the reference implementation of the adjustment itself.
  set.seed(20260803)
  reps <- 400
  simulate_power <- function(n_per_group) {
    hits <- 0
    for (i in seq_len(reps)) {
      truths <- rnorm(studies, d, tau)
      yi <- numeric(studies); vi <- numeric(studies)
      for (j in seq_len(studies)) {
        control <- rnorm(n_per_group, 0, 1)
        treated <- rnorm(n_per_group, truths[j], 1)
        pooled <- sqrt(((n_per_group - 1) * var(control) + (n_per_group - 1) * var(treated)) /
                         (2 * n_per_group - 2))
        yi[j] <- (mean(treated) - mean(control)) / pooled
        vi[j] <- 2 / n_per_group + yi[j]^2 / (4 * n_per_group)
      }
      fit <- try(metafor::rma(yi = yi, vi = vi, method = "DL", tau2 = tau^2, test = "knha"),
                 silent = TRUE)
      if (inherits(fit, "try-error")) next
      if (fit$pval < alpha) hits <- hits + 1
    }
    hits / reps
  }

  # Bisection on per-group N. Monte Carlo makes this noisy, so the answer is reported
  # with its replication count and read as an interval, not a point.
  # Bracket by doubling from a small start: probing the top of a wide range first fits
  # hundreds of models at an N the answer never approaches.
  low <- 4; high <- 16
  while (simulate_power(high) < target_power) {
    low <- high; high <- high * 2
    if (high > 4096) stop("Target power unreachable within the search range")
  }
  while (high - low > 8) {
    mid <- floor((low + high) / 2)
    if (simulate_power(mid) < target_power) low <- mid else high <- mid
  }
  per_group <- high
  result <- list(
    package = "metafor",
    package_version = as.character(utils::packageVersion("metafor")),
    assumptions = list(
      "Hartung-Knapp adjusted random-effects summary",
      "tau2 fixed at the declared value, not estimated",
      "balanced two-arm studies",
      paste0("Monte Carlo power over ", reps, " replications; resolution is +/- 8 per group")
    ),
    result = list(
      n_per_group_per_study = per_group,
      n_total = per_group * 2 * studies,
      power = target_power,
      method = "metafor::rma(test='knha') Monte Carlo"
    )
  )
} else if (scenario$model == "ordinal_regression") {
  if (!requireNamespace("MASS", quietly = TRUE)) stop("ordinal_regression requires MASS")
  odds_ratio <- scenario$effect$odds_ratio
  categories <- scenario$design$categories

  # Monte Carlo over MASS::polr, the established proportional-odds fitter. The latent
  # data-generating process matches PowerBench's declared contract: a standard logistic
  # latent variable cut at equally spaced thresholds, with a balanced binary predictor.
  set.seed(20260803)
  reps <- 400
  cuts <- seq(-1, 1, length.out = categories - 1)
  beta <- log(odds_ratio)
  z_critical <- if (identical(alternative, "two.sided")) qnorm(1 - alpha / 2) else qnorm(1 - alpha)

  simulate_power <- function(n_total) {
    hits <- 0; converged <- 0
    for (i in seq_len(reps)) {
      x <- rbinom(n_total, 1, 0.5)
      latent <- beta * x + rlogis(n_total)
      y <- factor(findInterval(latent, cuts), levels = 0:(categories - 1), ordered = TRUE)
      if (length(unique(y)) < 2) next
      fit <- try(MASS::polr(y ~ x, method = "logistic", Hess = TRUE), silent = TRUE)
      if (inherits(fit, "try-error")) next
      coefficients <- try(summary(fit)$coefficients, silent = TRUE)
      if (inherits(coefficients, "try-error")) next
      converged <- converged + 1
      if (abs(coefficients["x", "t value"]) > z_critical) hits <- hits + 1
    }
    if (converged == 0) return(0)
    hits / converged
  }

  low <- 20; high <- 64
  while (simulate_power(high) < target_power) {
    low <- high; high <- high * 2
    if (high > 8192) stop("Target power unreachable within the search range")
  }
  while (high - low > 16) {
    mid <- floor((low + high) / 2)
    if (simulate_power(mid) < target_power) low <- mid else high <- mid
  }
  result <- list(
    package = "MASS",
    package_version = as.character(utils::packageVersion("MASS")),
    assumptions = list(
      "proportional-odds cumulative logit model",
      "balanced binary predictor",
      "standard logistic latent variable with equally spaced thresholds",
      paste0("Monte Carlo power over ", reps, " replications; resolution is +/- 16 total")
    ),
    result = list(
      n_total = high,
      power = target_power,
      method = "MASS::polr Monte Carlo"
    )
  )
} else {
  stop(paste("This specialist adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
