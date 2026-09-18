---
type: paper-node
title: "Paper B (methods/validation) — Results"
manuscript_section: results
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Step 5)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Every figure is the run's real value from `reliability/metrics.json`,
> `stage_counts.json`, and the error analysis of `Abstract_Audit_20260704_162555.csv` against
> `synergy_reference_labels.csv`. No clinical outcomes exist, so there is no GRADE grading or Summary-of-findings
> table; the results object is the reliability table (Table 1).

# Results

## Records screened and decision distribution

The screener returned a decision for all *N* = 327 records with no parsing or application-programming-interface
failures. It retained 240 records (178 *include* and 62 *uncertain*) and excluded 87. Against the reference standard
of 78 relevant and 249 not-relevant records, this yielded 69 true positives, 9 false negatives, 171 false positives,
and 78 true negatives. The large false-positive count is the intended consequence of a recall-first pre-filter that
over-includes at the title/abstract stage, not a malfunction; its cost is reported below as low precision and is the
conscious trade-off for retaining relevant records.

## Primary outcome: recall

Recall was .88 (95% CI [.80, .94]) against the 78 reference-relevant records: the AI retained 69 and missed 9. The
confidence interval is moderately wide despite 78 positives, reflecting the modest number of relevant records rather
than the full 327 screened. The one-sided 95% Wilson lower bound—the quantity the acceptance gate keys on—was .81.

## Secondary and tertiary metrics

The recall-weighted *F*β (β = 3) was .73. Specificity was .31 and precision was .29; precision this low is expected
when a recall-first pre-filter retains most records, and is the deliberate trade-off rather than a performance
failure. The area under the receiver-operating-characteristic curve, computed from the model's uncalibrated
self-reported confidence, was .58, and work-saved-over-sampling at 95% recall was −.05; both are ranking-quality
diagnostics here rather than literal work saved, because the screener reconciles every record rather than
prioritising a ranked list. As tertiary and caveated quantities, *F*1 was .43 and Cohen's κ was .12 (95% CI
[.06, .17]). The low κ is a prevalence artefact: one class (not-relevant) dominates the set (prevalence index = .52),
so κ reads low even at appreciable raw agreement, which is why it is reported as a consistency check and not as an
accuracy headline. Table 1 collects the full metric set.

**Table 1.** *Reliability of the AI title/abstract second-screener against the SYNERGY benchmark reference standard
(*N* = 327 records; 78 reference-relevant).*

| Domain | Metric | Value | 95% CI |
| :-- | :-- | :-- | :-- |
| Accuracy (primary) | Recall (sensitivity) | .88 | [.80, .94] |
| | Recall, one-sided 95% lower bound | .81 | — |
| Accuracy (secondary) | *F*β (β = 3) | .73 | — |
| | Specificity | .31 | — |
| | Precision | .29 | — |
| | AUC-ROC | .58 | — |
| Efficiency | WSS@95% (diagnostic) | −.05 | — |
| Consistency (tertiary) | *F*1 | .43 | — |
| | Cohen's κ | .12 | [.06, .17] |

*Note.* Confusion matrix: 69 true positives, 9 false negatives, 171 false positives, 78 true negatives.
Precision and κ are secondary/tertiary by design and are not the evaluation's headline (RAISE Part 2, p. 5;
Appendix 1).

## Acceptance against the pre-specified threshold

Judged against the pipeline's default recall target of .95 on the one-sided 95% lower bound, the screener did not
clear the bar (.81 < .95), and the run was flagged **re-pilot**. We report this as a *default* gate rather than a
formal acceptance decision, because the target was not set a priori and independently of the tool developer (RAISE
Part 2 §1, Box 2, p. 9). The number of reference-relevant records (78) exceeded the minimum we had set for a stable
estimate, so the shortfall reflects screening behaviour on this benchmark rather than an underpowered gate.

## Error analysis: the nine missed records

The nine false negatives were the evaluation's most informative result, because they were largely attributable to the
two reference-standard qualifications declared in the Methods rather than to indiscriminate screening. Five were
pharmacokinetic, drug–drug-interaction, or healthy-volunteer studies of the review's own drugs (tolterodine,
oxybutynin) that the screener excluded on a strict reading of the approximated population criterion ("adults *with*
urinary incontinence or overactive bladder"); the original drug-class review had nonetheless included such studies,
and three of these five were included after full-text assessment in the source review. Two were records the source
labelled relevant that are, on their face, off topic for a urinary-incontinence drug review (a pre-eclampsia calcium
trial and a neonatal-outcomes study); both carried a positive full-text label in the dataset, so the screener's
exclusion is defensible and the discrepancy plausibly reflects reference-standard noise (the ceiling on every
estimate). The remaining two were urinary-incontinence records with no pharmacological intervention (a quality-of-life
survey and a natural-history review) that the screener reasonably excluded and that the source review also excluded at
full text. In sum, five of the nine "missed" records were included in the source review's final set—splitting into a
criteria-approximation effect and probable label noise—while the other four aligned with the source review's eventual
full-text exclusions.

## Contamination probe

The pre-scoring memorization probe recorded that the model recognised the Cohen et al. (2006) paper and its use of
the SYNERGY dataset but could not name any specific included clinical study. The observed recall of .88—materially
below the near-ceiling value that direct memorisation of the label set would tend to produce—is consistent with
general topic recognition rather than recall of the specific inclusion decisions. We therefore report the estimate as
a possibly-inflated upper bound that a fresh, in-progress review would be needed to confirm, rather than as a voided
result.

## Pre-specified analyses that were not estimable

Design-stratified recall (randomised vs non-randomised studies), source-database stratification, and the
mixed-effects screening-fatigue model could not be estimated on this dataset—study design is captured only at data
extraction, a single database supplied every record, and the reference labels carried no per-screener order or
timestamps—and are reported as not available rather than replaced by a proxy.
