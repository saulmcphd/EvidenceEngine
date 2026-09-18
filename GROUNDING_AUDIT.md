# Grounding audit — app stages vs the OKF concept brain (2026-07-01)

**Method.** A 27-agent workflow audited all 13 app stages: for each screen one agent read the frontend + backend
route + the matching playbook + the linked concept nodes and flagged anything **invented, contradicting a concept,
or omitting a rule the concept teaches**; a second agent adversarially re-checked every flag; a lead agent
consolidated. Verdicts: **0 well-grounded · 2 mostly · 7 partly · 4 weakly.**

The whole app *knows* the right method (it is in the concept nodes) but several screens break it in execution. Three
patterns dominate: (1) the human-first / AI-second spine is skipped on the AI-judgement steps (synthesis, extraction,
RoB); (2) three screening stages have no "can't get / can't read this paper" bucket, forcing silent exclusions;
(3) provenance is stamped on some screens, missing on others.

## Stage scorecard

| Step | Screen | Grounding | Gist |
| :-- | :-- | :-- | :-- |
| 1 Setup | Setup.jsx | partly | outcome *reporting* vs *measuring*; examples field can't save; stage-code jargon |
| 1b Protocol | Protocol.jsx | partly | AI Background no provenance; no registry duplicate-check gate; register-before-search buried |
| 2 Search | Search.jsx | mostly | ✅ search log + currency flag + CSV export + reference-list/restriction reminders built (2026-07-01); still open: PRESS peer-review nudge (LOW) |
| 5a Abstract | BlindScreening.jsx | mostly | recall-first honoured; no awaiting-classification / interesting-but-ineligible bucket |
| 5b Full-text | FullText.jsx | weakly | unobtainable/non-English only Include/Exclude → silent exclusion bias |
| 5c Reconcile | Reconcile.jsx | partly | final exclude savable with no reason/quote (breaks audit trail) |
| 6 Risk of bias | RoB.jsx | weakly | per-study not per-result; overall auto-maxed no override; AI quote never PDF-checked |
| 7 Extraction | Extract.jsx | partly | blind default OFF; no pilot loop; AI source-quote dropped before UI |
| 8 Synthesis | Synthesis.jsx | weakly | AI silent sole synthesist; GRADE from insufficient inputs; RoB never fed in |
| ✓ Reliability | Reliability.jsx | partly | threshold rule mis-cited; stability/test-retest missing; no COI gate |
| 9 Report | Report.jsx | mostly | AI-disclosure mislabelled item 27; PRISMA-trAIce over-claimed; GRADE/SoF not flagged as owed |
| 10 Evidence map | Evidence.jsx | partly | "same design/measure" implies combinability; no aggregate narrative summary |
| Help | Help.jsx | partly | "verified" library over-claim; no confident-but-wrong caveat |

---

## ✅ Fixes applied 2026-07-01 (safe, unambiguous, verified against the concept node)

- [x] **Setup — outcome MEASURING not REPORTING.** Placeholders reworded ("Measures at least one of your chosen
  outcomes"; "Does not measure any of your chosen outcomes") + a caption: a study that measured but didn't report is
  still included (missing results handled in synthesis). *(high, `concept-primary-vs-secondary-outcomes`)*
- [x] **Extraction — blind entry now ON by default** (`Extract.jsx` `useState(true)`); the per-row gate already
  reveals each AI value only after the human types theirs. *(high, `concept-blind-first-validation`)*
- [x] **Help — "verified methodology library" → "curated methodology library"** in the UI and in the LLM prompt
  strings + error message (`Help.jsx`, `app.py` ×3); all 235 notes are `human_verified:false`, so "verified" was an
  over-claim. *(high, `concept-ai-provenance`)*
- [x] **Help — persistent per-answer caveat** added: "AI-generated help — check it against the linked notes; it can
  sound confident and still be wrong." *(medium, `concept-hallucination-evaluation`)*
- [x] **Reliability — a-priori-threshold re-cited.** Was "RAISE Part 1 rec 3.20" (that is the human-oversight rec);
  now "RAISE Part 2 §2–3 — the Cochrane RCT Classifier had its 99%-recall bar set independently of the developers."
  *(high, citation discipline, `concept-a-priori-threshold-independent-developer`)*
- [x] **Report — AI-use disclosure relabelled** off "PRISMA item 27" (item 27 = data/code availability) to
  "PRISMA-trAIce; RAISE Part 1 recs 1.8–1.10". *(medium, `concept-prisma-item-reporting-guide`)*
- [x] **Report — PRISMA-trAIce marked "proposed (not yet endorsed) — cite as emerging"** in the flow caption.
  *(medium, `concept-prisma-traice`)*

---

## ✅ Fixes applied 2026-07-01 — session 2 (batch: human-first spine + provenance)
Verified: `py_compile` OK · `okf_writer.py selftest` PASSED · frontend build clean · 33-check in-process contract test
(no API key spent — LLM helpers monkeypatched) · browser walk-through (Synthesis compare/accept, Protocol caption; no
console errors) · adversarial review (14 agents; 9 raised / 4 confirmed → all 4 fixed) · sample Outputs + bundle left clean.

- [x] **Synthesis — human-first, AI never the sole synthesist** (HIGH). `Synthesis.jsx` rebuilt: you write each
  section; per-section "Get an independent AI draft" → a compare panel (independent second opinion · model · not
  human-verified) → "Use this as my draft" (Accept) → "✓ reviewed & reconciled". Backend: separate
  `synthesis_ai_drafts.json` store; `POST /api/synthesis/ai-draft` (GRADE skipped), `POST /api/synthesis/accept`
  (copies draft→field, flips the OKF node), `_synthesis_md()` writes only the reconciled human arm and tags
  AI-accepted sections; `synthesis_generate` no longer AI-drafts into the file. *(`concept-dual-screening`)*
- [x] **AI-draft provenance — Protocol + Synthesis** (HIGH). `okf_writer.write_ai_draft_node` + `set_node_verified`;
  every AI draft writes a provenance node (`human_verified:false` at birth, flipped on accept) and is labelled
  "not yet human-verified" in the UI and generated files. *(`concept-ai-provenance`)*
- Review-driven hardening (4 low findings, all fixed): re-drafting an accepted section keeps its AI-assisted tag
  (persistent `accepted_text`, so AI-derived text can't slip in untagged); the `synthesis.md` footer mentions AI
  only when a section was actually AI-assisted; `accept` guard `str()`-coerces (no 500 on a malformed store);
  `_protocol_md` docstring updated to the 5-tuple.
- Also fixed during build: `protocol_state()` unpacked `_protocol_md()` as a 4-tuple after it became a 5-tuple
  (500 → Protocol screen hung on "Loading…"); caught by browser verification, fixed + re-verified 200.

**Scorecard movement:** Synthesis weakly → **mostly** (human-first + provenance + GRADE-human-only landed; still open:
RoB-into-synthesis + the SWiM method ladder, MEDIUM/LOW). Protocol partly (Background provenance landed; registry
duplicate-check gate + register-before-search nudge still open).

## ✅ Fixes applied 2026-07-01 — session 3 (batch: "can't get / can't read this paper" bucket)
Verified: `py_compile` OK · frontend build clean · 19-check in-process contract test (awaiting recorded not-excluded,
PRISMA awaiting surfaced + rendered, 5c exclude reason/quote gate, awaiting parked out of the reconcile grid, saved
reason/quote reload, explicit-0 wins) · browser walk-through (5b awaiting controls + info-styled confirmation; 5c
parked-awaiting note + awaiting not a grid row; no console errors) · adversarial review (14 agents; 10 raised / 7
confirmed → all fixed) · sample Outputs left clean.

- Full-text (5b) **awaiting-classification bucket** (unobtainable + unreadable-language), never a silent exclude.
- **PRISMA** shows "Studies awaiting classification (n=X)" (tallied from the human arm; explicit stage_counts value wins).
- **5c** requires a failed-criterion reason + verbatim quote on a final full-text exclude (C41), reloaded on re-open.
- Review-driven fixes: awaiting records PARKED out of the reconcile grid (were leaking in as false disagreements —
  the top HIGH finding) + read-only note; saved exclude reason/quote reload; `_prisma_counts` honours an explicit 0;
  non-English-exclude caveat; awaiting confirmation is info-styled not amber. **Scorecard: 5b weakly → mostly, 5c partly → mostly.**

**Scope note:** awaiting was implemented at 5b (concept-grounded); 5a relies on "Maybe" to carry a can't-read record forward.

## ✅ Fixes applied 2026-07-01 — session 4 (batch: Search stage — search log finished)
Verified: `py_compile` OK · CSV-mirror unit test (BOM, quoted commas, non-dict skip, int→str, 0-hits kept) ·
currency month-math unit test in Node (empty→hidden, 6/12-mo thresholds, oldest-wins, future→0) · frontend build
clean · live API round-trip (POST→ok, GET round-trips, CSV on disk) · download route 200 for the CSV / 404 for the
non-allowlisted JSON (allowlist intact) · browser walk-through on the seeded log (red "out of date · 15 months"
pill + C37 caption + table + both buttons; no console errors) · client-side CSV matches the backend byte-for-byte ·
**sample Outputs restored** (test `search_log.json` + `search-record-table.csv` deleted → blank template).

- On discovery: the search log itself (one-row-per-search table + C36/C35/C30 grounding + Methods-item-6 feed) was
  **already built** in a prior session but never ticked here — the audit's "no search log" line was stale. Session 4
  built the two pieces that were genuinely absent:
- **Search-currency flag** (`Search.jsx`): computes the age of the OLDEST logged search (conservative, so a stale
  search can't hide behind a recent top-up) and shows a green/amber/red pill + a Cochrane-C37 caption (publish within
  ~12 months of the initial search, 6 preferred; rerun every database AND screen the delta, then log the rerun as a
  new row). *(`concept-publish-within-a-year-of-search`)*
- **Downloadable `search-record-table.csv`**: a client-side download button (always matches the on-screen table, no
  404 before first save) + a backend disk mirror written on every save (`_write_search_log_csv`, utf-8-sig BOM,
  canonical column headers) added to the `/api/download` allowlist — the appendix-ready audit artefact.
  *(`concept-search-record-table`)*

**Scorecard movement:** Search weakly → **mostly** (log + currency + CSV + restriction/reference-list reminders all
present; remaining open item is the LOW PRESS peer-review nudge).

---

## ⬜ Remaining backlog (queued pending scope decision)

### HIGH — breaks a non-negotiable or a referee would catch
- [x] **Protocol + Synthesis — AI drafts carry no provenance block.** ✅ DONE 2026-07-01 (session 2). New
  `okf_writer.write_ai_draft_node` + `set_node_verified`; both the Protocol Background draft and every Synthesis
  AI draft now write an OKF entity node (`ai_model/ai_provider/prompt_file/prompt_version/human_verified=false`,
  stamped at generation) and surface "AI-drafted — not yet human-verified" (Protocol toggle + generated doc caption;
  Synthesis compare panel). *(`concept-ai-provenance`)*
- [x] **Synthesis — AI is the silent sole synthesist** for blank sections. ✅ DONE 2026-07-01 (session 2). Human
  writes each section; AI produces an INDEPENDENT second-opinion draft in a SEPARATE store (never overwrites the
  human arm); the human compares and Accepts (reconciles) it → the section's OKF node flips `human_verified=true`
  and only accepted text enters `synthesis.md`, tagged "(AI-assisted … reviewed and reconciled)". An unaccepted draft
  never reaches the file (and re-drafting an accepted section keeps the tag). GRADE is never AI-drafted.
  *(`concept-dual-screening`)*
- [x] **5b — "awaiting classification / can't get this paper" bucket** ✅ DONE 2026-07-01 (session 3). 5b has
  "Can't get the full text" + "Can't read the language" controls → `ft_decision="awaiting"` (not an exclusion);
  tallied by `_ft_awaiting_count`, injected into PRISMA via `_prisma_counts` (surfaced in `_prisma_model` + drawn in
  the diagram's Included box), and PARKED out of the 5c reconcile grid (kept as a distinct bucket, shown read-only).
  *(`concept-full-text-retrieval-workflow`)* — NOTE: implemented at 5b (the concept-grounded place); 5a carries a
  can't-read record forward via "Maybe" (uncertain), so no separate 5a control was added.
- [x] **5b — non-English full text proficient-reader route** ✅ DONE 2026-07-01 (session 3). "Can't read the
  language" (+ language field) → awaiting, flagged "needs a proficient screener"; a caveat by the Exclude control
  says a non-English exclude must be a proficient reader's call, not a machine translation. *(`concept-multilingual-screening-logistics`)*
- [x] **5c — final reconciled *exclude* requires reason + verbatim quote** ✅ DONE 2026-07-01 (session 3).
  `consensus_write` rejects a full-text consensus exclude without exclusion_reason + supporting_quote (C41), persisted
  to `reconciliation_fulltext.csv` (RECON_COLS gained the 2 columns) and reloaded into the reconcile inputs.
  *(`concept-dual-screening` / C41)* — deferred: also incrementing `stage_counts.exclusion_reasons` from the reconciled
  arm (risks double-counting the AI screener's reasons; the reconciled reason lives in reconciliation_fulltext.csv).
- [ ] **RoB — rated per study, not per (study × outcome)**; never fixes the effect-of-interest (ITT vs per-protocol)
  or (ROBINS-I) the target trial. Add a per-result selector, an effect-of-interest toggle, and a Target-trial +
  a-priori-confounder box for ROBINS-I. *(`concept-rob2-domains`, `concept-nrsi-target-trial`)*
- [x] **Search — contemporaneous search log** ✅ DONE 2026-07-01 (session 4). The Search screen already carried a
  one-row-per-search log (date, full database name + interface/version, coverage dates, exact string as run, hits,
  limits+justification, and the C30 non-database/reference-list reminder), persisted to `search_log.json` and fed into
  the Methods write-up (PRISMA item 6). Session 4 finished the two genuinely-missing pieces of this item: (a) a
  **search-currency flag** — computed from the OLDEST logged search date (most conservative), amber >6 mo / red >12 mo,
  captioned to Cochrane C37 (rerun all databases + screen the delta within 12 months of the initial search, 6
  preferred) — grounded in [concept-publish-within-a-year-of-search]; (b) a **downloadable `search-record-table.csv`**
  (client-side button that always matches the on-screen table + a disk mirror written on save, added to the download
  allowlist). *(`concept-search-record-table`, `concept-documenting-reporting-search`, `concept-publish-within-a-year-of-search`)*
- [ ] **Extraction — AI source-quote column dropped before the UI** (`Audit_Notes` exists in the data). Render a
  source-quote/locus column beside each AI value with a "verified against source" control + a flag for any AI value
  lacking a locus. *(`concept-hallucination-evaluation`)*
- [ ] **Extraction — no pilot-and-revise loop (C43).** Add a pilot mode (run the extractor on 3–5 studies, reconcile,
  revise the form, bump `prompt_version`, then run the rest). *(`concept-data-collection-piloting`)*
- [ ] **Synthesis — GRADE drafted from data that can't support it** (no effect estimates, CIs, or RoB). Gate GRADE
  behind a per-outcome workflow that ingests reconciled RoB nodes + effect+CI and requires a human grade.
  *(`concept-grade-certainty`)*
- [ ] **Synthesis — risk of bias never read from Stage-6 nodes into synthesis.** Add a RoB column + body-level RoB
  summary; feed RoB into GRADE/robustness; note "high RoB is incorporated, never an exclusion gate".
  *(`concept-incorporating-rob-into-analysis`)*
- [ ] **Evidence map — "same design" / "shared measure" drawn as combinability links** the methodology denies.
  Demote to neutral descriptive links; caption that grouping is decided on PICO similarity in synthesis.
  *(`concept-grouping-studies-for-synthesis`)*
- [ ] **Evidence map — no aggregate "at a glance" narrative summary** (N studies, participants + range, dominant
  study, year span, settings, PICO spread). *(`concept-narrative-summary-included-studies`)*
- [ ] **Reliability — stability / test-retest missing app-wide** though `reliability.py` exposes `stability()`. Add a
  Stability card (flip-rate + variance over repeated identical-prompt runs; caching-defeated confirmation).
  *(`concept-llm-stability-test-retest`)*
- [ ] **Protocol — no pre-planning registry/duplicate-check gate.** Add a "before you register — have you searched
  PROSPERO/OSF/CDSR for an existing or in-progress review?" checklist + persist a registry-search date + go/no-go.
  *(`concept-checking-registries-for-ongoing-reviews`)*

### MEDIUM
- [ ] **Setup — examples round-trip broken** (backend supports `fields['examples']` but Setup never sends it); add an
  "Examples (one borderline include, one borderline exclude)" textarea + a 10–20-record pilot caption.
- [ ] **Setup — publication-status has no inclusive default**; default blank → "all (published, preprint, grey,
  unpublished)" + caption on MECIR C12 (include all statuses unless justified).
- [ ] **Protocol — PROSPERO picker has no health-outcome note / OSF alternative** at the point of choosing (a
  psychology reviewer could pick PROSPERO and be rejected). Add the caption there.
- [ ] **5b — reason dropdown has no guard** against excluding on outcome reporting (C40) or on a criterion not
  assessable from the text; add a reveal/caption (and optionally block outcome-reporting as a sole reason).
- [ ] **RoB — overall rating auto-maxed and read-only** though the caption promises the human finalises it; make it a
  human-settable select pre-filled with the worst-domain default + justification box.
- [ ] **RoB — conflicts of interest / funding captured nowhere**; add a separate "notable concern about COI" field
  (out of domain scoring, may inform Domain 5).
- [ ] **RoB — AI quote never checked against the PDF** (Extract + FullText do this); add a per-domain
  "quote-not-found / confabulation" flag + backend quote-back so an unsupported AI judgement is never auto-Low.
- [ ] **RoB — no descriptive non-bias fields / no "imprecision & external validity are not bias" cue** (a first-timer
  could mark a small study high-risk in a domain).
- [ ] **Extraction — no reported-vs-calculated flag, unit-of-analysis / analysis-N, or "no precision statistic = not
  poolable" flag.**
- [ ] **Synthesis — method choice reduced to "narrative vs meta-analysis"**; surface the SWiM data-driven ladder and
  name the two never-use vote-counting variants.
- [ ] **Synthesis — no grouping/study-characteristics matrix** (the human "which studies are similar enough to
  combine" decision) and no §9.4 direction/significance data-check + logged-deviation field.
- [ ] **Reliability — no conflict-of-interest field**; the screen can stamp "independent" on a conflicted evaluation
  (rec 2.8 forbids). Add a financial/non-financial COI field; suppress "independent" framing if declared.
- [ ] **Reliability — no stratified recall table** (by study design / source database / abstract length) — a strong
  average masks a weak stratum.
- [ ] **Report — checklist never signals GRADE certainty + Summary-of-Findings (items 15/22) are still owed** (a
  green checklist reads as a finished manuscript). Add a "still owed" row.
- [ ] **Report — no "present, don't recommend" / verb-strength-bound-to-certainty guardrail** (Table 15.6.b) — the
  single rule most likely to get a write-up rejected.
- [ ] **Help — inline note viewer strips the frontmatter incl. provenance**; render a small "drafted by …; not yet
  human-verified" footer.
- [ ] **Evidence map — no risk-of-bias-as-a-body signal** even when Stage-6 nodes exist.
- [ ] **Evidence map — "shared measure" edge implies combinability** across different constructs/time-points.
- [ ] **5a/5b/5c — no "interesting-but-ineligible" tag** (collapses into a plain exclude, losing the
  background/snowballing + reference-list-mining bucket).
- [ ] **Extraction — dev jargon / file paths on screen** (`prompter.py`, `EvidenceEngine/PDFs/`, raw audit filename,
  record_id as study title).

### LOW (mostly the jargon/stage-code sweep + optional captions)
- [ ] **Global jargon sweep** — internal stage codes ("5a/5b/5c", "step 6/7") leak into user prose on ≥7 screens
  (Setup, Protocol, FullText, Reconcile, Extract, Synthesis, Evidence, Report), plus raw filenames, script names
  (`prompter.py`, `boolean-search-builder`, `master_records.csv`), file paths (`EE/.env`), and unglossed
  acronyms/codes (RAISE, C46, WSS@95%, AUC-ROC, VIF). One pass across all screens.
- [ ] **5a — Maybe's "carried forward, you lose nothing" meaning** only shown in the consent gate; add to the visible
  in-screen banner.
- [ ] **5a — one-click "failed: <criterion>" exclusion reason** from the criterion tabs already on screen.
- [ ] **5c — reference-standard-ceiling caveat** absent under the GO/RE-PILOT gate (blind human decisions are
  fallible and cap any accuracy claim).
- [ ] **Reliability — gloss WSS@95% / AUC-ROC / F-β**, and sanitise the raw statistician strings (VIF, method,
  interval_type) out of the reader view.
- [ ] **Reliability — no contamination check** ("is your reference a published review the model may have
  memorised?") + the memorization-probe artefact.
- [ ] **Synthesis — SoF scaffold + heterogeneity note** (pooling gate) not built.
- [ ] **Synthesis / Report — pointers to Stage-9 certainty-graded "implications" + no-recommendations discipline.**
- [ ] **Protocol — amendment triad (what/why/at-which-stage)** taught only inside the generated doc; add an in-app
  helper line + the "register before you search" nudge near the Generate button.
- [ ] **Search — restriction+justification field (C35), unobtainable→awaiting note, PRESS peer-review nudge.**
- [ ] **Report — dissemination/KT plan + plain-language summary** pointer; expand "RAISE" on first use.
- [ ] **Extraction — numeric-input validation** for per-arm statistic rows (optional hardening).

---

## Audit's own honesty caveats
- Several **jargon** findings were tagged to concept nodes that don't literally state the rule — the governing
  authority is the `CLAUDE.md` UX non-negotiable + the `ux-for-phd-students-new-to-sr` memory. Re-anchor those there.
- A few concept nodes are themselves **stale** (e.g. `concept-iterative-search-development` still says the
  search-term editor lives on Setup — it moved to the Search step). Update the node.
- Some backend RAISE **rec 3.20** citations (human oversight, in the generated Methods / disclosure) are *correct* —
  only the Reliability-screen use for the *a-priori threshold* was wrong (now fixed).
- A few items match things already logged as **deferred** in `PROGRESS.md` (per-result RoB keying, the RoB quote-back
  guard) — corroboration, not new surprises.
