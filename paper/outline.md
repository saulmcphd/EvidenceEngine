---
type: paper-node
title: "Paper B (methods/validation) — outline"
manuscript_section: outline
target_journal: "Research Synthesis Methods (alt: Systematic Reviews)"
provenance:
  ai_model: claude-opus-4-8
  ai_provider: anthropic
  prompt_file: session-authored (academic-writing skill; playbook-write-up Step 1)
  prompt_version: paper-b-draft-v1
  human_verified: false
---

# Paper B — outline (methods / validation paper)

**Working title.** *Human-first, AI-second screening for systematic reviews: a contamination-aware benchmark of a
local, provider-agnostic pipeline (EvidenceEngine).*

> Draft assembled from the OKF bundle + the run's real reliability figures (`reliability/metrics.json`) and AI-use
> disclosure (`raise-disclosure.md`), per `playbook-write-up`. **Not human-verified.** Every numbered RAISE
> recommendation cited below is drawn from the already-generated disclosure and **must be re-verified against the
> RAISE Part 1 source before submission** (playbook-write-up Guardrail "RAISE citation discipline"). This is a
> **proof-of-concept** validation, framed as such throughout — never as a "definitive second reviewer".

## Section order (confirm before drafting the remaining sections)

1. **Title + structured abstract** (PRISMA-for-Abstracts; 150–250 words). Background/objective · methods · results
   (recall + 95% CI, the contamination caveat) · conclusions (proof-of-concept, disclosed limitations). — *drafted last.*

2. **[Body opens with the title repeated — no "Introduction" heading (`apa-style`)].** Background & rationale:
   - AI is entering every stage of systematic reviewing; the governing concern is that a generative model must
     **augment, never replace, human judgement** (Cochrane MECIR C39; RAISE Part 1 human-oversight rec 3.20).
   - The product thesis this paper evaluates: a **human-first, AI-second** spine — a human completes each step, an AI
     repeats it *independently*, the two are compared, and the human reconciles — applied across the *whole* pipeline,
     with a **blind-first** reliability layer. State what is novel (others apply AI to a single step; the
     human-first-then-AI-check-across-all-steps design is not established) without over-claiming.
   - The two threats a validation must confront up front: **training-data contamination** (validating against a
     published review the model may have memorised — RAISE Part 2 §2, pp.16–18) and the **reference-standard ceiling**
     (performance can be only as good as the labels it is graded against — RAISE Part 2 Appendix 1, p.32).
   - **Objective (explicit).** Estimate the recall of the AI abstract second-screener against a benchmark reference
     standard, recall-first, with the contamination risk measured and disclosed rather than assumed away.

3. **Methods** (drafted in `methods-section.md`): the pipeline; the AI abstract screener; the benchmark dataset and
   reference standard (with the criteria-approximation caveat); contamination handling (the pre-scoring memorization
   probe); the recall-first reliability analysis and the a-priori-vs-default acceptance threshold; the AI-use
   disclosure (RAISE Part 1 recs 1.8/1.9 buckets) and human-oversight statement; software/reproducibility.

4. **Results** — *stub, to draft next.* No clinical outcomes, so **no GRADE / Summary-of-findings table**; the results
   object is the reliability table. Report, from `reliability/metrics.json`:
   - **Headline (Accuracy):** recall = .88 (95% CI [.80, .94]) on *N* = 78 reference-relevant records; one-sided 95%
     lower bound .81; 69 of 78 kept, 9 missed.
   - **Secondary:** *F*β(β = 3) = .73; specificity = .31; precision = .29 (low by design — the conscious recall-first
     pre-filter trade-off, not a failure); AUC = .58; WSS@95% = −.05 (a ranking diagnostic here, not literal work
     saved). **Tertiary (caveated):** *F*1 = .43; Cohen's κ = .12 (95% CI [.06, .17]) — prevalence caveat (one class
     dominates, so κ reads low even at appreciable agreement).
   - **Acceptance verdict:** against the **default** .95 recall bar (not set a priori independently of the developer),
     the one-sided lower bound (.81) does not reach the target → **re-pilot**, reported honestly as a default gate.
   - **Error analysis of the 9 misses** (the paper's most informative result): 5 pharmacokinetic / drug-interaction /
     healthy-volunteer studies *of the review's own drugs* excluded on a strict population reading of the approximated
     criteria (3 were included at full text in the source review); 2 off-topic records the source labelled relevant
     (reference-standard noise — the AI's exclusion is arguably correct); 2 non-drug records the AI reasonably dropped
     that the source also excluded at full text.
   - **Contamination result:** the pre-scoring probe recorded that the model recognised the *dataset* but could not
     name its included studies; recall of .88 (not ≈1.0) is consistent with topic recognition rather than label
     memorisation — so the estimate is reported as a possibly-inflated **upper bound**, not voided.

5. **Discussion** — *stub.* Summary of the main result; **potential biases in the evaluation** (single benchmark, a
   published-review reference rather than blind fresh-human decisions, an approximated criteria set, no
   reconciliation/fatigue arm exercised here); completeness/applicability (one topic, one database, one model);
   agreements/disagreements with prior AI-screening evaluations. Apply the overinterpretation guardrails (interpret the
   CI width, not a pass/fail threshold; do not read "did not clear the bar" as "unfit").

6. **Conclusions** — *stub.* Two subsections, **no recommendations**. Implications for the method (a local,
   provider-agnostic, contamination-aware, human-first-AI-second design is feasible and produces an auditable,
   provenance-stamped record; recall is promising but unproven pending a blind-first fresh-review validation).
   Implications for research (the pre-registered blind-human-first study the product centres on; a precision/assurance
   calculation to fix *N* positives and an a-priori, developer-independent recall bar; multi-model and multi-topic
   replication).

7. **Other information** (PRISMA 24–26). Registration (____ — none yet; state honestly); funding + funder role (____);
   competing interests (**author-built and author-evaluated — a real conflict, declared; the evaluation is not
   presented as independent**, RAISE Part 1 rec 2.8); data/code availability = the OKF bundle (Zenodo DOI, FAIR /
   FAIR4RS) — the bundle is the data-availability statement (PRISMA item 27).

## Inputs → sections (the join spine)
- Methods ← `criteria.txt`, `screening_abstract.txt` (prompt + version), `config.json` (model/provider/threshold),
  `reliability/memorization-probe.md`, `raise-disclosure.md`.
- Results ← `reliability/metrics.json`, `Abstract_Audit_*.csv` (the 9-miss error analysis), `synergy_reference_labels.csv`.
- Other information ← `responsible-handover.md`, the OKF bundle Zenodo DOI (to mint).
