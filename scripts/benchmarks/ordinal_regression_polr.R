# Regenerates data/benchmarks/ordinal_regression_r_polr.json.
#
# Committing the generator alongside the fixture is deliberate: a fixture whose
# provenance is only a `source` string cannot be re-derived by a reviewer, which is the
# same trust problem as an uncited number. Run from the repository root:
#
#   & "C:\Program Files\R\R-4.4.0\bin\Rscript.exe" scripts/benchmarks/ordinal_regression_polr.R
#
# Requires: MASS (ships with R).

suppressMessages(library(MASS))

set.seed(20260803)

simulate_polr_power <- function(n, odds_ratio, categories, reps = 3000, alpha = 0.05) {
  cuts <- seq(-1, 1, length.out = categories - 1)
  beta <- log(odds_ratio)
  hits <- 0
  converged <- 0
  for (i in seq_len(reps)) {
    x <- rbinom(n, 1, 0.5)
    latent <- beta * x + rlogis(n)
    y <- factor(findInterval(latent, cuts), levels = 0:(categories - 1), ordered = TRUE)
    if (length(unique(y)) < 2) next
    fit <- try(polr(y ~ x, method = "logistic", Hess = TRUE), silent = TRUE)
    if (inherits(fit, "try-error")) next
    coefficients <- try(summary(fit)$coefficients, silent = TRUE)
    if (inherits(coefficients, "try-error")) next
    converged <- converged + 1
    if (abs(coefficients["x", "t value"]) > qnorm(1 - alpha / 2)) hits <- hits + 1
  }
  list(power = hits / converged, converged = converged)
}

cat(sprintf("R version: %s\n", getRversion()))
cat(sprintf("MASS version: %s\n\n", packageVersion("MASS")))

for (n in c(191, 614)) {
  result <- simulate_polr_power(n, odds_ratio = 1.5, categories = 4)
  cat(sprintf(
    "N=%d  MASS::polr power=%.4f  (converged=%d)\n",
    n, result$power, result$converged
  ))
}
