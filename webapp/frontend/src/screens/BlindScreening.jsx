import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api.js'
import { highlightByConcept } from '../concepts.jsx'
import RunAI from '../RunAI.jsx'
import UploadScreened from '../UploadScreened.jsx'

// Stage 5a — blind title/abstract screening (the reference screen). Simplified per Saul's direction:
// the ABSTRACT leads (it's the main source of information), and each eligibility criterion is a TAB that
// reveals its keywords + whether this record mentions them on click — instead of dumping every keyword and
// the full criteria text at once. Keyword EDITING now lives on Setup, so this screen just consumes them.
// Blind-first: no AI output, no peer decisions, no ranking is ever shown here.
// Entry point B ("already screened elsewhere?") is the shared UploadScreened card — the same two-entry-points
// design as the Full-text screen, one component for both stages.

const doiUrl = (doi) => { const d = String(doi || '').trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, ''); return d ? 'https://doi.org/' + d : '' }

export default function BlindScreening() {
  const [screeners, setScreeners] = useState([])
  const [who, setWho] = useState('')
  const [consent, setConsent] = useState(false)
  const [criteria, setCriteria] = useState('')
  const [showCriteria, setShowCriteria] = useState(false)   // full criteria collapsed by default (declutter)
  const [state, setState] = useState(null)
  const [reason, setReason] = useState('')
  const [tab, setTab] = useState('')                        // active criterion tab (concept id)
  const [err, setErr] = useState('')
  const reasonRef = useRef(null)

  useEffect(() => {
    api('/screeners').then(d => { setScreeners(d.screeners || []); if (d.screeners?.length) setWho(d.screeners[0]) }).catch(e => setErr(String(e)))
    api('/criteria').then(d => setCriteria(d.text || '')).catch(() => {})
  }, [])

  const load = useCallback(() => { if (!who) return; api('/worklist?screener=' + encodeURIComponent(who)).then(setState).catch(e => setErr(String(e))) }, [who])
  useEffect(() => { setConsent(false); setState(null) }, [who])
  useEffect(() => { if (who && consent) load() }, [who, consent, load])

  // keep a valid active criterion tab as concepts load (default = first inclusion criterion)
  useEffect(() => {
    const ids = (state?.concepts || []).map(c => c.id)
    if (ids.length && !ids.includes(tab)) setTab((state.concepts.find(c => c.role === 'include') || state.concepts[0]).id)
  }, [state, tab])

  const giveConsent = () => { api('/consent', { method: 'POST', body: { screener: who } }).catch(() => {}); setConsent(true) }

  const decide = useCallback((decision) => {
    if (!state?.next) return
    api('/decision', { method: 'POST', body: { screener: who, record_id: state.next.record_id, position: state.next.position, decision, reason: decision === 'exclude' ? reason : '' } })
      .then(d => { setState(d); setReason('') }).catch(e => setErr(String(e)))
  }, [state, who, reason])

  const undo = () => api('/undo', { method: 'POST', body: { screener: who } }).then(setState).catch(e => setErr(String(e)))

  // I / M / E decide; R focuses the exclusion-reason field (Rayyan parity) — disabled while typing in a field
  useEffect(() => {
    const onKey = (e) => {
      if (!consent || !state?.next) return
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return
      const k = e.key.toLowerCase()
      if (k === 'i') decide('include')
      else if (k === 'm') decide('uncertain')
      else if (k === 'e') decide('exclude')
      else if (k === 'r') { e.preventDefault(); reasonRef.current?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [consent, state, decide])

  if (err) return <div className="warn">Could not load: {err}. Is the backend running, and have you built master records + per-screener orders?</div>
  if (!screeners.length) return <div className="info">No per-screener orders yet. Build the master records first on <strong>Search &amp; records</strong>, then return here.</div>

  const concepts = state?.concepts || []
  const cov = Object.fromEntries((state?.next?.coverage || []).map(c => [c.id, c]))
  const active = concepts.find(c => c.id === tab)
  const activeCov = active ? cov[active.id] : null

  return (
    <div className="blind">
      {/* slim rail: who + progress only */}
      <div className="facets">
        <div className="card" style={{ marginBottom: 14 }}><div className="bd">
          <span className="blind-badge">● BLIND ON</span>
          <div style={{ marginTop: 12, fontSize: 11.5, fontWeight: 600, color: '#4b5563' }}>You are</div>
          <select className="select" value={who} onChange={e => setWho(e.target.value)} style={{ marginTop: 4 }}>
            {screeners.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div></div>
        {consent && state && !state.error && (
          <div className="card"><div className="hd"><h2>Your decisions</h2></div><div className="bd">
            <div className="count-row"><span>Undecided</span><span className="v">{state.remaining}</span></div>
            <div className="count-row"><span style={{ color: 'var(--inc)' }}>Included</span><span className="v">{state.counts?.include ?? 0}</span></div>
            <div className="count-row"><span style={{ color: 'var(--maybe)' }}>Maybe</span><span className="v">{state.counts?.maybe ?? 0}</span></div>
            <div className="count-row"><span style={{ color: 'var(--exc)' }}>Excluded</span><span className="v">{state.counts?.exclude ?? 0}</span></div>
            <div className="muted" style={{ fontSize: 10.5, marginTop: 10 }}>Edit the criteria &amp; keywords on <strong>Setup</strong>.</div>
          </div></div>
        )}
      </div>

      {/* main */}
      <div>
        <UploadScreened />
        {!consent ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>Instructions &amp; consent</h2>
            <ul style={{ fontSize: 13, lineHeight: 1.7, color: '#374151' }}>
              <li>Decide only from the criteria and the title/abstract shown.</li>
              <li>Set aside anything you already know about these papers.</li>
              <li>When genuinely unsure, choose <strong>Maybe</strong> — it <em>definitely</em> carries through to full text. Only Exclude removes a study here. Never exclude because the abstract is short or doesn't mention an outcome — missing information is a reason to keep, not exclude.</li>
              <li>Your decisions and their timestamps are recorded for a methods study; nothing else is collected.</li>
            </ul>
            <button className="btn primary" onClick={giveConsent}>I consent — start screening</button>
          </div></div>
        ) : !state ? <div className="muted">Loading…</div>
          : state.error ? <div className="warn">{state.message || state.error}</div>
            : (
              <>
                <div className="info" style={{ marginBottom: 12, padding: '8px 13px' }}>
                  You decide from the record and criteria alone — <strong>the AI's calls are hidden here</strong> (you reconcile later). Unsure → <strong>Maybe</strong>: it carries through to full text, and <strong>only Exclude</strong> removes a study here.
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, color: 'var(--muted)', marginBottom: 4 }}>
                  <span>{state.decided} of {state.total} screened</span>
                  <span>{state.decided > 0 && <span style={{ color: 'var(--blue)', cursor: 'pointer', fontWeight: 600, marginRight: 10 }} onClick={undo}>↶ Undo last</span>}<span className="mono">{who}</span></span>
                </div>
                <div className="progress" style={{ marginBottom: 14 }}><div style={{ width: (state.total ? (state.decided / state.total * 100) : 0) + '%' }} /></div>

                {state.next ? (
                  <>
                    {/* RECORD — the abstract is the focus, right up top */}
                    <div className="card" style={{ marginBottom: 14 }}><div className="bd">
                      <div className="rec-meta">{['Record ' + state.next.position + ' of ' + state.total, state.next.authors, state.next.year, state.next.source_db].filter(Boolean).join('  ·  ')}</div>
                      <div className="rec-title">{highlightByConcept(state.next.title, concepts) || '(no title)'}</div>
                      <div className="rec-abstract big">{highlightByConcept(state.next.abstract, concepts) || <span className="muted">(no abstract on file — use “Get full text”)</span>}</div>
                      {doiUrl(state.next.doi) && <div className="ft-getfull"><a className="ft-link" href={doiUrl(state.next.doi)} target="_blank" rel="noreferrer">Get full text ↗</a><span className="muted" style={{ fontSize: 11 }}>read the whole paper via your university access</span></div>}
                      <input ref={reasonRef} className="input" style={{ marginTop: 14 }} placeholder="Exclusion reason (optional · press R to jump here)"
                        value={reason} onChange={e => setReason(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') decide('exclude') }} />
                      {/* MECIR C40 carve-out (F3): don't exclude just because an outcome isn't REPORTED — only if it wasn't MEASURED */}
                      <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>
                        Excluding on the outcome? Only if the study didn’t <strong>measure</strong> it — never just because it didn’t <strong>report</strong> it (that’s a synthesis matter, MECIR C40).
                      </div>
                      <div className="decide">
                        <button className="inc" onClick={() => decide('include')}>Include<span className="k">I</span></button>
                        <button className="maybe" onClick={() => decide('uncertain')}>Maybe<span className="k">M</span></button>
                        <button className="exc" onClick={() => decide('exclude')}>Exclude<span className="k">E</span></button>
                      </div>
                    </div></div>

                    {/* CRITERIA — one tab per criterion; click to see its keywords + whether mentioned here */}
                    <div className="card"><div className="bd">
                      <div className="dlab" style={{ marginBottom: 8 }}>Eligibility criteria — click one to see its search terms</div>
                      <div className="crit-tabs">
                        {concepts.map(c => (
                          <button key={c.id} className={'crit-tab' + (c.id === tab ? ' on' : '')} onClick={() => setTab(c.id)} title={c.role}
                            style={c.id === tab ? { borderColor: c.color, color: c.text, background: c.color } : undefined}>
                            <span className="dot2" style={{ background: cov[c.id]?.matched ? (c.role === 'exclude' ? 'var(--exc)' : 'var(--inc)') : '#cbd5e1' }} />
                            {c.label}
                          </button>
                        ))}
                      </div>
                      {active ? (
                        <div style={{ marginTop: 12 }}>
                          <div style={{ fontSize: 12.5, marginBottom: 6 }}>
                            {activeCov?.matched
                              ? <span style={{ color: active.role === 'exclude' ? 'var(--exc)' : 'var(--inc)', fontWeight: 600 }}>{active.role === 'exclude' ? '⚠ exclusion vocabulary present' : '✓ mentioned in this record'}</span>
                              : <span className="muted">○ not mentioned in this title/abstract</span>}
                            {activeCov?.hits?.length ? <span className="muted"> — matched: {activeCov.hits.join(', ')}</span> : null}
                          </div>
                          <div className="chips">{(active.terms || []).map(t => <span key={t} className="chip" style={{ background: active.color, color: active.text }}>{t}</span>)}</div>
                          <div className="muted" style={{ fontSize: 10.5, marginTop: 8 }}>The search synonyms for this criterion — a presence cue, not a decision. Read the context (e.g. “support was NOT measured” still mentions support).</div>
                          {/* One-click: record the FAILED criterion as the exclusion reason (MECIR C41) instead of free-typing (F4) */}
                          <div style={{ marginTop: 8 }}>
                            <button className="btn" style={{ fontSize: 11.5, padding: '4px 10px' }}
                              onClick={() => setReason(active.role === 'exclude' ? `matched exclusion criterion: ${active.label}` : `failed criterion: ${active.label}`)}>
                              ✗ Use “{active.label}” as the exclusion reason
                            </button>
                            <span className="muted" style={{ fontSize: 10.5, marginLeft: 8 }}>fills the reason box below with this criterion — one click, no typing</span>
                          </div>
                        </div>
                      ) : <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>No criteria keywords yet — set them on Setup.</div>}
                      <div style={{ marginTop: 12, borderTop: '1px solid var(--line)', paddingTop: 10 }}>
                        <span className="muted" style={{ fontSize: 12, cursor: 'pointer' }} onClick={() => setShowCriteria(v => !v)}>{showCriteria ? '▾ Hide' : '▸ Show'} full eligibility criteria text</span>
                        {showCriteria && <pre className="crit" style={{ marginTop: 8 }}>{criteria || '(eligibility criteria not set yet)'}</pre>}
                      </div>
                    </div></div>
                  </>
                ) : (
                  <div className="card"><div className="bd">
                    <h2 style={{ marginTop: 0, color: 'var(--inc)' }}>✓ All {state.total} records screened for {who}</h2>
                    <p className="muted">Compile your blind decisions, then run the AI second screener — it screens the same records independently, and you reconcile the two.</p>
                    <button className="btn primary" onClick={() => api('/compile', { method: 'POST' }).then(r => alert(r.ok ? 'Compiled your screening decisions' + (r.removed_duplicates ? ` (removed ${r.removed_duplicates} duplicate rows)` : '') : 'Compile failed')).catch(e => alert(String(e)))}>
                      Compile my decisions
                    </button>
                    <RunAI stage="abstract" />
                  </div></div>
                )}

                {state.missing?.length > 0 && <div className="warn" style={{ marginTop: 14 }}>{state.missing.length} record(s) in your order are missing from your master records and were skipped.</div>}
              </>
            )}
      </div>
    </div>
  )
}
