---
type: paper-node
title: "Paper B (methods/validation) — Discussion"
manuscript_section: discussion
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Steps 6–7)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Structured for a methods/validation paper (the five clinical-review Discussion
> subheadings are adapted, since there are no clinical outcomes). Every Discussion sentence was checked against the
> overinterpretation guardrails: interpret the confidence interval and its width rather than a pass/fail threshold,
> and do not read "did not clear the bar" as "unfit" (playbook-write-up Step 7).

# Discussion

## Summary of the main finding

On a single benchmark, the AI title/abstract second-screener retained 69 of 78 reference-relevant records, a recall
of .88 (95% CI [.80, .94]). The interval is the more informative object than the point estimate: it indicates that,
even in this favourable setting, the true miss rate could plausibly be as high as one in five relevant records, or as
low as one in sixteen. A screening pre-filter is only as safe as its worst plausible recall, so the lower bound—not
the .88—is the quantity that should govern any claim of usefulness. The error analysis materially softens the raw
count of nine misses: five of the nine records were in fact included in the source review's final set, and these
divided into three that our approximated population criterion excluded despite being pharmacokinetic studies of the
review's own drugs, and two that the source labelled relevant but that are, on inspection, off topic for a
urinary-incontinence drug review. The remaining four aligned with the source review's eventual full-text exclusions.
The screener's behaviour was therefore closer to defensible than the headline nine-miss count suggests, but this
reading depends on the two reference-standard qualifications discussed below and does not license a stronger claim
than "promising and worth a properly designed test".

## Strengths of the evaluation

The evaluation's principal strength is that it confronts the two threats to a validation of this kind rather than
assuming them away. Contamination was measured, not hoped against: the memorization probe was run and recorded before
any scoring, and its finding—recognition of the dataset but not of the specific inclusion decisions—lets the recall be
read as a possibly-inflated upper bound with a stated reason, rather than as a clean result. The analysis was
recall-first throughout, so the low precision (.29) is reported as the intended cost of a pre-filter rather than
disguised by a misleading composite such as accuracy or *F*1. The acceptance gate was reported honestly as the tool's
default rather than dressed as an a-priori criterion, and the whole run left a provenance-stamped, auditable record.
These are the reporting behaviours the governing guidance asks for, and they are built into the pipeline rather than
applied after the fact.

## Limitations and potential biases of the evaluation

The limitations are substantial and bound every claim. First and most important, the reference standard was a
published review's own labels, not the blind, independent decisions of a fresh human reviewer, which is the reference
the pipeline is actually designed to be graded against; a published-review benchmark is both weaker and
contamination-prone, and it left the reconciliation and human-oversight step—the core of the human-first, AI-second
design—demonstrated by construction but not exercised on these records. Second, the eligibility criteria were a
good-faith approximation of an unavailable original, and the error analysis showed this approximation to be a direct
cause of misses. Third, the reference labels themselves were imperfect: two off-topic records carried positive labels,
a concrete instance of the reference-standard ceiling. Fourth, the evaluation used one model, one topic, one drug-class
review, and one database, so the estimate cannot be assumed to transfer. Fifth, the ranking diagnostics (AUC, WSS)
rested on the model's uncalibrated self-reported confidence and should be read only as such. Finally, the evaluation
was author-built and author-evaluated—a declared conflict of interest that means it is not presented as independent.

## Applicability and generalisability

Because the estimate rests on a single model applied to a single drug-class review screened with approximated
criteria, it should be treated as a bounded proof of concept for this configuration and not as a general property of
AI screening or of the pipeline. Recall on observational-heavy topics, on questions with less standardised
vocabulary, or with a different or smaller model could differ, and nothing here speaks to those cases. The design's
transferable claim is narrower and process-level: a local, provider-agnostic, contamination-aware, recall-first
screening step that records provenance and refuses to self-certify against an ungrounded bar is feasible and produces
the artefacts a transparent report requires.

## Relation to prior work

The result sits within a literature that has repeatedly framed AI-assisted screening as a recall-first,
work-saving pre-filter and cautioned against precision-oriented composites; the recall-first metric set and the
work-saved framing follow that tradition, and the choice to gate on a high recall bar echoes the pre-specified
99%-recall target adopted for the Cochrane randomised-controlled-trial classifier (Thomas et al., 2021). Setting such
a target a priori and independently of the *tool* developer is a distinct reporting expectation (Thomas et al., 2026,
RAISE Part 2 §1, Box 2)—one this benchmark's default bar did not meet, and which the follow-up validation should.
What is less established, and what this paper positions rather than proves, is the surrounding design: a human
completes each step, the AI repeats it independently, and the human reconciles, applied across the whole pipeline with
a blind-first reliability layer. The present benchmark is a first, deliberately hedged step toward evaluating that
design; it does not, on its own, establish it.
