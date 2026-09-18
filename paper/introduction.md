---
type: paper-node
title: "Paper B (methods/validation) — Introduction"
manuscript_section: introduction
provenance:
  ai_model: claude-sonnet-5
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Step 2)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** No "Introduction" heading is used, per `apa-style`; the paper title is repeated at
> the top of the body and the section opens directly into the Background. Assembled from `outline.md` §2 and the OKF
> bundle's provenance nodes, per `playbook-write-up` Step 2. Numbered RAISE recommendations must be re-verified
> against the RAISE Part 1 source before submission (playbook-write-up Guardrail "RAISE citation discipline").

# Human-first, AI-second screening for systematic reviews: a contamination-aware benchmark of a local, provider-agnostic pipeline (EvidenceEngine)

Artificial intelligence (AI) is entering every stage of the systematic-review process, from search and screening
through data extraction and synthesis (Higgins et al., 2023; Thomas et al., 2026). The methodological consensus
governing that entry is unambiguous: a generative model may *augment* a review but must never *replace* the human
judgement on which the review's validity rests. Dual, independent screening by two reviewers has long been a
mandatory expectation for full-text eligibility decisions (Higgins et al., 2023, Cochrane MECIR C39), and the
responsible-AI guidance written specifically for evidence synthesis extends the same principle to an AI collaborator:
human oversight of every AI-assisted judgement is a standing recommendation, not an optional safeguard (Thomas et al.,
2026, RAISE Part 1, recommendation 3.20). Any tool that proposes to use AI in screening must therefore be evaluated as
a *second* screener working alongside a human, not as a replacement for one.

The pipeline this paper evaluates, EvidenceEngine, instantiates that principle as a single design spine applied
across the whole review process rather than at one stage in isolation: for each step, a human completes the task, an
AI repeats the same task independently against the identical criteria, the two outputs are compared, and the human
reconciles any disagreement—so that the reconciled human decision, never the raw AI output, becomes the review's
data. A *blind-first* reliability layer sits underneath this spine: where a validation study is run, the human
decision is recorded before the AI output is seen, so that agreement is not inflated by the human being anchored to
what the AI already proposed. Existing work has applied AI to individual review tasks—most visibly title/abstract
screening (van de Schoot et al., 2021) and full-text classification (Thomas et al., 2021)—typically evaluated in
isolation and without a blind-first human reference. A human-first-then-AI-check design applied consistently across
every stage of the pipeline, with blind-first validation built in rather than added after the fact, is, to our
knowledge, not yet established in the published literature; this paper does not claim to establish it either, but
reports the first evaluation of one link in that chain.

A credible evaluation of an AI second screener has to confront two threats before a single recall figure can be
trusted, and both are treated here as explicit design concerns rather than as limitations to be discovered later.
The first is **training-data contamination**: if the benchmark against which the AI is graded is a published review,
the AI's underlying language model may already have encountered that review, or the studies it included, during
training, so that an apparently high recall reflects memorisation rather than screening skill (Thomas et al., 2026,
RAISE Part 2 §2, pp. 16–18). The second is the **reference-standard ceiling**: an AI screener can only ever be shown
to agree or disagree with the reference labels it is graded against, and if those labels are themselves imperfect—as
a published review's own labels typically are, being neither blind nor independently re-derived—then an apparent AI
error may in fact be an error in the reference standard, not in the AI (Thomas et al., 2026, RAISE Part 2, Appendix
1, p. 32). Reporting a screening evaluation without disclosing how these two threats were handled risks presenting a
number that looks more definitive than the design can support.

**Objective.** The present study estimates the recall of EvidenceEngine's AI title/abstract second-screener against a
fixed benchmark reference standard, with recall specified as the primary outcome because a missed relevant study is
substantially costlier to a review than an unnecessary full-text read (Thomas et al., 2026, RAISE Part 2, p. 5). The
evaluation measures and discloses contamination risk via a pre-scoring memorization probe, rather than assuming it
away, and reports the acceptance threshold's own provenance—whether it was set a priori and independently of the tool
developer—rather than presenting a pass/fail verdict without that context. Consistent with a first evaluation of this
kind, the study is framed throughout as a bounded proof of concept, not as a demonstration that the AI is a
"definitive second reviewer."
