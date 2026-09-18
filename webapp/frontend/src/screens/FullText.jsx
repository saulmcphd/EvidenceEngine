import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api.js'
import { highlightByConcept, CoverageStrip } from '../concepts.jsx'
import RunAI from '../RunAI.jsx'
import UploadScreened from '../UploadScreened.jsx'

const doiUrl = (doi) => {
  const d = String(doi || '').trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')
  return d ? 'https://doi.org/' + d : ''
}

export default function FullText() {
  const [screeners, setScreeners] = useState([])
  const [who, setWho] = useState('')
  const [state, setState] = useState(null)
  const [reason, setReason] = useState('')
  const [quote, setQuote] = useState('')
  const [interesting, setInteresting] = useState(false)   // interesting-but-ineligible bookmark on an exclude (F2)
  const [lang, setLang] = useState('')
  const [found, setFound] = useState(null)
  const [showUpload, setShowUpload] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [msgOk, setMsgOk] = useState(false)   // awaiting success is info-styled, not an amber warning
  const fileRef = useRef(null)
  const checkTimer = useRef(null)

  useEffect(() => {
    api('/screeners').then(d => {
      setScreeners(d.screeners || [])
      if (d.screeners && d.screeners.length) setWho(d.screeners[0])
    }).catch(e => setErr(String(e)))
  }, [])

  const load = useCallback(() => {
    if (!who) return
    api('/fulltext/worklist?screener=' + encodeURIComponent(who))
      .then(d => { setState(d); setReason(''); setQuote(''); setInteresting(false); setLang(''); setFound(null); setMsg(''); setShowUpload(false) })
      .catch(e => setErr(String(e)))
  }, [who])
  useEffect(() => { if (who) load() }, [who, load])

  // debounced verbatim quote-back check (only meaningful when a PDF is on file)
  useEffect(() => {
    if (!state?.next || !quote.trim()) { setFound(null); return }
    clearTimeout(checkTimer.current)
    checkTimer.current = setTimeout(() => {
      api('/fulltext/quotecheck', { method: 'POST', body: { record_id: state.next.record_id, quote } })
        .then(setFound).catch(() => setFound(null))
    }, 450)
    return () => clearTimeout(checkTimer.current)
  }, [quote, state])

  const decide = (decision) => {
    if (!state?.next) return
    api('/fulltext/decision', {
      method: 'POST',
      body: { screener: who, record_id: state.next.record_id, decision, reason, supporting_quote: quote, interesting },
    }).then(d => {
      // surface ANY guard message (need_reason_quote, MECIR C40 reporting-only, …) rather than crashing on it
      if (d.error) { setMsg(d.message || d.error); setMsgOk(false); return }
      setState(d); setReason(''); setQuote(''); setInteresting(false); setLang(''); setFound(null); setShowUpload(false)
      setMsg(d.last_flag ? '⚠ ' + d.last_flag : ''); setMsgOk(false)
    }).catch(e => setErr(String(e)))
  }

  // "Can't GET / can't READ this paper" → Studies Awaiting Classification (NOT an exclusion).
  const awaiting = (why) => {
    if (!state?.next || !why.trim()) return
    api('/fulltext/decision', {
      method: 'POST',
      body: { screener: who, record_id: state.next.record_id, decision: 'awaiting', awaiting_reason: why },
    }).then(d => {
      if (d.error) { setMsg(d.message || d.error); setMsgOk(false); return }
      setState(d); setReason(''); setQuote(''); setInteresting(false); setLang(''); setFound(null); setShowUpload(false)
      setMsg('→ Sent to Studies Awaiting Classification (not excluded).'); setMsgOk(true)
    }).catch(e => setErr(String(e)))
  }

  const undo = () => api('/fulltext/undo', { method: 'POST', body: { screener: who } }).then(setState).catch(e => setErr(String(e)))

  const upload = () => {
    const f = fileRef.current?.files?.[0]
    if (!f || !state?.next) return
    const fd = new FormData(); fd.append('record_id', state.next.record_id); fd.append('file', f)
    fetch('/api/fulltext/upload', { method: 'POST', body: fd }).then(() => load()).catch(e => setErr(String(e)))
  }

  if (err) return <div className="warn">Could not load: {err}</div>
  if (!screeners.length) return <div className="info">No per-screener orders yet — set up Search &amp; records first.</div>

  const rec = state?.next
  const url = rec ? doiUrl(rec.doi) : ''

  return (
    <div style={{ maxWidth: 760 }}>
      {/* Entry point B — the same "upload your decisions" door as the abstract screen (shared component) */}
      <UploadScreened stage="fulltext" />
      <div className="info" style={{ marginBottom: 14 }}>
        Only records you kept at abstract stage appear here. Read the <strong>full paper</strong> (open it with the link under
        the abstract — your library/university access), then decide <strong>Include / Exclude</strong>. Every Exclude needs ONE
        primary reason and a <strong>verbatim quote</strong> from the paper. Can’t get or can’t read a paper? Send it to
        <strong> Awaiting Classification</strong> (below) — never a silent exclude. Blind: the AI's calls stay hidden until reconciliation.
      </div>

      <div style={{ display: 'flex', gap: 14, alignItems: 'center', marginBottom: 14 }}>
        <span className="blind-badge">● BLIND ON</span>
        <select className="select" style={{ width: 200 }} value={who} onChange={e => setWho(e.target.value)}>
          {screeners.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {state && !state.error && (
          <span className="muted" style={{ fontSize: 12 }}>
            {state.decided} of {state.total} full texts assessed
            {(state.counts?.awaiting > 0) && <span style={{ color: 'var(--maybe)', marginLeft: 8 }}>· {state.counts.awaiting} awaiting</span>}
            {/* Undo only removes an IN-APP decision — decided also counts imported ones, which undo can't touch */}
            {((state.counts?.include || 0) + (state.counts?.exclude || 0) + (state.counts?.awaiting || 0)) > 0 &&
              <span style={{ color: 'var(--blue)', cursor: 'pointer', fontWeight: 600, marginLeft: 10 }} onClick={undo}>↶ Undo last</span>}
          </span>
        )}
      </div>

      {!state ? <div className="muted">Loading…</div>
        : state.error ? <div className="warn">{state.message || state.error}</div>
        : !rec ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0, color: 'var(--inc)' }}>✓ All {state.total} full texts assessed for {who}</h2>
            <p className="muted">Now run the AI second screener over the same full texts — it decides independently, and you reconcile the two.</p>
            <RunAI stage="fulltext" />
          </div></div>
        ) : (
          <>
            <div className="card" style={{ marginBottom: 12 }}><div className="bd" style={{ paddingTop: 12, paddingBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--muted)' }}>
                <span>{state.decided} of {state.total} assessed</span><span className="mono">{rec.record_id}</span>
              </div>
              <div className="progress"><div style={{ width: (state.total ? (state.decided / state.total * 100) : 0) + '%' }} /></div>
            </div></div>

            {/* record: title + abstract + the get-full-text link underneath */}
            <div className="card" style={{ marginBottom: 12 }}><div className="bd">
              <div className="rec-title">{highlightByConcept(rec.title, state.concepts) || '(no title)'}</div>
              <div className="rec-meta">{[rec.authors, rec.year].filter(Boolean).join('  ·  ')}</div>
              <div className="rec-abstract">{highlightByConcept(rec.abstract, state.concepts) || <span className="muted">(no abstract on file)</span>}</div>
              <CoverageStrip coverage={rec.coverage} />

              <div className="ft-getfull">
                {url
                  ? <a className="btn primary" href={url} target="_blank" rel="noreferrer">Get full text ↗</a>
                  : <span className="muted" style={{ fontSize: 12.5 }}>No DOI on file for this record — locate the paper in your library catalogue.</span>}
                {url && <span className="muted" style={{ fontSize: 11.5 }}>Opens <span className="mono">{url}</span> — download &amp; read via your university access, then decide below.</span>}
              </div>
            </div></div>

            {/* decision */}
            <div className="card"><div className="bd">
              <h2 className="hd-inline">Eligibility decision</h2>
              <details style={{ margin: '8px 0' }}>
                <summary className="muted" style={{ cursor: 'pointer', fontSize: 12 }}>Eligibility criteria</summary>
                <pre className="crit" style={{ marginTop: 8 }}>{state.criteria || '(eligibility criteria not set yet)'}</pre>
              </details>

              <label style={{ fontSize: 11.5, fontWeight: 600, color: '#4b5563' }}>If excluding — primary reason</label>
              <select className="select" style={{ marginTop: 4 }} value={reason} onChange={e => setReason(e.target.value)}>
                <option value="">— choose a reason —</option>
                {(state.reasons || []).map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              {/* MECIR C40 reminder (F3) — the backend also soft-blocks a reporting-only exclude */}
              <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>
                MECIR C40: never exclude just because an outcome isn’t <strong>reported</strong> (that’s a synthesis / reporting-bias matter). Only exclude on the outcome if the study didn’t <strong>measure</strong> it.
              </div>

              <label style={{ fontSize: 11.5, fontWeight: 600, color: '#4b5563', display: 'block', marginTop: 12 }}>
                Verbatim supporting quote (paste the exact sentence from the paper you read)
              </label>
              <textarea className="input" style={{ height: 70, marginTop: 4 }} value={quote}
                onChange={e => setQuote(e.target.value)} placeholder="Paste the exact sentence from the paper that proves the failed criterion" />
              {quote.trim() && found && (
                found.found
                  ? <div style={{ color: 'var(--inc)', fontSize: 12, marginTop: 4 }}>✓ quote found in the uploaded PDF</div>
                  : <div style={{ color: found.has_pdf ? 'var(--exc)' : 'var(--muted)', fontSize: 12, marginTop: 4 }}>
                      {found.has_pdf ? '✗ not found in the uploaded PDF — your exclude is still recorded, but flagged to re-verify the quote at reconciliation' : 'no PDF uploaded — your quote is recorded but not auto-verified'}
                    </div>
              )}

              <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                For a non-English paper, base any <strong>Exclude</strong> on a proficient reader’s reading of the full
                text — not a machine translation. If you can’t read it, use “Can’t read the language” below (that parks
                it, it doesn’t exclude it).
              </p>

              {/* optional: upload the PDF so the quote-back guard can auto-verify the exclusion */}
              <div style={{ marginTop: 10 }}>
                {!showUpload
                  ? <span className="muted" style={{ fontSize: 11.5, cursor: 'pointer' }} onClick={() => setShowUpload(true)}>
                      {rec.has_pdf ? '✓ a PDF is on file — your quote will be auto-checked · re-upload' : '＋ Have the PDF on this computer? Upload it to auto-check your quote'}
                    </span>
                  : <div style={{ fontSize: 12 }}>
                      <input ref={fileRef} type="file" accept="application/pdf" />
                      <button className="btn" style={{ marginLeft: 8 }} onClick={upload}>Upload</button>
                      <span className="muted" style={{ marginLeft: 8 }}>optional — only to auto-verify the exclusion quote</span>
                    </div>}
              </div>

              {msg && <div className={msgOk ? 'info' : 'warn'} style={{ marginTop: 12 }}>{msg}</div>}

              {/* interesting-but-ineligible bookmark (F2) — a tag on an Exclude, never the included set */}
              <label style={{ display: 'flex', gap: 6, alignItems: 'flex-start', marginTop: 12, fontSize: 12, color: '#374151' }}>
                <input type="checkbox" checked={interesting} onChange={e => setInteresting(e.target.checked)} style={{ marginTop: 2 }} />
                <span>Interesting but ineligible — bookmark this study for the background/discussion and reference-list mining. It stays an <strong>Exclude</strong> with its failed-criterion reason and never enters the included set. <span className="muted">(applies when you Exclude)</span></span>
              </label>
              <div className="decide" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <button className="inc" onClick={() => decide('include')}>Include</button>
                <button className="exc" onClick={() => decide('exclude')}>Exclude</button>
              </div>
              <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>No “Maybe” at full text — the whole paper is available, so the call is definitive.</p>

              {/* Can't GET / can't READ this paper → Studies Awaiting Classification (NOT an exclusion) */}
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
                <h2 className="hd-inline" style={{ fontSize: 12.5 }}>Can’t get or can’t read this paper?</h2>
                <p className="muted" style={{ fontSize: 11.5, margin: '2px 0 8px', lineHeight: 1.5 }}>
                  If you can’t obtain the full text (try your library → open access → a colleague at another institution →
                  email the author) or it’s in a language you can’t read, <strong>don’t exclude it</strong> — send it to
                  <strong> Studies Awaiting Classification</strong>. It stays in the PRISMA flow, so a hard-to-get paper
                  never becomes a silent exclusion.
                </p>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <button className="btn" onClick={() => awaiting('Full text could not be obtained')}>Can’t get the full text</button>
                  <button className="btn" onClick={() => awaiting(lang.trim()
                    ? `Not in a language I can read (${lang.trim()}) — needs a proficient screener`
                    : 'Not in a language I can read — needs a proficient screener')}>Can’t read the language</button>
                  <input className="input" style={{ width: 150 }} placeholder="language (e.g. Chinese)"
                    value={lang} onChange={e => setLang(e.target.value)} />
                </div>
                <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  A rough machine translation is fine to <em>keep</em> a record at abstract stage, but a full-text
                  include/exclude needs a proficient reader — this flags it for one (record the translation method later).
                </p>
              </div>
            </div></div>
          </>
        )}
    </div>
  )
}
