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

# noninferiority_t is inherently one-sided (the scenario declares alternative
# "greater"); every other branch is restricted to two.sided.
if (!identical(alternative, "two.sided") && !identical(scenario$model, "noninferiority_t")) {
  stop("This pwrss adapter supports two.sided scenarios only")
}

if (scenario$model == "logistic_regression") {
  predictor_type <- if (is.null(scenario$design$predictor_type)) "binary" else scenario$design$predictor_type
  if (!identical(predictor_type, "binary")) {
    stop("This pwrss adapter supports the binary predictor contract only")
  }
  # Matched to PowerBench: a binary exposure at the scenario's allocation fractions
  # (exposed fraction = ratio / (1 + ratio); 0.5 when balanced), never the pwrss normal
  # default. Verified at ratio = 1.5: both tools return 903.
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  answer <- pwrss::pwrss.z.logreg(
    p0 = scenario$effect$p_baseline,
    odds.ratio = scenario$effect$odds_ratio,
    power = power,
    alpha = alpha,
    alternative = pwrss_alternative,
    method = "demidenko",
    dist = list(dist = "bernoulli", prob = ratio / (1 + ratio))
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
  # PowerBench multiplies both arms' rates by the scenario's exposure (default 1), so it
  # must be passed through -- dropping it would compare different rate scales whenever a
  # scenario declares exposure != 1. Verified at exposure = 2: pwrss 394 vs PowerBench
  # 398, the same ~1% approximation gap the exposure = 1 comparison already shows.
  exposure <- if (is.null(scenario$design$exposure)) 1 else scenario$design$exposure
  answer <- pwrss::pwrss.z.poisson(
    exp.beta0 = scenario$design$baseline_rate,
    exp.beta1 = scenario$effect$rate_ratio,
    mean.exposure = exposure,
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
} else if (scenario$model == "two_sample_t") {
  # kappa is n1/n2 in pwrss; the scenario's allocation_ratio is n2/n1. pwrss 1.0.0
  # FORCES welch.df = TRUE for unbalanced designs (a warning says so), so the degrees of
  # freedom are Welch-Satterthwaite even with equal declared SDs. With sd1 = sd2 the
  # noncentrality is identical to the pooled test, and the returned sample sizes match
  # the exact pooled noncentral t for every committed scenario; the df convention is
  # declared on the Python side so any residual gap is attributed, not hidden.
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  answer <- pwrss::pwrss.t.2means(
    mu1 = scenario$effect$cohens_d, mu2 = 0, sd1 = 1, sd2 = 1,
    kappa = 1 / ratio, power = power, alpha = alpha,
    alternative = pwrss_alternative, verbose = FALSE
  )
  n1 <- as.integer(answer$n[[1]]); n2 <- as.integer(answer$n[[2]])
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "Cohen's d with equal declared group SDs",
      "Welch-Satterthwaite degrees of freedom (forced by pwrss for unbalanced designs)",
      "noncentral t"
    ),
    result = list(
      n1 = n1, n2 = n2, n_total = n1 + n2,
      power = answer$power,
      method = "pwrss.t.2means"
    )
  )
} else if (scenario$model == "welch_t") {
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  answer <- pwrss::pwrss.t.2means(
    mu1 = scenario$effect$mean_difference, mu2 = 0,
    sd1 = scenario$effect$sd_group1, sd2 = scenario$effect$sd_group2,
    kappa = 1 / ratio, power = power, alpha = alpha,
    alternative = pwrss_alternative, verbose = FALSE
  )
  n1 <- as.integer(answer$n[[1]]); n2 <- as.integer(answer$n[[2]])
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "raw mean difference with separate group SDs",
      "Welch-Satterthwaite degrees of freedom",
      "noncentral t"
    ),
    result = list(
      n1 = n1, n2 = n2, n_total = n1 + n2,
      power = answer$power,
      method = "pwrss.t.2means (Welch)"
    )
  )
} else if (scenario$model == "noninferiority_t") {
  # pwrss expresses non-inferiority as a NEGATIVE margin when higher outcomes are
  # better: H0 d <= margin vs H1 d > margin, which matches PowerBench's
  # one-sided test against -margin. kappa carries the allocation ratio -- omitting it
  # would return balanced arms for an unbalanced design. Verified at ratio = 1.5:
  # both tools return 42/63 = 105.
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  answer <- pwrss::pwrss.t.2means(
    mu1 = scenario$effect$true_difference, mu2 = 0,
    sd1 = scenario$effect$sd, sd2 = scenario$effect$sd,
    kappa = 1 / ratio,
    margin = -scenario$effect$margin, power = power, alpha = alpha,
    alternative = "non-inferior", verbose = FALSE
  )
  n1 <- as.integer(answer$n[[1]]); n2 <- as.integer(answer$n[[2]])
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "one-sided non-inferiority against a raw-scale margin",
      "common SD, balanced allocation",
      "t reference with noncentrality under the null margin"
    ),
    result = list(
      n1 = n1, n2 = n2, n_total = n1 + n2,
      power = answer$power,
      method = "pwrss.t.2means(alternative='non-inferior')"
    )
  )
} else if (scenario$model == "ancova") {
  # PowerBench's f is adjusted for the covariate: f_adj = f / sqrt(1 - R^2). pwrss
  # takes (partial) eta-squared, so the adapter converts the ADJUSTED f2 -- passing the
  # unadjusted effect returns N = 200 instead of 150 for the committed scenario, a
  # parameterization mismatch, not a disagreement.
  f2_adjusted <- scenario$effect$cohens_f^2 / (1 - scenario$design$covariate_r2)
  answer <- pwrss::pwrss.f.ancova(
    eta2 = f2_adjusted / (1 + f2_adjusted),
    n.levels = scenario$design$groups, n.cov = 1,
    power = power, alpha = alpha, verbose = FALSE
  )
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "one treatment factor with one covariate",
      "eta-squared converted from the covariate-adjusted Cohen f",
      "noncentral F with df2 = N - groups - 1"
    ),
    result = list(
      n_total = as.integer(answer$n.total),
      power = answer$power,
      method = "pwrss.f.ancova(eta2 from adjusted f2)"
    )
  )
} else if (scenario$model == "planned_contrast") {
  # The cell means realize PowerBench's declared contract mu_j = w_j / rms(w) * f, so
  # the contrast's standardized effect is exactly f. pwrss tests the contrast with a
  # t statistic (identical to F with one numerator df) but insists on k.covariates >= 1,
  # so its error df is N - groups - 1 rather than PowerBench's N - groups; declared on
  # the Python side.
  weights <- as.numeric(unlist(scenario$design$contrast_weights))
  groups <- scenario$design$groups
  mu <- weights / sqrt(mean(weights^2)) * scenario$effect$cohens_f
  answer <- pwrss::power.t.contrast(
    mu.vector = mu, sd.vector = rep(1, groups), contrast.vector = weights,
    p.vector = rep(1 / groups, groups),
    power = power, alpha = alpha, verbose = FALSE
  )
  result <- list(
    package = "pwrss",
    package_version = version,
    assumptions = list(
      "single pre-specified contrast, balanced groups",
      "cell means placed at w_j / rms(w) * f, matching the PowerBench contract",
      "t test on the contrast; error df = N - groups - 1 (pwrss requires one covariate slot)"
    ),
    result = list(
      n_total = as.integer(answer$n.total),
      power = answer$power,
      method = "pwrss::power.t.contrast"
    )
  )
} else {
  stop(paste("This pwrss adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
