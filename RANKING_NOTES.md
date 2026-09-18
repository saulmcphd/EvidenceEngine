# RANKING_NOTES — the ranked reconciliation queue (`ranked_queue.csv`)

## What it is and when to use it

Running `screener_abstract.py` with `--ranked-output` writes a second CSV, `ranked_queue.csv`
(same output folder as the audit file), containing **every screened record, sorted so the ones most
likely to be relevant come first**. Columns: `record_id, title, ai_decision, confidence, rationale,
relevance_score`.

It is a **work queue for the production arm**: the order in which a (non-blind) reviewer tackles
reconciliation. Instead of working through records in database order, you start where the AI says
"almost certainly relevant" and work down. It is useful in two situations:

- **A normal (non-validation) review**, where you are reconciling the AI's screen and want the
  likely includes on top.
- **The production arm of a validation run**, i.e. only *after* the blind human decisions have been
  recorded and locked.

## Why the sort key is `relevance_score`, not raw `confidence`

The screener's `confidence` number means *"how sure the AI is of its own decision"* — so an
`exclude` at confidence 95 means **confidently irrelevant**. Sorting by raw confidence descending
would put "definitely irrelevant" records at the very top of the queue next to "definitely
relevant" ones, which is useless as a priority order (and would make WSS@95%, below, meaningless).

`relevance_score` folds the decision and the confidence into one *likely-relevant-first* scale:

| ai_decision | relevance_score | range |
| :-- | :-- | :-- |
| include | 50 + confidence/2 | 50–100 |
| uncertain | 50 | 50 |
| exclude | 50 − confidence/2 | 0–50 |

So within the includes the order **is** confidence-descending (as originally specified); uncertains
sit in the middle; and among excludes the *least-sure* excludes come first — exactly the ones a
reconciler should double-check before trusting a "definitely out". Ties keep the master-records
order (stable sort), so the queue is deterministic. The raw `confidence` column is kept unchanged.
(If a raw confidence-descending file is ever wanted instead, it is a one-line change in
`build_ranked_queue`.)

## The blind-first gate (plain English)

**This file must never appear on the blind human screening screen.**

In a validation run the whole point is that the human records their include/exclude decisions
*before seeing anything the AI produced*. If the human screens records in the AI's ranked order —
or can even see that ranking exists — they know which records the AI liked, and their "independent"
decisions are anchored to the AI's. The agreement statistics would then be inflated and the
validation worthless. The same one-directional rule as the audit file's blank `Human_Decision`
column applies: AI output flows to the human only **at reconciliation, after** the blind decisions
are locked. The gate is marked with a `BLIND-FIRST GATE` comment at the exact line in
`screener_abstract.py` where the file is written, so no future UI work wires it into the blind
screen by accident.

## How WSS@95% will be computed from this ranking (Task 2, SYNERGY)

**WSS@95%** ("work saved over sampling at 95% recall") answers: *if a reviewer read records in this
ranked order and stopped once 95% of the truly relevant records had been found, how much reading
would they save compared with reading in random order?*

From `ranked_queue.csv` plus the reference labels (SYNERGY's include/exclude):

1. Sort by `relevance_score` descending (the file already is).
2. Walk down the list until the records seen so far contain ≥ 95% of all truly relevant records.
3. `WSS@95% = (records NOT read ÷ total records) − 0.05` (the 0.05 credits the 5% of relevant
   records you accepted to miss). Positive = the ranking saves real work; ≈ 0 = no better than
   random order.

Two implementation notes for Task 2:

- **Use the existing engine, don't reimplement:** `reliability.py` already has a tie-safe
  `wss_at_recall(human_bin, scores)` (ties counted pessimistically, so the result doesn't depend on
  row order). Feed it `relevance_score` as `scores`.
- **This differs from the SYNERGY benchmark's reported WSS (−.05):** that run fed *raw* confidence
  into `wss_at_recall`, which mixes confident excludes in with confident includes — one reason it
  showed no ranking value. Task 2 should report WSS@95% on `relevance_score`, and can report the
  raw-confidence figure alongside it for comparison. Either way the standing caveats apply: the
  scores are uncalibrated LLM self-report, and EvidenceEngine's default workflow reconciles every
  record, so WSS here is a **ranking-quality diagnostic**, not a literal workload saving.
