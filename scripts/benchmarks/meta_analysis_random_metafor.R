# Regenerates data/benchmarks/meta_analysis_random_r_metafor.json.
#
# metafor is the reference implementation of the Hartung-Knapp adjustment, so it is the
# right adjudicator for the random-effects planning path. Run from the repository root:
#
#   & "C:\Program Files\R\R-4.4.0\bin\Rscript.exe" scripts/benchmarks/meta_analysis_random_metafor.R
#
# Requires: metafor.

suppressMessages(library(metafor))

set.seed(11)

studies <- 6
tau <- 0.2
true_d <- 0.3
n_per_group <- 542
replications <- 400

hits_hk <- 0
hits_unadjusted <- 0
se_hk <- numeric(replications)
se_unadjusted <- numeric(replications)

for (i in seq_len(replications)) {
  study_truths <- rnorm(studies, true_d, tau)
  yi <- numeric(studies)
  vi <- numeric(studies)
  for (j in seq_len(studies)) {
    control <- rnorm(n_per_group, 0, 1)
    treated <- rnorm(n_per_group, study_truths[j], 1)
    pooled <- sqrt(((n_per_group - 1) * var(control) + (n_per_group - 1) * var(treated)) /
                     (2 * n_per_group - 2))
    yi[j] <- (mean(treated) - mean(control)) / pooled
    vi[j] <- 2 / n_per_group + yi[j]^2 / (4 * n_per_group)
  }

  # tau^2 is held at its known value, matching the PowerBench planning contract, which
  # treats between-study heterogeneity as a declared design assumption rather than an
  # estimated quantity.
  fit_hk <- rma(yi = yi, vi = vi, method = "DL", tau2 = tau^2, test = "knha")
  fit_unadjusted <- rma(yi = yi, vi = vi, method = "DL", tau2 = tau^2)

  se_hk[i] <- fit_hk$se
  se_unadjusted[i] <- fit_unadjusted$se
  if (fit_hk$pval < 0.05) hits_hk <- hits_hk + 1
  if (fit_unadjusted$pval < 0.05) hits_unadjusted <- hits_unadjusted + 1
}

cat(sprintf("R version: %s\n", getRversion()))
cat(sprintf("metafor version: %s\n\n", packageVersion("metafor")))
cat(sprintf("metafor knha  : power=%.4f  mean SE=%.5f\n", hits_hk / replications, mean(se_hk)))
cat(sprintf("metafor plain : power=%.4f  mean SE=%.5f\n",
            hits_unadjusted / replications, mean(se_unadjusted)))
