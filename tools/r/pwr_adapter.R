args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: pwr_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("pwr", quietly = TRUE)) stop("The R adapter requires jsonlite and pwr")
scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
if (scenario$decision_rule$alternative != "two.sided") stop("This initial pwr adapter supports two.sided scenarios only")

if (scenario$model == "two_sample_t") {
  answer <- pwr::pwr.t.test(d = scenario$effect$cohens_d, sig.level = scenario$decision_rule$alpha, power = scenario$target_power, type = "two.sample", alternative = "two.sided")
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("balanced allocation", "pooled-variance two-sample t-test", "noncentral t"), result = list(n1 = n, n2 = n, n_total = 2 * n, power = answer$power, method = "pwr.t.test"))
} else if (scenario$model == "paired_t") {
  answer <- pwr::pwr.t.test(d = scenario$effect$cohens_dz, sig.level = scenario$decision_rule$alpha, power = scenario$target_power, type = "paired", alternative = "two.sided")
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("paired standardized change dz", "noncentral t"), result = list(n_total = n, power = answer$power, method = "pwr.t.test paired"))
} else if (scenario$model == "chi_square_gof") {
  p_null <- as.numeric(unlist(scenario$effect$p_null))
  p_alternative <- as.numeric(unlist(scenario$effect$p_alternative))
  w <- sqrt(sum((p_alternative - p_null)^2 / p_null))
  answer <- pwr::pwr.chisq.test(w = w, df = length(p_null) - 1, sig.level = scenario$decision_rule$alpha, power = scenario$target_power)
  n <- ceiling(answer$N)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("multinomial goodness-of-fit", "Pearson chi-square", "noncentral chi-square approximation", "asymptotically adequate expected null counts"), result = list(n_total = n, power = answer$power, cohens_w = w, method = "pwr.chisq.test"))
} else if (scenario$model == "one_way_anova") {
  answer <- pwr::pwr.anova.test(k = scenario$design$groups, f = scenario$effect$cohens_f, sig.level = scenario$decision_rule$alpha, power = scenario$target_power)
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("balanced groups", "omnibus F test", "noncentral F"), result = list(n_per_group = n, n_total = n * scenario$design$groups, power = answer$power, method = "pwr.anova.test"))
} else if (scenario$model == "linear_regression") {
  answer <- pwr::pwr.f2.test(u = scenario$design$predictors, f2 = scenario$effect$cohens_f2, sig.level = scenario$decision_rule$alpha, power = scenario$target_power)
  n <- ceiling(answer$u + answer$v + 1)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("overall regression F test", "Cohen f2", "noncentral F"), result = list(n_total = n, power = answer$power, method = "pwr.f2.test"))
} else if (scenario$model == "incremental_regression") {
  answer <- pwr::pwr.f2.test(u = scenario$design$tested_predictors, f2 = scenario$effect$cohens_f2, sig.level = scenario$decision_rule$alpha, power = scenario$target_power)
  n <- ceiling(scenario$design$total_predictors + answer$v + 1)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("tested predictor block", "Cohen f2", "noncentral F"), result = list(n_total = n, power = answer$power, method = "pwr.f2.test incremental block"))
} else if (scenario$model == "correlation") {
  answer <- pwr::pwr.r.test(r = scenario$effect$rho, sig.level = scenario$decision_rule$alpha, power = scenario$target_power, alternative = "two.sided")
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("Fisher-z approximation", "Pearson correlation"), result = list(n_total = n, power = answer$power, method = "pwr.r.test"))
} else if (scenario$model == "one_sample_proportion") {
  # pwr uses Cohen's arcsine h with a NORMAL approximation. PowerBench uses an
  # exact binomial rejection region, so a gap here is an expected method
  # difference, not a defect (see parameterization notes on the Python side).
  h <- pwr::ES.h(scenario$effect$p_alternative, scenario$effect$p_null)
  answer <- pwr::pwr.p.test(h = h, sig.level = scenario$decision_rule$alpha, power = scenario$target_power, alternative = "two.sided")
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("Cohen arcsine effect size h", "normal approximation", "no exact binomial correction"), result = list(n_total = n, power = answer$power, cohens_h = h, method = "pwr.p.test"))
} else if (scenario$model == "two_sample_proportion") {
  # pwr.2p.test is balanced-only; the adapter refuses unbalanced designs on the
  # Python side rather than silently reporting a balanced answer for one.
  #
  # ES.h is ANTISYMMETRIC: ES.h(p1,p2) == -ES.h(p2,p1). Here that is harmless because
  # pwr squares h for a two-sided test -- verified, both signs give n_total = 186 for
  # p1=.30, p2=.50. It would NOT be harmless one-sided: `pwr.2p.test(h = <negative>,
  # alternative = "greater")` dies inside uniroot with "f() values at end points not of
  # opposite sign". Both this script (line 5) and the Python `supports()` restrict the
  # adapter to two.sided, so the crash is unreachable today. Anyone lifting that
  # restriction must pass abs(h) with the direction supplied via `alternative`.
  h <- pwr::ES.h(scenario$effect$p_group1, scenario$effect$p_group2)
  answer <- pwr::pwr.2p.test(h = h, sig.level = scenario$decision_rule$alpha, power = scenario$target_power, alternative = "two.sided")
  n <- ceiling(answer$n)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("Cohen arcsine effect size h", "balanced allocation", "normal approximation"), result = list(n1 = n, n2 = n, n_total = 2 * n, power = answer$power, cohens_h = h, method = "pwr.2p.test"))
} else if (scenario$model == "chi_square_independence") {
  # ES.w2 takes the JOINT cell probability matrix and derives w from the
  # implied marginals, which is exactly the parameterization the scenario uses.
  joint <- scenario$effect$joint_probabilities
  P <- do.call(rbind, lapply(joint, function(row) as.numeric(unlist(row))))
  w <- pwr::ES.w2(P)
  df <- (nrow(P) - 1) * (ncol(P) - 1)
  answer <- pwr::pwr.chisq.test(w = w, df = df, sig.level = scenario$decision_rule$alpha, power = scenario$target_power)
  n <- ceiling(answer$N)
  result <- list(package = "pwr", package_version = as.character(utils::packageVersion("pwr")), assumptions = list("Pearson chi-square test of independence", "noncentral chi-square approximation", "no minimum expected cell count enforced"), result = list(n_total = n, power = answer$power, cohens_w = w, df = df, method = "pwr.chisq.test"))
} else stop(sprintf("Unsupported model: %s", scenario$model))
jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, pretty = TRUE)
