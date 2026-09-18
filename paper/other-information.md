---
type: paper-node
title: "Paper B (methods/validation) — Other information"
manuscript_section: other-information
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing + apa-style skills; playbook-write-up Step 9)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** PRISMA 2020 items 24–27. Items with nothing yet on record are honest `____`
> blanks, not assertions.

# Other information

## Registration and protocol (PRISMA item 24)

- **Registration:** ____ (this contamination-aware benchmark was not prospectively registered; state this plainly.
  A methods evaluation of this kind is not a PROSPERO-eligible intervention review, but the analysis plan—recall
  as the primary outcome, the recall-first metric set, and the acceptance rule—should be time-stamped and shared
  before the pre-registered blind-human-first validation the Conclusions call for.)
- **Protocol availability:** the run's analysis plan, prompts, and configuration are contained in the reproducibility
  bundle (below); a standalone pre-registration for the follow-up validation is ____ (to complete).
- **Amendments (item 24c):** the eligibility criteria were a good-faith approximation of an unavailable original;
  this substitution, and its effect on apparent recall, are reported in the Methods and Results rather than hidden.

## Support and funding (PRISMA item 25)

- **Funding:** ____ (state the funding source and grant number, or "no specific funding").
- **Role of funder:** ____ (state the funder's role in design, conduct, analysis, or reporting, or "none").

## Competing interests (PRISMA item 26)

The evaluation was **author-built and author-evaluated**: the developer of the pipeline conducted its validation.
This is a real conflict of interest, declared here, and it is the reason the evaluation is **not** presented as
independent (Thomas et al., 2026, RAISE Part 1, recommendation 2.8). The acceptance threshold was likewise the tool's own default and was
not set by an evaluator independent of the developer, which is reported as a default gate rather than an a-priori
acceptance decision. Mitigation for the follow-up study: recruit an independent methodologist to fix the acceptance
bar and audit the evaluation design before any scoring.

## Availability of data, code, and materials (PRISMA item 27)

All run artefacts—the record set, the AI decisions with rationales and self-reported confidences, the reliability
metrics, the pre-scoring memorization probe, and the generated AI-use disclosure—are retained in an interoperable
Open Knowledge Foundation bundle that serves as the data-availability statement: the bundle *is* the supplement. It is
to be released under an open licence with a Zenodo digital object identifier, Dublin Core metadata, and per-file
checksums, following FAIR (data) and FAIR4RS (research software) principles, as recommended for tool developers in
RAISE Part 1 (Thomas et al., 2026, recommendation 3.6; verified against the RAISE Part 1 source). The benchmark
dataset itself is openly distributed as part of the SYNERGY collection (see References).
