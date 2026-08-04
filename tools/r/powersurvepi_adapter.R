# R `powerSurvEpi` adapter: Welch unequal-variance t sample size.
#
# ssizeWelchT implements exactly PowerBench's Welch contract -- raw mean difference,
# separate group SDs, Satterthwaite degrees of freedom, two-sided noncentral t -- so it is
# a genuinely independent second opinion on the welch_t path (pwrss being the first).
#
# The package's survival functions (ssizeCT and relatives) use the Freedman formula
# parameterized by per-arm event probabilities pE and pC. The committed log-rank scenario
# declares only an OVERALL p_event, which does not determine pE and pC, so the survival
# branch is deliberately absent: an answer would require inventing assumptions the
# scenario does not state.
#
# Usage: Rscript powersurvepi_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: powersurvepi_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("powerSurvEpi", quietly = TRUE)) {
  stop("The powerSurvEpi adapter requires jsonlite and powerSurvEpi")
}

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
power <- scenario$target_power
alternative <- scenario$decision_rule$alternative
version <- as.character(utils::packageVersion("powerSurvEpi"))

if (!identical(alternative, "two.sided")) {
  stop("powerSurvEpi::ssizeWelchT is two-sided only")
}

if (scenario$model == "welch_t") {
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  answer <- powerSurvEpi::ssizeWelchT(
    ratioN2toN1 = ratio,
    meanDiff = scenario$effect$mean_difference,
    sd1 = scenario$effect$sd_group1,
    sd2 = scenario$effect$sd_group2,
    power = power, alpha = alpha
  )
  result <- list(
    package = "powerSurvEpi",
    package_version = version,
    assumptions = list(
      "raw mean difference with separate group SDs",
      "Satterthwaite degrees of freedom",
      "two-sided noncentral t"
    ),
    result = list(
      n1 = as.integer(answer$n1), n2 = as.integer(answer$n2),
      n_total = as.integer(answer$n1 + answer$n2),
      power = power,
      method = "powerSurvEpi::ssizeWelchT"
    )
  )
} else {
  stop(paste("This powerSurvEpi adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
