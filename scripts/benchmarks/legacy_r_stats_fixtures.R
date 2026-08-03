# Regenerates data/benchmarks/welch_t_r_stats.json and
# data/benchmarks/chi_square_gof_r_stats.json.
#
# Both fixtures predate this script and shipped with only a `source` string, so their
# values could not be re-derived by a reviewer (see PM-010 in project lessons). This
# reproduces them from base R's distribution functions, independently of SciPy.
#
# Run from the repository root:
#
#   & "C:\Program Files\R\R-4.4.0\bin\Rscript.exe" scripts/benchmarks/legacy_r_stats_fixtures.R
#
# Requires: stats (base R) only.

cat(sprintf("R version: %s\n\n", getRversion()))

# --- Welch-Satterthwaite noncentral-t planning approximation -------------------------

welch_power <- function(n1, n2, mean_difference, sd_group1, sd_group2, alpha, alternative) {
  variance <- sd_group1^2 / n1 + sd_group2^2 / n2
  df <- variance^2 / ((sd_group1^2 / n1)^2 / (n1 - 1) + (sd_group2^2 / n2)^2 / (n2 - 1))
  ncp <- mean_difference / sqrt(variance)
  if (alternative == "two.sided") {
    critical <- qt(1 - alpha / 2, df)
    power <- pt(-critical, df, ncp) + pt(critical, df, ncp, lower.tail = FALSE)
  } else {
    critical <- qt(1 - alpha, df)
    power <- pt(critical, df, ncp, lower.tail = FALSE)
  }
  list(power = power, satterthwaite_df = df)
}

cat("-- welch_t_r_stats.json --\n")
welch_cases <- list(
  list(id = "unbalanced_sd_1_2_target_80",
       n1 = 116, n2 = 174, mean_difference = 0.5,
       sd_group1 = 1.0, sd_group2 = 2.0, alpha = 0.05, alternative = "two.sided"),
  list(id = "unequal_sd_1_3_adjusted_alpha",
       n1 = 60, n2 = 120, mean_difference = 0.5,
       sd_group1 = 1.0, sd_group2 = 3.0, alpha = 0.025, alternative = "two.sided")
)
for (case in welch_cases) {
  result <- welch_power(case$n1, case$n2, case$mean_difference,
                        case$sd_group1, case$sd_group2, case$alpha, case$alternative)
  cat(sprintf("%s\n  power            = %.15f\n  satterthwaite_df = %.15f\n",
              case$id, result$power, result$satterthwaite_df))
}

# --- Cohen's w and noncentral chi-square goodness-of-fit -----------------------------

cohens_w <- function(p_null, p_alternative) {
  sqrt(sum((p_alternative - p_null)^2 / p_null))
}

chi_square_gof_power <- function(n, p_null, p_alternative, alpha) {
  w <- cohens_w(p_null, p_alternative)
  df <- length(p_null) - 1
  critical <- qchisq(1 - alpha, df)
  pchisq(critical, df, ncp = n * w^2, lower.tail = FALSE)
}

cat("\n-- chi_square_gof_r_stats.json --\n")
p_null <- c(0.5, 0.3, 0.2)
p_alternative <- c(0.4, 0.4, 0.2)
cat(sprintf("three_category_w_0231_target_80\n  cohens_w = %.16f\n  power    = %.16f\n",
            cohens_w(p_null, p_alternative),
            chi_square_gof_power(181, p_null, p_alternative, 0.05)))
