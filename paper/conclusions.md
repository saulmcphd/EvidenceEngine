---
type: paper-node
title: "Paper B (methods/validation) — Conclusions"
manuscript_section: conclusions
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Step 8)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Two subsections, no recommendations (present and interpret; do not tell reviewers
> what to do — playbook-write-up Step 8 / Guardrail "No recommendations"). Language is kept cautious throughout
> because the certainty is low (a single contamination-affected benchmark with approximated criteria).

# Conclusions

## Implications for the method

A local, provider-agnostic screening step in which a human completes the task, an AI repeats it independently, and the
two are compared appears feasible, and it can be run so that every decision carries provenance and the acceptance
verdict is reported honestly rather than self-certified. On this single contamination-aware benchmark the AI
second-screener's recall (.88, 95% CI [.80, .94]) is consistent with a useful recall-first pre-filter, but the
estimate is bounded by the lower confidence limit, by an approximated criteria set, by probable reference-label noise,
and by a memorization probe indicating that the model recognised the dataset—so it is best read as promising and
unproven rather than as evidence that the tool is a dependable second screener. That the pipeline flagged the run
"re-pilot" against its own default bar, rather than passing it, is itself a property worth noting: a screening tool
that declines to certify itself against an ungrounded threshold is behaving as a transparent-reporting instrument
should.

## Implications for research

The evaluation the design actually calls for has not yet been done and is the priority: a pre-registered,
blind-human-first validation on a fresh or in-progress review, in which one or more human reviewers record their
decisions before seeing any AI output and the reconciled human decision—not the AI's—is the review's data, so that the
reference standard is neither memorised nor circular. Such a study should fix the number of validation-relevant
records through a precision or assurance calculation and set the recall acceptance bar a priori and independently of
the tool developer, before any scoring. Beyond that single study, the estimate's generalisability is untested: recall
should be replicated across multiple models, across topics with less standardised vocabulary and higher proportions of
non-randomised studies, and across databases, and reported with design-stratified recall where study design has been
captured. Finally, the fatigue question central to the human-first rationale—whether human screening error rises with
time on task while the AI does not—requires its own adequately designed study, with at least several screeners,
randomised presentation order, and per-decision timestamps, none of which this benchmark provided.
