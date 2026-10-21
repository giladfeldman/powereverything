# R `rpact` adapter: group-sequential sample size for a two-sample t design.
#
# rpact is a validated clinical-trials package (used for regulatory submissions) and is
# fully independent of gsDesign, so the two together give the group-sequential scenario
# two external opinions that share no code. Unlike gsDesign's normal-based `nNormal`
# route, `getSampleSizeMeans` computes the t-test sample size, which is closer to
# PowerBench's exact-t fixed-design base.
#
# Usage: Rscript rpact_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: rpact_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("rpact", quietly = TRUE)) {
  stop("The rpact adapter requires jsonlite and rpact")
}

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
power <- scenario$target_power
alternative <- scenario$decision_rule$alternative
version <- as.character(utils::packageVersion("rpact"))

if (!identical(alternative, "two.sided")) {
  stop("This rpact adapter supports two.sided scenarios only")
}

if (scenario$model == "group_sequential_t") {
  looks <- if (is.null(scenario$design$looks)) 2 else scenario$design$looks
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  if (ratio != 1) stop("This rpact adapter supports balanced allocation only")

  design <- rpact::getDesignGroupSequential(
    kMax = looks, typeOfDesign = "asOF",
    alpha = alpha, sided = 2, beta = 1 - power
  )
  size <- rpact::getSampleSizeMeans(
    design,
    alternative = scenario$effect$cohens_d, stDev = 1,
    allocationRatioPlanned = 1
  )
  n_per_arm <- ceiling(size$maxNumberOfSubjects / 2)
  result <- list(
    package = "rpact",
    package_version = version,
    assumptions = list(
      "O'Brien-Fleming type alpha-spending (asOF), two-sided",
      "equally spaced looks, efficacy stopping only",
      "t-test sample size at the final analysis"
    ),
    result = list(
      n1 = n_per_arm, n2 = n_per_arm, n_total = 2 * n_per_arm,
      power = power,
      method = "rpact::getSampleSizeMeans(getDesignGroupSequential(typeOfDesign='asOF'))"
    )
  )
} else {
  stop(paste("This rpact adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
