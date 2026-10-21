# R `gsDesign` adapter: group-sequential designs and log-rank required events.
#
# gsDesign (Keaveney/Anderson, Merck) is the established reference implementation for
# group-sequential boundary computation, and its `nEvents` is a direct implementation of
# the Schoenfeld required-events formula -- the same formula PowerBench declares for the
# two-arm log-rank scenario.
#
# Group-sequential caveat, declared rather than hidden: gsDesign inflates a FIXED-design
# sample size that comes from the asymptotic normal test (`nNormal`), while PowerBench
# inflates the exact fixed-design t. Both then apply Lan-DeMets O'Brien-Fleming spending,
# so the answers differ by the normal-vs-t base (a few observations), not by the
# sequential machinery.
#
# Usage: Rscript gsdesign_adapter.R scenario.json output.json

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("Usage: gsdesign_adapter.R scenario.json output.json")
if (!requireNamespace("jsonlite", quietly = TRUE) || !requireNamespace("gsDesign", quietly = TRUE)) {
  stop("The gsDesign adapter requires jsonlite and gsDesign")
}

scenario <- jsonlite::fromJSON(args[[1]], simplifyVector = FALSE)
alpha <- scenario$decision_rule$alpha
power <- scenario$target_power
alternative <- scenario$decision_rule$alternative
version <- as.character(utils::packageVersion("gsDesign"))

if (!identical(alternative, "two.sided")) {
  stop("This gsDesign adapter supports two.sided scenarios only")
}

if (scenario$model == "group_sequential_t") {
  looks <- if (is.null(scenario$design$looks)) 2 else scenario$design$looks
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  if (ratio != 1) stop("This gsDesign adapter supports balanced allocation only")
  d <- scenario$effect$cohens_d

  # Two-sided alpha via a symmetric design (test.type = 2) at alpha / 2 per side.
  n_fixed <- gsDesign::nNormal(delta1 = d, sd = 1, alpha = alpha / 2, beta = 1 - power, ratio = 1)
  design <- gsDesign::gsDesign(
    k = looks, test.type = 2, alpha = alpha / 2, beta = 1 - power,
    sfu = gsDesign::sfLDOF, n.fix = n_fixed
  )
  n_per_arm <- ceiling(design$n.I[[looks]] / 2)
  result <- list(
    package = "gsDesign",
    package_version = version,
    assumptions = list(
      "Lan-DeMets O'Brien-Fleming alpha spending, symmetric two-sided efficacy bounds",
      "equally spaced looks",
      "fixed-design base is the asymptotic normal sample size (nNormal), not the exact t"
    ),
    result = list(
      n1 = n_per_arm, n2 = n_per_arm, n_total = 2 * n_per_arm,
      power = power,
      inflation_factor = design$n.I[[looks]] / n_fixed,
      method = "gsDesign::gsDesign(test.type=2, sfu=sfLDOF) on nNormal"
    )
  )
} else if (scenario$model == "logrank_two_arm") {
  if (is.null(scenario$effect$p_event)) {
    stop("This gsDesign adapter requires a supplied p_event; derived event probabilities are not matched")
  }
  ratio <- if (is.null(scenario$design$allocation_ratio)) 1 else scenario$design$allocation_ratio
  events <- gsDesign::nEvents(
    hr = scenario$effect$hazard_ratio,
    alpha = alpha / 2, beta = 1 - power, ratio = ratio
  )
  # N = ceil(events / p_event) mirrors PowerBench's declared convention; the tool's own
  # answer is the required event count, reported alongside.
  n_total <- ceiling(events / scenario$effect$p_event)
  result <- list(
    package = "gsDesign",
    package_version = version,
    assumptions = list(
      "Schoenfeld required-events formula under proportional hazards",
      "two-sided alpha via alpha/2 per side",
      "N = ceiling(events / p_event) applied by the adapter, mirroring the scenario's stated convention"
    ),
    result = list(
      n_total = as.integer(n_total),
      required_events = events,
      power = power,
      method = "gsDesign::nEvents / p_event"
    )
  )
} else {
  stop(paste("This gsDesign adapter does not cover model", scenario$model))
}

jsonlite::write_json(result, args[[2]], auto_unbox = TRUE, digits = 15)
