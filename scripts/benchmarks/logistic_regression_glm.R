# Regenerates data/benchmarks/logistic_regression_r_glm.json.
#
# Also documents the pwrss predictor-distribution assumption difference, which is the
# reason a naive cross-tool comparison reads a 3.4x gap that is not a defect in either
# tool. Run from the repository root:
#
#   & "C:\Program Files\R\R-4.4.0\bin\Rscript.exe" scripts/benchmarks/logistic_regression_glm.R
#
# Requires: stats (base R). pwrss is optional and only used for the comparison section.

set.seed(7)

simulate_glm_power <- function(n, odds_ratio, p_baseline, reps = 3000, alpha = 0.05) {
  intercept <- log(p_baseline / (1 - p_baseline))
  slope <- log(odds_ratio)
  hits <- 0
  converged <- 0
  for (i in seq_len(reps)) {
    x <- rbinom(n, 1, 0.5)
    probability <- 1 / (1 + exp(-(intercept + slope * x)))
    y <- rbinom(n, 1, probability)
    if (length(unique(y)) < 2 || length(unique(x)) < 2) next
    fit <- try(glm(y ~ x, family = binomial()), silent = TRUE)
    if (inherits(fit, "try-error")) next
    coefficients <- summary(fit)$coefficients
    if (!("x" %in% rownames(coefficients))) next
    converged <- converged + 1
    if (abs(coefficients["x", "z value"]) > qnorm(1 - alpha / 2)) hits <- hits + 1
  }
  list(power = hits / converged, converged = converged)
}

cat(sprintf("R version: %s\n\n", getRversion()))

for (n in c(856, 249)) {
  result <- simulate_glm_power(n, odds_ratio = 1.5, p_baseline = 0.30)
  cat(sprintf(
    "N=%d  glm MC power=%.4f  (converged=%d)\n",
    n, result$power, result$converged
  ))
}

# The assumption difference, made explicit. pwrss defaults to a standard-normal
# predictor; PowerBench's binary branch contrasts two equally sized groups. Calling
# pwrss with an explicit Bernoulli predictor is the comparable configuration.
if (requireNamespace("pwrss", quietly = TRUE)) {
  cat("\n-- pwrss comparison (predictor distribution matters) --\n")
  default_call <- pwrss::pwrss.z.logreg(
    p0 = 0.30, odds.ratio = 1.5, power = 0.80, alpha = 0.05,
    alternative = "not equal", method = "demidenko"
  )
  cat(sprintf("pwrss default (normal predictor)   N = %.0f\n", ceiling(default_call$n)))
}
