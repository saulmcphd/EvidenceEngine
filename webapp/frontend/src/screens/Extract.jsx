import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api.js'

export default function Extract() {
  const [studies, setStudies] = useState(null)
  const [auditFile, setAuditFile] = useState(null)
  const [demo, setDemo] = useState(true)   // real-run flag from the backend: badge shows ONLY when no real audit
  const [rid, setRid] = useState('')
  const [detail, setDetail] = useState(null)
  const [agree, setAgree] = useState(null)
  const [blind, setBlind] = useState(true)   // blind-first is a non-negotiable: hide the AI value until the human records theirs
  const [draft, setDraft] = useState({})        // variable -> { human, consensus }
  const [err, setErr] = useState('')
  const [runMsg, setRunMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [pilot, setPilot] = useState(false)     // C43 pilot-and-revise: trial the form on the first N PDFs
  const [pilotN, setPilotN] = useState(3)        // 3-5 per Cochrane; extraction is token-expensive, so default 3
  const [pdfs, setPdfs] = useState(null)
  const fileRef = useRef(null)
  const pdfRef = useRef(null)

  const loadStudies = useCallback(() => {
    api('/extract/studies').then(d => { setStudies(d.studies || []); setAuditFile(d.audit_file); setDemo(d.demo !== false); setErr('') })
      .catch(e => setErr(String(e)))
    api('/extract/agreement').then(setAgree).catch(() => {})
  }, [])
  const loadPdfs = useCallback(() => api('/studies/pdfs').then(setPdfs).catch(() => {}), [])
  useEffect(() => { loadStudies(); loadPdfs() }, [loadStudies, loadPdfs])

  const uploadPdfs = () => {
    const fl = pdfRef.current?.files
    if (!fl || !fl.length) return
    const fd = new FormData(); [...fl].forEach(f => fd.append('files', f))
    fetch('/api/studies/upload-pdf', { method: 'POST', body: fd }).then(r => r.json())
      .then(d => { if (d.ok) { setPdfs(d); if (pdfRef.current) pdfRef.current.value = '' } else setErr(d.message || 'PDF upload failed') })
      .catch(e => setErr(String(e)))
  }
  const useFulltextPdfs = () => api('/studies/use-fulltext-pdfs', { method: 'POST' }).then(setPdfs).catch(e => setErr(String(e)))

  const loadDetail = useCallback(() => {
    if (!rid) { setDetail(null); return }
    api('/extract/detail?record_id=' + encodeURIComponent(rid)).then(d => { setDetail(d); setDraft({}) }).catch(e => setErr(String(e)))
  }, [rid])
  useEffect(() => { loadDetail() }, [loadDetail])

  const save = (variable, patch) => {
    api('/extract/value', { method: 'POST', body: { record_id: rid, variable, ...patch } })
      .then(() => { loadDetail(); loadStudies() }).catch(e => setErr(String(e)))
  }

  const runAI = () => {
    const n = Math.floor(Number(pilotN))
    if (pilot && !(n >= 1)) { setRunMsg('Enter how many studies to pilot (1 or more) — a ticked pilot with no count must not launch a full run.'); return }
    setBusy(true)
    setRunMsg(pilot ? `Piloting the AI extractor on the first ${n} PDF(s)…` : 'Running the AI extractor over your included-study PDFs…')
    api('/extract/run', { method: 'POST', body: { limit: pilot ? n : 0 } }).then(d => {
      setBusy(false)
      const msg = d.ok
        ? `AI extraction complete over ${d.pdfs} PDF(s)${d.pilot ? ' (pilot — reconcile these against the PDFs, revise the form, then run the rest)' : ''}${d.prompt_version ? ` · form ${d.prompt_version}` : ''}.`
        : (d.message || 'AI run could not complete.')
      setRunMsg(msg + (d.log ? '\n' + d.log : ''))
      loadStudies()
    }).catch(e => { setBusy(false); setRunMsg(String(e)) })
  }

  const upload = () => {
    const f = fileRef.current?.files?.[0]
    if (!f) return
    const fd = new FormData(); fd.append('file', f)
    fetch('/api/extract/upload', { method: 'POST', body: fd }).then(r => r.json()).then(d => {
      setRunMsg(d.ok ? `Uploaded ${d.rows} rows (${d.shape}) → ${d.audit_file}. Now run the AI to compare, then reconcile.` : (d.message || 'Upload failed'))
      loadStudies()
    }).catch(e => setErr(String(e)))
  }

  const a = agree?.agreement
  if (err) return <div className="warn">Could not load: {err}</div>

  return (
    <div>
      <div className="info" style={{ marginBottom: 14 }}>
        You extract the standardised fields from each included study (or upload a sheet you already finished); the AI is your
        <strong> second extractor</strong>; you reconcile <strong>every value</strong> — the reconciled <strong>Consensus</strong>,
        never the raw AI output, is the review's data (Cochrane C46). A value the AI invents that isn't in the source is a
        <strong> hallucination</strong> — surfaced here, never hidden. Each AI value shows its <strong>source quote/locus</strong>
        so you can check it against the paper; a value with <strong>no source</strong> is flagged (unverifiable). Record your
        value before peeking (blind-first).
      </div>

      {/* Included-study PDFs — the AI extractor (and §6 RoB rater) read these from PDFs/. Without them,
          "Run AI extractor" has nothing to read, so the upload lives right here. */}
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>Included-study PDFs</h2>
          <span className="muted" style={{ fontSize: 12 }}>{pdfs ? `${pdfs.count} PDF(s) ready for extraction` : '…'}</span>
        </div>
        <div className="bd">
          <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
            The AI extractor reads the full text of each <strong>included</strong> study.
            Upload them here (they stay on your machine). {pdfs?.fulltext_count ? <>You already uploaded <strong>{pdfs.fulltext_count}</strong> PDF(s) at full-text screening — copy them straight in.</> : null}
          </div>
          <input ref={pdfRef} type="file" accept=".pdf" multiple style={{ fontSize: 12 }} />
          <button className="btn primary" style={{ marginLeft: 8 }} onClick={uploadPdfs}>Upload study PDFs</button>
          {pdfs?.fulltext_count ? <button className="btn" style={{ marginLeft: 8 }} onClick={useFulltextPdfs}>Use my full-text PDFs ({pdfs.fulltext_count})</button> : null}
          {pdfs?.pdfs?.length ? <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>In the extraction set: {pdfs.pdfs.join(', ')}</div> : null}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 6 }}>
        {studies !== null && demo && <span className="demo-badge">DEMO · no real run yet</span>}
        <button className="btn" disabled={busy || (pilot && !(Math.floor(Number(pilotN)) >= 1))} onClick={runAI}>
          {busy ? 'Extracting…' : (pilot ? `▶ Pilot on first ${Math.floor(Number(pilotN)) >= 1 ? Math.floor(Number(pilotN)) : '…'}` : '▶ Run AI extractor')}
        </button>
        <input ref={fileRef} type="file" accept=".csv,.xlsx" style={{ fontSize: 12 }} />
        <button className="btn" onClick={upload}>⤓ Upload my extraction sheet</button>
        {auditFile && <span className="muted" style={{ fontSize: 11.5 }}>AI arm: <span className="mono">{auditFile}</span></span>}
      </div>
      <label style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        <input type="checkbox" checked={pilot} onChange={e => setPilot(e.target.checked)} />
        Pilot on the first
        <input className="input" type="number" min="1" style={{ width: 54 }} value={pilotN}
          onChange={e => setPilotN(e.target.value)} disabled={!pilot} />
        studies only
        <span className="muted"> — recommended before the full run: trial the form on 3–5 studies, reconcile them against the PDFs, revise the form, then extract the rest (Cochrane C43).</span>
      </label>

      {runMsg && <pre className="crit" style={{ marginBottom: 14, whiteSpace: 'pre-wrap' }}>{runMsg}</pre>}

      {/* agreement summary — DEMO; the headline numbers are HIDDEN until enough fields are reconciled,
          because on a blank audit they read as a fabricated 0%/100% result rather than a real metric. */}
      {a && (() => {
        const ready = (agree.reconciled_fields || 0) >= Math.max(5, Math.ceil((agree.total_fields || 0) * 0.6))
        return (
        <div className="card" style={{ marginBottom: 14 }}><div className="bd">
          <div style={{ display: 'flex', gap: 22, flexWrap: 'wrap', alignItems: 'baseline' }}>
            <div><span className="dlab">Field agreement (AI vs your values)</span>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'var(--mono)', color: 'var(--navy)' }}>
                {ready && a.overall_agreement != null ? (a.overall_agreement * 100).toFixed(0) + '%' : '—'}</div></div>
            <div><span className="dlab">Hallucination rate</span>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'var(--mono)', color: 'var(--exc)' }}>
                {ready && a.hallucination_rate != null ? (a.hallucination_rate * 100).toFixed(0) + '%' : '—'}</div></div>
            <div className="muted" style={{ fontSize: 11.5, maxWidth: 440 }}>
              <strong>DEMO — not a validated number.</strong> {ready
                ? <>Computed on {agree.reconciled_fields}/{agree.total_fields} reconciled fields; read the headline recall/agreement on the Reliability screen.</>
                : <>Reconcile the fields first ({agree.reconciled_fields || 0}/{agree.total_fields || 0} done) — on a blank audit these would read as a fabricated 0% / 100%, so they stay hidden until you've reconciled the study.</>}
            </div>
          </div>
        </div></div>
        )
      })()}

      {studies === null ? <div className="muted">Loading…</div>
        : !auditFile ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>No extraction yet</h2>
            <p className="muted" style={{ lineHeight: 1.7 }}>
              Two ways in: <strong>Run AI extractor</strong> (the AI extractor,
              over your included-study PDFs, with your own API key) — or
              <strong> upload an extraction sheet</strong> you already finished and just run the AI check. Then reconcile each field.
            </p>
          </div></div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '230px 1fr', gap: 16, alignItems: 'start' }}>
            <div className="card"><div className="bd" style={{ padding: 10 }}>
              <div className="dlab" style={{ marginBottom: 6 }}>Studies</div>
              {studies.map(s => (
                <div key={s.record_id} onClick={() => setRid(s.record_id)}
                  className={'study-item' + (s.record_id === rid ? ' on' : '')}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{s.record_id}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{s.reconciled}/{s.fields} reconciled</div>
                </div>
              ))}
            </div></div>

            <div>
              {!detail ? <div className="muted">Pick a study to extract / reconcile.</div>
                : detail.error ? <div className="warn">{detail.message}</div>
                : (
                <div className="card"><div className="bd">
                  <div className="rec-title" style={{ fontSize: 16, margin: 0 }}>{detail.title || detail.record_id}</div>
                  <div className="rec-meta" style={{ marginBottom: 6 }}>{[detail.authors, detail.year].filter(Boolean).join(' · ')} · {detail.record_id}</div>
                  {detail.ai_confidence !== '' && detail.ai_confidence != null && (
                    <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
                      AI self-reported extraction confidence {detail.ai_confidence} — uncalibrated; it is the AI's own claim, not a reconcilable value.
                    </div>
                  )}
                  <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <input type="checkbox" checked={blind} onChange={e => setBlind(e.target.checked)} /> Blind entry (hide AI values until I record mine)
                  </label>
                  <div style={{ overflowX: 'auto' }}>
                  <table className="ext-table">
                    <thead><tr><th>Field</th><th>AI value</th><th>Source (AI)</th><th>Your value</th><th></th><th>Consensus</th><th></th></tr></thead>
                    <tbody>
                      {detail.fields.map(f => (
                        <tr key={f.variable} className={f.hallucination ? 'hallu' : ''}>
                          <td className="mono" style={{ fontSize: 11.5 }}>{f.variable}{f.hallucination && <span className="hflag">⚠ hallucination</span>}</td>
                          <td style={{ fontSize: 12 }}>{blind && !f.human ? <span className="muted">hidden</span> : (f.ai || <span className="muted">—</span>)}</td>
                          <td style={{ fontSize: 11, maxWidth: 210 }}>
                            {blind && !f.human ? <span className="muted">hidden</span>
                              : f.source_locus
                                ? <span className="muted" title={f.source_locus}>“{f.source_locus.length > 90 ? f.source_locus.slice(0, 90) + '…' : f.source_locus}”</span>
                                : f.no_locus ? <span className="hflag" title="AI gave a value with no source — verify against the paper">⚠ no source</span>
                                  : <span className="muted">—</span>}
                          </td>
                          <td><input className="input ext-in" defaultValue={f.human}
                            onBlur={e => e.target.value !== f.human && save(f.variable, { human: e.target.value })} /></td>
                          <td>{f.match === 'Y' ? <span className="mchip ok">✓</span> : f.match === 'N' ? <span className="mchip no">✕</span> : ''}</td>
                          <td><input className="input ext-in" defaultValue={f.consensus}
                            onBlur={e => e.target.value !== f.consensus && save(f.variable, { consensus: e.target.value })} /></td>
                          <td>{f.error_category && <span className="muted" style={{ fontSize: 10.5 }}>{f.error_category}</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                  <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
                    Edit a cell and click away to save it straight into the audit file the engine reads. The study's knowledge
                    node is marked human-verified once <strong>every extraction field shown here</strong> is reconciled
                    (structurally-inapplicable “Not applicable” cells and the risk-of-bias domains are handled separately, so
                    they don't block it). Outcome/results data must be reconciled in duplicate (C46).
                  </p>
                </div></div>
              )}
            </div>
          </div>
        )}
    </div>
  )
}
