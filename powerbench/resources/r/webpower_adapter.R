# R `WebPower` adapter: factorial ANOVA terms and simple mediation.
#
# wp.kanova powers one term of a multi-way ANOVA with the same noncentral-F convention
# PowerBench uses (error df = N - cells), so the factorial comparison is like-for-like.
#
# wp.mediation is DELIBERATELY a different test: it powers the SOBEL z on the product
# a*b, while PowerBench powers the joint-significance decision. Sobel is conservative, so
# WebPower's N is expected to be larger. That is declared as a test-variant difference on
# the Python side -- recording it as a disagreement would be a comparison error, and
# silently matching it would hide real information about how the two decision rules
# differ.
#
# Variance matching for mediation: wp.mediation takes TOTAL variances of x, m and y.
# PowerBench declares standardized paths with RESIDUAL SDs, so the adapter converts:
# var(m) = a^2 var(x) + sd_m_resid^2, and with c' = 0, var(y) = b^2 var(m) + sd_y_resid^2.
# Passing 1s (the naive call) powers a different design and returns 176 instead of 183
# for the committed scenario.
#
# Usage: Rscript webpower_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: webpower_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("WebPower", quietly = TRUE)) {
  stop("The WebPower adapter requires jsonlite and WebPower")
}

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
power <- scenario$target_power
alternative <- scenario$decision_rule$alternative
version <- as.character(utils::packageVersion("WebPower"))

if (!identical(alternative, "two.sided")) {
  stop("This WebPower adapter supports two.sided scenarios only")
}

if (scenario$model == "factorial_anova") {
  a <- scenario$design$levels_a
  b <- scenario$design$levels_b
  term <- scenario$design$tested_term
  ndf <- switch(term,
    "A" = a - 1,
    "B" = b - 1,
    "AB" = (a - 1) * (b - 1),
    stop(paste("Unknown tested term", term))
  )
  answer <- WebPower::wp.kanova(
    ndf = ndf, f = scenario$effect$cohens_f, ng = a * b,
    alpha = alpha, power = power
  )
  result <- list(
    package = "WebPower",
    package_version = version,
    assumptions = list(
      "balanced cells",
      "noncentral F for the tested term",
      "error df = N - cells"
    ),
    result = list(
      n_total = as.integer(ceiling(answer$n)),
      power = power,
      method = sprintf("WebPower::wp.kanova(ndf=%d, ng=%d)", ndf, a * b)
    )
  )
} else if (scenario$model == "mediation_indirect") {
  cprime <- if (is.null(scenario$effect$direct_cprime)) 0 else scenario$effect$direct_cprime
  if (abs(cprime) > 1e-12) {
    stop("This WebPower adapter matches the c' = 0 contract only; a direct path changes var(y)")
  }
  a_path <- scenario$effect$a_path
  b_path <- scenario$effect$b_path
  sd_m <- if (is.null(scenario$design$residual_sd_m)) 1 else scenario$design$residual_sd_m
  sd_y <- if (is.null(scenario$design$residual_sd_y)) 1 else scenario$design$residual_sd_y
  var_x <- 1
  var_m <- a_path^2 * var_x + sd_m^2
  var_y <- b_path^2 * var_m + sd_y^2
  answer <- WebPower::wp.mediation(
    power = power, a = a_path, b = b_path,
    varx = var_x, varm = var_m, vary = var_y, alpha = alpha
  )
  result <- list(
    package = "WebPower",
    package_version = version,
    assumptions = list(
      "Sobel z test on the product a*b (NOT joint significance)",
      "total variances derived from PowerBench's standardized paths and residual SDs",
      "no direct path (c' = 0)"
    ),
    result = list(
      n_total = as.integer(ceiling(answer$n)),
      power = power,
      method = "WebPower::wp.mediation (Sobel)"
    )
  )
} else {
  stop(paste("This WebPower adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
