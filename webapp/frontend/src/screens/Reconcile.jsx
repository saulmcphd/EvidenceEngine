import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'
import RunAI from '../RunAI.jsx'

const PILL = { include: 'inc', exclude: 'exc', uncertain: 'maybe', split: 'maybe', awaiting: 'maybe', '': 'maybe' }
const LABEL = { include: 'Include', exclude: 'Exclude', uncertain: 'Maybe', split: 'Split', awaiting: 'Awaiting', '': '—' }
const FILTERS = [
  ['all', 'All'],
  ['dis', 'Disagreements'],
  ['pending', 'Pending'],
  ['sel', 'Selection review'],
]

function Pill({ v }) {
  return <span className={'pill ' + (PILL[v] || 'maybe')}>{LABEL[v] || v}</span>
}

const doiUrl = (doi) => {
  const d = String(doi || '').trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')
  return d ? 'https://doi.org/' + d : ''
}

// Decision-aware relevance score — the SAME ranking the AI ranked-queue uses (screener_abstract.relevance_score).
// The AI's confidence is confidence IN ITS DECISION, so a confident EXCLUDE is confidently IRRELEVANT; ranking on
// raw confidence alone would mix sure-excludes in with sure-includes. include 50+conf/2 · uncertain 50 · exclude 50-conf/2.
function relevanceScore(decision, confidence) {
  let c = parseFloat(confidence)
  if (!Number.isFinite(c)) c = 0
  c = Math.max(0, Math.min(100, c))
  const d = String(decision || '').trim().toLowerCase()
  if (d === 'include') return 50 + c / 2
  if (d === 'exclude') return 50 - c / 2
  return 50
}

export default function Reconcile() {
  const [stage, setStage] = useState('abstract')
  const [screener, setScreener] = useState('')   // '' = whole team (consensus of all screeners)
  const [filter, setFilter] = useState('all')
  const [sortMode, setSortMode] = useState('attention')   // 'attention' (default) | 'relevance' (prioritised)
  const [state, setState] = useState(null)
  const [err, setErr] = useState('')
  const [draft, setDraft] = useState({})         // record_id -> { note }
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    const q = '/reconcile?stage=' + stage + '&screener=' + encodeURIComponent(screener)
    api(q).then(d => { setState(d); setErr('') }).catch(e => setErr(String(e)))
  }, [stage, screener])
  useEffect(() => { load() }, [load])

  const saveConsensus = (rid, decision, routed) => {
    const d0 = draft[rid] || {}
    // The guard and the POST must read exactly what the inputs DISPLAY: the draft if edited, else the
    // already-saved values the row carries — otherwise re-saving a saved exclude (e.g. to add a note)
    // is falsely rejected while the reason/quote sit visibly filled on screen.
    const row = (state?.rows || []).find(x => x.record_id === rid) || {}
    const exReason = d0.exReason ?? row.exclusion_reason ?? ''
    const exQuote = String(d0.exQuote ?? row.supporting_quote ?? '')
    // interesting-but-ineligible bookmark carries on an exclude at EITHER stage: draft edit wins, else the
    // existing tag on the row (from a prior screener/reconciliation)
    const interesting = ((d0.interesting ?? (row.interesting === 'yes')) ? 'yes' : '')
    // A final full-text EXCLUDE must carry a failed-criterion reason + verbatim quote (C41) — guard client-side too.
    if (!routed && decision === 'exclude' && stage === 'fulltext' && !(exReason && exQuote.trim())) {
      setErr('A final full-text exclude needs a failed-criterion reason AND a verbatim quote — fill them in above this record.')
      return
    }
    setBusy(rid); setErr('')
    api('/consensus', {
      method: 'POST',
      body: { stage, record_id: rid, consensus_decision: routed ? '' : decision, routed_third: !!routed,
        note: d0.note ?? row.note ?? '', exclusion_reason: exReason, supporting_quote: exQuote, interesting },
    }).then(d => {
      setBusy('')
      if (d.error) { setErr(d.message || d.error); return }
      load()
    }).catch(e => { setBusy(''); setErr(String(e)) })
  }

  const rows = (state?.rows || []).filter(r => {
    if (filter === 'dis') return !r.match && !r.ai_missing   // a missing AI arm is neither agreed nor disagreed
    if (filter === 'pending') return !r.consensus
    if (filter === 'sel') return r.selection_review
    return true
  })
  // Prioritised (efficiency) order — reconciliation-only. Sorts the SAME rows most-likely-relevant first from the
  // AI arm's decision+confidence; it only REORDERS what's already shown (the blind screen is never touched).
  const orderedRows = sortMode === 'relevance'
    ? rows.map((r, i) => [r, i]).sort((a, b) =>
        (relevanceScore(b[0].ai, b[0].ai_confidence) - relevanceScore(a[0].ai, a[0].ai_confidence)) || (a[1] - b[1])
      ).map(x => x[0])
    : rows
  const c = state?.counts || {}

  return (
    <div>
      <div className="info" style={{ marginBottom: 14 }}>
        <strong>The blind is lifted here — and only here.</strong> Run this after your blind screening and the
        independent AI run are both done. You see both calls, settle each disagreement, and your <strong>Consensus </strong>
        becomes the review's working data. The Consensus is <em>not</em> the AI's report card — that stays your blind
        decision (recall, with its confidence interval, is on the Reliability screen). When still unsure at abstract
        stage, keep the study (recall-first); the AI is your second checker and you make every final call.
      </div>

      {/* controls */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
        {state?.demo && <span className="demo-badge">DEMO · no real run yet</span>}
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
          Reconcile stage
          <select className="select" style={{ width: 'auto' }} value={stage} onChange={e => setStage(e.target.value)}>
            <option value="abstract">Title/abstract (5a)</option>
            <option value="fulltext">Full text (5b)</option>
          </select>
        </label>
        <select className="select" style={{ width: 200 }} value={screener} onChange={e => setScreener(e.target.value)}>
          <option value="">{(state?.screeners?.length || 0) > 1 ? 'All reviewers (team)' : 'You (the reviewer)'}</option>
          {(state?.screeners || []).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {state?.ai_audit_file && <span className="muted" style={{ fontSize: 11.5 }}>AI arm: <span className="mono">{state.ai_audit_file}</span></span>}
      </div>

      {err && <div className="warn" style={{ marginBottom: 14 }}>{err}</div>}

      {state?.gate && (
        <>
          <div className={'gate ' + (state.gate.verdict === 'GO' ? 'go' : 'nogo')}>
            <strong>{state.gate.verdict === 'GO' ? '✓ GO' : '⟳ RE-PILOT'}</strong>
            &nbsp;— recall one-sided lower bound {state.gate.lower} vs {state.gate.independent ? 'a-priori' : 'default'} threshold {state.gate.threshold}
            <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>({state.gate.source})</span>
            <span className="demo-badge" style={{ marginLeft: 8 }}>{state.gate.validated ? 'validated run' : 'DEMO threshold check'}</span>
          </div>
          {/* Reference-standard ceiling at the gate (F8) — concept-gold-standard-reference-caveat / RAISE 2 Appendix 1 */}
          <div className="muted" style={{ fontSize: 11, margin: '4px 0 10px' }}>
            This recall can only be as good as the reference standard it is scored against — the AI cannot score better
            than the blind-human decisions (or benchmark) it is compared to (RAISE&nbsp;2). A <strong>GO</strong> is relative
            to that reference, not proof the screening is correct in absolute terms.
          </div>
        </>
      )}

      {!state ? <div className="muted">Loading…</div>
        : !state.has_ai && !state.has_human ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>Nothing to reconcile yet</h2>
            <p className="muted" style={{ lineHeight: 1.7 }}>
              Reconciliation needs <strong>both</strong> arms for this stage:
              your blind {stage === 'fulltext' ? 'full-text' : 'abstract'} decisions <em>and</em> an independent AI run.
              Complete the {stage === 'fulltext' ? 'Full-text' : 'Title/abstract'} screen (or upload decisions you already made, on that same screen).
              You can run the AI second screener right here once your own decisions exist:
            </p>
            <RunAI stage={stage} onDone={load} compact />
          </div></div>
        ) : !state.has_ai ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>Your decisions are in — now run the AI second screener</h2>
            <p className="muted" style={{ lineHeight: 1.7 }}>
              You have blind {stage === 'fulltext' ? 'full-text' : 'abstract'} decisions but the AI has not screened
              this stage yet. Run it below (it uses the provider you chose on Setup); when it finishes, this screen
              fills with the side-by-side comparison to reconcile.
            </p>
            <RunAI stage={stage} onDone={load} compact />
          </div></div>
        ) : !state.has_human ? (
          <div className="warn">No blind human {stage} decisions yet{screener ? ` for ${screener}` : ''}. Complete the {stage === 'fulltext' ? 'Full-text' : 'Title/abstract'} screen (or upload your decisions) first.</div>
        ) : (
          <>
            {/* count cards */}
            <div className="recon-cards">
              <div className="rc"><div className="n">{c.agreed ?? 0}</div><div className="l">Agreed</div></div>
              <div className="rc dis"><div className="n">{c.disagreed ?? 0}</div><div className="l">Disagreed</div></div>
              <div className="rc"><div className="n">{c.pending ?? 0}</div><div className="l">Pending consensus</div></div>
              {!screener && c.human_split > 0 && <div className="rc"><div className="n">{c.human_split}</div><div className="l">Human-split</div></div>}
              <div className="rc sel"><div className="n">{c.selection_review ?? 0}</div><div className="l">Selection review</div></div>
            </div>
            <div className="muted" style={{ fontSize: 11.5, margin: '4px 0 10px' }}>
              Working counts of what still needs your adjudication — <strong>not an agreement score</strong>. The AI's
              recall (with its 95% CI) is graded against your blind decisions on the Reliability screen, never here.
            </div>

            {stage === 'fulltext' && state.awaiting > 0 && (
              <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 12px' }}>
                {state.awaiting} full-text record(s) are <strong>awaiting classification</strong> (couldn’t be obtained
                or read) — they’re parked out of reconciliation, not excluded, and appear in the PRISMA flow. Bring one
                back by resolving retrieval/translation on the Full-text screen (records screened in-app), or by
                correcting and re-uploading your decisions export (imported records — a re-upload wins per record).
              </div>
            )}

            {(state.human_only > 0 || state.ai_only > 0) && (
              <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 12px' }}>
                {state.human_only > 0 && (stage === 'fulltext'
                  ? <>{state.human_only} record(s) you screened have no AI second opinion — the latest AI run didn’t cover them (usually a missing or unmatched PDF, or a pilot run on the first few). They appear below marked “no AI arm”, so you can still complete their final decision. </>
                  : <>{state.human_only} record(s) you screened are not in the AI arm yet. </>)}
                {state.ai_only > 0 && <>{state.ai_only} record(s) the AI screened you have not screened yet. </>}
                {stage === 'fulltext'
                  ? <>An AI-only record never receives a consensus without your decision.</>
                  : <>Only records decided by <em>both</em> appear below (inner join).</>}
              </div>
            )}

            <div className="seg" style={{ marginBottom: 12 }}>
              {FILTERS.map(([k, l]) => (
                <button key={k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>
                  {l}{k === 'sel' ? ` (${c.selection_review ?? 0})` : ''}
                </button>
              ))}
            </div>

            {/* Prioritised (efficiency) order — safe here because the blind is already lifted at reconciliation. */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', margin: '0 0 12px' }}>
              <span className="muted" style={{ fontSize: 11.5 }}>Order</span>
              <div className="seg">
                <button className={sortMode === 'attention' ? 'on' : ''} onClick={() => setSortMode('attention')}>Needs attention first</button>
                <button className={sortMode === 'relevance' ? 'on' : ''} onClick={() => setSortMode('relevance')}>Most-likely-relevant first</button>
              </div>
              {sortMode === 'relevance' && (
                <span className="muted" style={{ fontSize: 11 }}>
                  Prioritised (efficiency) view — work the AI's most-likely-relevant records first. It only reorders this
                  list; it changes no decision, and your blind screening is never affected.
                </span>
              )}
            </div>
            {filter === 'sel' && (
              <div className="info" style={{ marginBottom: 12 }}>
                <strong>Selection review — the recall safeguard.</strong> These are the records where <em>either</em> reviewer
                — you or the AI — would drop the study or was unsure about it (including the ones the AI keeps but you would
                exclude, where the AI rescues a study you'd have lost). A missed relevant study (false negative) is the costly
                error, so look hardest here before you let an exclusion stand.
              </div>
            )}

            {orderedRows.length === 0 ? (
              <div className="card"><div className="bd"><p className="muted" style={{ margin: 0 }}>No records match this filter.</p></div></div>
            ) : orderedRows.map(r => (
              <div key={r.record_id} className={'recon-row card' + (r.match ? '' : ' mismatch')}>
                <div className="bd">
                  <div className="recon-head">
                    <div>
                      <div className="rec-title" style={{ fontSize: 15, margin: 0 }}>{r.title || '(no title)'}</div>
                      <div className="rec-meta">
                        {r.record_id}{r.selection_review ? ' · selection-review' : ''}
                        {doiUrl(r.doi) && <> · <a className="ft-inline" href={doiUrl(r.doi)} target="_blank" rel="noreferrer">full text ↗</a></>}
                      </div>
                    </div>
                    <div className="recon-decisions">
                      <div className="dcol"><span className="dlab">You{r.human_split ? ' (split)' : ''}</span><Pill v={r.human} /></div>
                      <div className="dcol"><span className="dlab">AI</span>{r.ai_missing ? <span className="pill maybe">not screened</span> : <Pill v={r.ai} />}</div>
                      {r.ai_missing
                        ? <span className="mchip no">no AI arm</span>
                        : <span className={'mchip ' + (r.match ? 'ok' : 'no')}>{r.match ? '✓ agree' : '✕ differ'}</span>}
                    </div>
                  </div>

                  {r.human_split && (
                    <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                      Reviewers disagree: {Object.entries(r.per_screener).map(([s, v]) => `${s}=${v}`).join(', ')} — you are the third voter here.
                    </div>
                  )}

                  <div className="ai-box">
                    {r.ai_missing ? (
                      <div className="muted" style={{ fontSize: 12 }}>
                        The AI’s latest run didn’t cover this record, so there’s no second opinion. Usual causes:
                        its PDF isn’t staged (or its filename didn’t match the record), or the last run was a
                        pilot on the first few records. Stage/check the PDF on the Full-text screening page and
                        re-run the AI — or record your final decision below without one (it stays your call either way).
                      </div>
                    ) : (<>
                    <div className="dlab">AI rationale</div>
                    {r.ai_confidence !== '' && !r.selection_review && r.ai !== 'exclude' && (
                      <div className="muted" style={{ fontSize: 10.5, marginTop: 1 }}>
                        AI self-reported confidence {r.ai_confidence} — uncalibrated, not a validated probability
                      </div>
                    )}
                    <div className="ai-rat">{r.ai_rationale || <span className="muted">(none)</span>}</div>
                    </>)}
                    {stage === 'fulltext' && (r.ai_reason || r.ai_quote) && (
                      <div style={{ marginTop: 6, fontSize: 12 }}>
                        {r.ai_reason && <div><span className="dlab">AI reason</span> {r.ai_reason}</div>}
                        {r.ai_quote && (
                          <div style={{ marginTop: 3 }}>
                            <span className="dlab">AI quote</span> “{r.ai_quote}”{' '}
                            {r.ai_quote_verified === true ? <span style={{ color: 'var(--inc)' }}>✓ found in PDF</span>
                              : r.ai_quote_verified === false ? <span style={{ color: 'var(--exc)' }}>✗ NOT found in PDF — treat the exclusion with suspicion</span>
                              : <span className="muted">(no PDF to verify)</span>}
                          </div>
                        )}
                      </div>
                    )}
                    {stage === 'fulltext' && (r.human_reason || r.human_quote || r.human_flag) && (
                      <div style={{ marginTop: 6, fontSize: 12 }}>
                        {r.human_reason && <div><span className="dlab">Your reason</span> {r.human_reason}</div>}
                        {r.human_quote && <div style={{ marginTop: 3 }}><span className="dlab">Your quote</span> “{r.human_quote}”</div>}
                        {/* r.human_flag alone must still render — an imported exclude missing BOTH its
                            reason and quote is exactly the row whose flag the user most needs to see */}
                        {r.human_flag && <div className="warn" style={{ marginTop: 4 }}>{r.human_flag}</div>}
                      </div>
                    )}
                  </div>

                  {/* a final full-text exclude must document a failed criterion + verbatim quote (C41) */}
                  {stage === 'fulltext' && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-start', margin: '8px 0 2px' }}>
                      <div style={{ flex: '1 1 200px', minWidth: 180 }}>
                        <span className="dlab">If excluding — failed criterion</span>
                        <select className="select" value={draft[r.record_id]?.exReason ?? r.exclusion_reason ?? ''}
                          onChange={e => setDraft(s => ({ ...s, [r.record_id]: { ...(s[r.record_id] || {}), exReason: e.target.value } }))}>
                          <option value="">— choose a reason —</option>
                          {(state.reasons || []).map(x => <option key={x} value={x}>{x}</option>)}
                        </select>
                      </div>
                      <div style={{ flex: '2 1 260px', minWidth: 200 }}>
                        <span className="dlab">Verbatim quote</span>
                        <input className="input" placeholder="exact sentence from the paper"
                          value={draft[r.record_id]?.exQuote ?? r.supporting_quote ?? ''}
                          onChange={e => setDraft(s => ({ ...s, [r.record_id]: { ...(s[r.record_id] || {}), exQuote: e.target.value } }))} />
                      </div>
                      {/* MECIR C40 reminder (F3) — the backend soft-blocks a reporting-only exclude on save */}
                      <div className="muted" style={{ flexBasis: '100%', fontSize: 10.5 }}>
                        MECIR C40: an outcome not <strong>reported</strong> is not an exclusion ground (synthesis matter) — exclude on the outcome only if it wasn’t <strong>measured</strong>.
                      </div>
                    </div>
                  )}

                  {/* interesting-but-ineligible bookmark (playbook-title-abstract-screening step 9 / F2) — the
                      SAME three-bucket distinction (excluded ≠ awaiting-classification ≠ interesting-but-
                      ineligible) applies at BOTH screening stages, not full-text only; pre-checked if a
                      screener already flagged it. Saved only on an Exclude consensus (backend-enforced). */}
                  <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 11.5, color: '#374151', margin: '6px 0 2px' }}>
                    <input type="checkbox"
                      checked={draft[r.record_id]?.interesting ?? (r.interesting === 'yes')}
                      onChange={e => setDraft(s => ({ ...s, [r.record_id]: { ...(s[r.record_id] || {}), interesting: e.target.checked } }))} />
                    Interesting but ineligible — bookmark for the background/discussion &amp; reference-list mining (saved on an Exclude consensus; never enters the included set)
                  </label>

                  {/* consensus control */}
                  <div className="recon-actions">
                    <span className="dlab">Consensus</span>
                    {['include', stage !== 'fulltext' ? 'uncertain' : null, 'exclude'].filter(Boolean).map(d => (
                      <button key={d} disabled={busy === r.record_id}
                        className={'cbtn ' + PILL[d] + (r.consensus === d ? ' on' : '')}
                        onClick={() => saveConsensus(r.record_id, d, false)}>{LABEL[d]}</button>
                    ))}
                    <button className={'cbtn third' + (r.routed_third ? ' on' : '')} disabled={busy === r.record_id}
                      onClick={() => saveConsensus(r.record_id, '', true)}>→ 3rd reviewer</button>
                    <input className="input" style={{ flex: 1, minWidth: 140 }} placeholder="note (optional)"
                      value={draft[r.record_id]?.note ?? r.note ?? ''}
                      onChange={e => setDraft(s => ({ ...s, [r.record_id]: { ...(s[r.record_id] || {}), note: e.target.value } }))} />
                    {r.consensus
                      ? <span className="muted" style={{ fontSize: 11.5 }}>saved: <strong>{LABEL[r.consensus]}</strong></span>
                      : r.routed_third
                      ? <span className="muted" style={{ fontSize: 11.5 }}>→ awaiting 3rd reviewer</span>
                      : <span className="muted" style={{ fontSize: 11.5 }}>pending</span>}
                    {stage !== 'fulltext' && !r.match && (
                      <span className="muted" style={{ fontSize: 11, flexBasis: '100%' }}>
                        Unsure? Keep it (Include or Maybe) and let full text decide — recall-first.
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </>
        )}
    </div>
  )
}
