---
type: paper-node
title: "Paper B (methods/validation) — Methods"
manuscript_section: methods
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Steps 3–4)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Figures are the run's real values from `reliability/metrics.json`; the AI-use
> statements are re-tensed from the generated `raise-disclosure.md`. Numbered RAISE recommendations must be
> re-verified against the RAISE Part 1 source before submission (playbook-write-up Guardrail).

# Methods

## Study design and evaluation framework

We conducted a contamination-aware benchmark evaluation of an artificial-intelligence (AI) title-and-abstract
second-screener, embedded in a local systematic-review pipeline (EvidenceEngine). The evaluation was designed as a
Study-Within-A-Review: the AI screened a fixed record set independently, and its decisions were graded against an
external reference standard. Consistent with guidance that recall (sensitivity) is paramount for screening because a
missed relevant study is far costlier than an extra one to read, we specified recall as the primary outcome and
treated precision and related quantities as secondary (Thomas et al., 2026, RAISE Part 2, p. 5). The evaluation and
its reporting were structured to the RAISE Part 2 §4 reporting checklist (Thomas et al., 2026, pp. 22–24).

The pipeline instantiates a *human-first, AI-second* design: a human completes a review step, an AI repeats the same
step independently against the identical criteria, the two are compared, and the human reconciles any disagreement,
whose reconciled decision—not the AI output—becomes the review's data. The AI is therefore a second screener and
never the sole reviewer (Higgins et al., 2023, Cochrane MECIR C39; Thomas et al., 2026, RAISE Part 1, human-oversight
recommendation 3.20). The present benchmark
exercised the AI arm and the comparison against a reference standard; because the reference labels stood in for the
human arm (see below), the reconciliation step was demonstrated by design but not applied to these records. The
pipeline runs locally through a provider-agnostic model interface, so no record content or key left the analysis
machine.

## The AI title-and-abstract second-screener

For each record, the screener applied the pre-specified eligibility criteria to the title and abstract and returned a
structured decision—*include*, *exclude*, or *uncertain*—with a one-sentence rationale and a self-reported
confidence. The prompt instructed the model to disregard any prior knowledge of the review or its studies and to
apply only the supplied criteria; to over-include at the title/abstract stage; to return *uncertain* rather than
*exclude* whenever an eligibility element could not be judged from the abstract; and never to exclude on a criterion
that could not be assessed from the title or abstract alone. An *uncertain* decision was carried forward to full text
and, in the analysis, counted as a retained (positive) record, consistent with the recall-first stance. Requests were
issued at temperature 0 through a provider-agnostic interface (LiteLLM); an unparseable response defaulted to
*uncertain* and any technical failure defaulted to *include*, so that no relevant record could be lost to a parsing
or network error. The model of record was Google Gemini 2.5 Flash (`gemini/gemini-2.5-flash`), run with the
researcher's own application-programming-interface key; the exact prompt file (`screening_abstract.txt`) and its
content-hash version were archived with each decision.

## Benchmark dataset and reference standard

We evaluated the screener on the "Urinary Incontinence" drug-class review dataset distributed with the SYNERGY
collection, originally assembled by Cohen, Hersh, Peterson, and Yen (2006) to study automated citation
classification. The record set comprised *N* = 327 titles and abstracts. The reference standard was the dataset's own
title-and-abstract screening labels (78 records labelled relevant, 249 not relevant); of the 78, 40 were included
after full-text assessment in the source review.

Two features of this reference standard qualify every estimate and are stated here rather than in the limitations
alone. First, it is a **published-review benchmark**, not the blind, independent decisions of a fresh human reviewer
that the pipeline is designed around; grading an AI against a review's published labels is a weaker and
contamination-prone reference than a purpose-collected blind human standard, and we report it as such. Second, the
exact eligibility criteria used by the original reviewers are not distributed with the dataset. We therefore
reconstructed a good-faith PICO approximation from the dataset topic (population: adults with urinary incontinence or
overactive bladder; intervention: a pharmacological treatment; comparator: placebo, another drug, or none; outcomes:
efficacy and/or safety), and recorded that any mismatch between this approximation and the original criteria would
tend to *lower* apparent recall by causing defensible but non-matching exclusions.

## Contamination handling

Because the reference standard is a published review that the model may have encountered during training, we ran a
memorization probe **before** any scoring and recorded its output verbatim to the run record
(`reliability/memorization-probe.md`), so that a suspiciously high recall could be traced to memorisation rather than
skill (Thomas et al., 2026, RAISE Part 2 §2, data contamination, pp. 16–18). The configured model was asked, without
access to the labels,
whether it recognised the review and could name its included studies. It reported recognising the Cohen et al. (2006)
paper and its use of the SYNERGY dataset but stated that it could not name specific included clinical studies. We
therefore interpret the recall estimate as a possibly memorisation-inflated **upper bound** and, following the
guidance, note that a fresh or in-progress review would be the appropriate reference for a definitive claim. A
positive probe caps interpretation; it does not, on its own, void the estimate.

## Reliability analysis

We joined the AI decisions to the reference labels on a stable record identifier and computed recall-first screening
metrics with the positive class defined as *include* (and, per the recall-first stance, *uncertain* mapped to
include). The primary quantity was recall with a Wilson 95% confidence interval. We report as secondary the
recall-weighted *F*β with β = 3 (a missed relevant study judged roughly β² ≈ 9 times as costly as an extra full-text
screen; Thomas et al., 2026, RAISE Part 2 Appendix 1, p. 34), specificity, precision, the area under the
receiver-operating-characteristic
curve, and work-saved-over-sampling at 95% recall; and as tertiary, with explicit caveats, *F*1 and Cohen's κ with a
bootstrap 95% confidence interval and a prevalence note. We did not headline *F*1, accuracy, or κ, because on a highly
imbalanced screening set an "exclude-everything" classifier attains high accuracy while missing every relevant study.

The acceptance threshold was the pipeline's **default** recall target of .95, evaluated against the one-sided 95%
Wilson lower bound of recall rather than the point estimate. Because no person was recorded as having set this target
a priori and independently of the tool developer, we report it honestly as a default gate and not as an a-priori,
developer-independent acceptance criterion (Thomas et al., 2026, RAISE Part 2 §1, Box 2, p. 9). Every reported number
is further bounded by the reference-standard ceiling: performance can be only as good as the reference labels, so an
apparent AI error may be an error in the reference (Thomas et al., 2026, RAISE Part 2 Appendix 1, p. 32).

We had pre-specified design-stratified recall (randomised-controlled-trial vs non-randomised studies), a source-
database stratification, and a mixed-effects screening-fatigue model as secondary analyses. None was estimable on
this dataset: study design is captured only at data extraction and no study was extracted; a single database
(PubMed) supplied every record; and the reference labels carried no per-screener order or timestamps. We report these
as not available rather than substituting a proxy.

## AI-use disclosure and human oversight

We disclose AI use per the RAISE Part 1 recommendations (Thomas et al., 2026) to declare AI use for each judgement
(recommendation 1.8) and to report it against the four content buckets of recommendation 1.9: the tool name, version,
and date; the purpose, the stage affected, and the justification with the validation reported here; declarations of
interest; and the limitations of the AI use. Each AI decision was written to a provenance-stamped record carrying the
exact model and version, the provider, the prompt file, and the prompt version, with a human-verification flag that is
set only after a human reconciles the decision. The design principle that a human reconciles every AI judgement
(Higgins et al., 2023, MECIR C39; Thomas et al., 2026, RAISE Part 1, recommendation 3.20) is built into the pipeline;
we again note that this benchmark used published labels in place of that human arm, so the oversight step was not
exercised on these records. The evaluation was author-built and author-evaluated—a real conflict of interest, which we
declare and which means the evaluation is **not** presented as independent (Thomas et al., 2026, RAISE Part 1,
recommendation 2.8).

## Software, reproducibility, and data availability

Screening was deterministic in specification (temperature 0, a pinned model version, and an archived prompt with a
content-hash version), acknowledging that production language models are not bit-for-bit reproducible even at
temperature 0. All run artefacts—the record set, the AI decisions with rationales and confidences, the reliability
metrics, the memorization probe, and the generated AI-use disclosure—are retained in an interoperable knowledge
bundle that serves as the reproducibility package and the data-availability statement (to be released under an open
licence with a Zenodo digital object identifier and file checksums, following FAIR and FAIR4RS principles). Analyses
used the pipeline's own reliability module; no results were re-implemented by hand.
