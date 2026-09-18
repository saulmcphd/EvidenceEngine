---
type: paper-node
title: "Paper B (methods/validation) — structured abstract"
manuscript_section: abstract
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Step 9)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Structured to the PRISMA-for-Abstracts items, adapted for a methods/validation
> paper; ~200 words (target 150–250).

# Abstract

**Background and objective.** Artificial intelligence (AI) is entering every stage of systematic reviewing, where a
generative model must augment rather than replace human judgement. We evaluated the recall of an AI title/abstract
second-screener embedded in a local, provider-agnostic, human-first pipeline, treating training-data contamination and
the reference-standard ceiling as explicit design concerns rather than afterthoughts.

**Methods.** We screened all 327 records of the SYNERGY "Urinary Incontinence" drug-class benchmark (Cohen et al.,
2006) at temperature 0 with a recall-first prompt, using a good-faith approximation of the unavailable original
eligibility criteria. The reference standard was the dataset's own screening labels—a published-review benchmark, not
blind fresh-human decisions. Before scoring, a memorization probe recorded what the model recalled of the review.
Recall with a Wilson 95% confidence interval was the primary outcome.

**Results.** Recall was .88 (95% CI [.80, .94]); the screener retained 69 of 78 reference-relevant records and missed
nine. Five of the nine misses were in the source review's final set, splitting into a criteria-approximation effect
and probable reference-label noise. The probe indicated dataset recognition but not memorised decisions, so the
estimate is a possibly-inflated upper bound.

**Conclusions.** A contamination-aware, human-first, AI-second screening step is feasible and auditable, but recall
remains promising and unproven pending a pre-registered, blind-human-first validation.
