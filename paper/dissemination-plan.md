---
type: paper-node
title: "Paper B (methods/validation) — Dissemination plan"
manuscript_section: dissemination-plan
provenance:
  ai_model: claude-sonnet-5
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing skill; playbook-write-up Step 11)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

> **Draft — not human-verified.** Answers the five dissemination decisions playbook-write-up Step 11 asks for
> (audience, key message, format, messenger, timing/channel). The key message is reused verbatim from
> `conclusions.md`'s certainty-graded take-home, per the playbook's instruction not to re-derive it. This is a plan,
> not a claim that dissemination has happened — every channel below is a proposal Saul confirms or edits.

# Dissemination plan

## 1. Audience — name a priority group, not "everybody"

The single highest-priority audience is **systematic-review methodologists and information specialists who are
currently deciding whether to adopt an AI second-screener for their own review** — the people this paper's finding
is actually decision-relevant for. Two secondary audiences follow from that: **Cochrane/Campbell/JBI/CEE methods
groups** shaping guidance on AI-assisted screening (the paper directly engages the 2025 position statement those
groups jointly issued), and **researchers building or evaluating similar AI-screening tools**, who are the natural
audience for the contamination-aware benchmark design itself, independent of this specific tool's recall figure.
A broader public/patient audience is served by the plain-language summary, but is not this plan's priority target —
this is a methods paper about a screening tool, not a review of a clinical question with direct patient relevance.

## 2. Key message — the certainty-graded conclusion, reused verbatim

> A local, human-first, AI-second screening design is feasible and produces an auditable, provenance-stamped record.
> On this single contamination-aware benchmark, the AI second-screener's recall (.88, 95% CI [.80, .94]) is
> consistent with a useful recall-first pre-filter, but the estimate is **promising and unproven** rather than
> evidence that the tool is a dependable second screener. That the tool flagged its own run "re-pilot" against its
> default bar, rather than passing itself, is itself the behaviour a transparent-reporting instrument should show.

This is deliberately the *same* sentence the Conclusions carries — the dissemination message must not drift from, or
overstate, what the paper itself concludes.

## 3. Format

- **Primary:** the peer-reviewed paper itself (target *Research Synthesis Methods*, alternatively *Systematic
  Reviews*), plus the openly licensed OKF knowledge bundle (Zenodo DOI) as the reproducibility supplement.
- **Secondary, short-form:** a plain-language summary (`plain-language-summary.md`, already drafted) suitable for a
  blog-length post or a methods-group newsletter item.
- **Secondary, structured:** a short slide deck (5–8 slides) built directly from the Results table and the error
  analysis, for a methods-seminar or conference lightning talk — the error-analysis breakdown of the nine misses is
  the single most conference-talk-friendly result in the paper and should headline any such deck.
- **Not planned:** a press release or general-media pitch — the finding is a methods result for a specialist
  audience, not a clinical or public-health headline, and framing it as one would risk overstating a "promising and
  unproven" result.

## 4. Messenger — partner with bodies that already have reach

- **Cochrane Methods / the Campbell-Cochrane-JBI-CEE AI position-statement authors** — the paper explicitly engages
  their 2025 position statement; sharing the preprint with that group before or alongside submission is the most
  direct route to the audience most able to act on the finding.
- **The EvidenceEngine repository itself** (GitHub) — the OKF bundle and template repository are already public
  distribution points; a short README summary linking the paper once published reaches anyone who forks the tool.
- **Author's own professional network** (the author's university/lab channels) for the first announcement — no
  existing large-reach partner has been engaged yet; this is flagged, not assumed.

## 5. Timing and channel

- **On preprint/submission:** post a preprint (e.g. OSF, matching RAISE's own OSF-hosted precedent) at the same time
  the paper is submitted, so the methods community can see the design before peer review completes.
- **On acceptance:** publish the plain-language summary alongside the paper; share via the repository README and the
  author's professional network.
- **Ongoing:** the OKF bundle stays live and versioned on Zenodo regardless of the paper's publication timeline, so
  the reproducibility artefact is available to anyone who finds the tool independently of the paper's own reach.

## Not yet done (honest status)

No dissemination step above has actually happened yet — this document is the *plan*, confirmed at protocol stage in
spirit and finalised here per Step 11, not a record of completed outreach. Saul should confirm the messenger list
(are there other methods groups or mailing lists worth adding?) before any of this is executed.
