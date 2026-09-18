import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// Severity RANK per tool for the "overall = worst domain" guidance. ROBINS-I 'No information' is NOT
// a severity — it means the evidence to judge is missing — so it is excluded from the worst-domain
// calc (it must never outrank Critical, which would hide a synthesis-excluding result).
const RANK = {
  RoB2: { 'Low': 0, 'Some concerns': 1, 'High': 2 },
  'ROBINS-I': { 'Low': 0, 'Moderate': 1, 'Serious': 2, 'Critical': 3 },
}
const pillClass = (v) => {
  const s = String(v || '').toLowerCase()
  if (s === 'low') return 'inc'
  if (s.includes('some concern') || s === 'moderate') return 'maybe'
  if (s === 'high' || s === 'serious' || s === 'critical') return 'exc'
  return ''
}
// Notable-concern-COI pill colour (a SEPARATE judgement, not a bias level). 'no notable' must be tested
// before 'notable concern' since the former contains the latter.
const coiPill = (v) => {
  const s = String(v || '').toLowerCase()
  if (s.includes('no notable')) return 'inc'
  if (s.includes('notable concern')) return 'exc'
  return 'maybe'
}

export default function RoB() {
  const [studies, setStudies] = useState(null)
  const [auditFile, setAuditFile] = useState(null)
  const [demo, setDemo] = useState(true)   // real-run flag from the backend: badge shows ONLY when there is no real audit (F5)
  const [rid, setRid] = useState('')
  const [detail, setDetail] = useState(null)
  const [blind, setBlind] = useState(true)   // blind-first is the standard: rate each domain BEFORE seeing the AI (concept-blind-first-validation), matching the extraction screen; untick to reconcile
  const [toolOverride, setToolOverride] = useState('')
  const [err, setErr] = useState('')
  const [runMsg, setRunMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const loadStudies = useCallback(() => {
    api('/rob/studies').then(d => { setStudies(d.studies || []); setAuditFile(d.audit_file); setDemo(d.demo !== false); setErr('') })
      .catch(e => setErr(String(e)))
  }, [])
  useEffect(() => { loadStudies() }, [loadStudies])

  const loadDetail = useCallback(() => {
    if (!rid) { setDetail(null); return }
    api('/rob/detail?record_id=' + encodeURIComponent(rid) + '&blind=' + (blind ? 'true' : 'false')
      + (toolOverride ? '&tool=' + encodeURIComponent(toolOverride) : ''))
      .then(setDetail).catch(e => setErr(String(e)))
  }, [rid, blind, toolOverride])
  useEffect(() => { loadDetail() }, [loadDetail])
  useEffect(() => { setToolOverride('') }, [rid])   // reset the design override when switching study

  const judge = (domain, field, value) => {
    api('/rob/judge', { method: 'POST', body: { record_id: rid, domain, [field]: value } })
      .then(() => { loadDetail(); loadStudies() }).catch(e => setErr(String(e)))
  }

  const runAI = () => {
    setBusy(true); setRunMsg('Running the AI second rater over your included-study PDFs…')
    api('/rob/run', { method: 'POST' }).then(d => {
      setBusy(false)
      setRunMsg(d.ok ? `AI run complete over ${d.pdfs} PDF(s). Reload the study list.` : (d.message || 'AI run could not complete — see the note.') + (d.log ? '\n' + d.log : ''))
      loadStudies()
    }).catch(e => { setBusy(false); setRunMsg(String(e)) })
  }

  const overall = (() => {
    if (!detail || !detail.domains) return null
    const rank = RANK[detail.tool] || {}
    const ranked = detail.domains.map(d => d.consensus).filter(v => v in rank)   // 'No information' excluded
    if (!ranked.length) return null
    return ranked.reduce((w, v) => (rank[v] > rank[w] ? v : w), ranked[0])
  })()

  if (err) return <div className="warn">Could not load: {err}</div>

  return (
    <div>
      <div className="info" style={{ marginBottom: 12 }}>
        <strong>One profile per study, for now.</strong> This screen records a single risk-of-bias profile for each
        study. RoB&nbsp;2 guidance recommends a <strong>separate profile for each primary result</strong> within a study
        (an RCT reporting two primary outcomes should get two profiles). Multi-result assessment is on the roadmap — for
        now, assess the <strong>most critical outcome</strong> and note any others in the overall judgement.
      </div>
      <div className="info" style={{ marginBottom: 14 }}>
        Risk of bias uses the <strong>design-appropriate tool</strong> — RoB&nbsp;2 for randomised trials, ROBINS-I for
        non-randomised (legacy tools are comparison-only). The AI proposes a per-domain answer and a verbatim quote as
        your <strong>second rater</strong>; you reconcile every domain and finalise the overall judgement. High risk of
        bias is <strong>not</strong> an exclusion — it feeds sensitivity analysis and GRADE.
      </div>

      <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
        {studies !== null && demo && <span className="demo-badge">DEMO · no real run yet</span>}
        <button className="btn" disabled={busy} onClick={runAI}>▶ Run AI second rater</button>
        {auditFile && <span className="muted" style={{ fontSize: 11.5 }}>AI arm: <span className="mono">{auditFile}</span></span>}
        <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
          <input type="checkbox" checked={blind} onChange={e => setBlind(e.target.checked)} /> Blind round (hide the AI while I rate)
        </label>
      </div>

      {runMsg && <pre className="crit" style={{ marginBottom: 14, whiteSpace: 'pre-wrap' }}>{runMsg}</pre>}

      {studies === null ? <div className="muted">Loading…</div>
        : !auditFile ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>No AI risk-of-bias assessment yet</h2>
            <p className="muted" style={{ lineHeight: 1.7 }}>
              The AI second rater (design-branched RoB 2 / ROBINS-I) runs over your
              included-study PDFs with your own API key. Add the PDFs and
              click <strong>Run AI second rater</strong> — or upload a finished extraction sheet on the Data-extraction screen
              (the two stages share one audit file). Then you reconcile each domain here.
            </p>
          </div></div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '230px 1fr', gap: 16, alignItems: 'start' }}>
            {/* study rail */}
            <div className="card"><div className="bd" style={{ padding: 10 }}>
              <div className="dlab" style={{ marginBottom: 6 }}>Included studies</div>
              {studies.map(s => (
                <div key={s.record_id} onClick={() => setRid(s.record_id)}
                  className={'study-item' + (s.record_id === rid ? ' on' : '')}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{s.record_id}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{s.tool} · {s.rob_reconciled} reconciled</div>
                  {!s.in_included_set && <div style={{ fontSize: 10, color: 'var(--maybe)' }}>not in full-text includes</div>}
                </div>
              ))}
            </div></div>

            {/* domain grid */}
            <div>
              {!detail ? <div className="muted">Pick a study to assess.</div>
                : detail.error ? <div className="warn">{detail.message}</div>
                : detail.needs_design ? (
                  <div className="card"><div className="bd">
                    <h2 style={{ marginTop: 0 }}>Which tool? Set the study design first</h2>
                    <p className="muted" style={{ lineHeight: 1.7 }}>
                      The risk-of-bias tool must follow the <strong>design</strong>, not a default — RoB&nbsp;2 for a
                      randomised trial, ROBINS-I for a non-randomised study. The design couldn't be resolved automatically
                      {detail.ai_design ? <> (the AI read it as “{detail.ai_design}”)</> : null}, so choose it:
                    </p>
                    <div style={{ display: 'flex', gap: 10 }}>
                      <button className="btn primary" onClick={() => setToolOverride('RoB2')}>Randomised → RoB 2</button>
                      <button className="btn primary" onClick={() => setToolOverride('ROBINS-I')}>Non-randomised → ROBINS-I</button>
                    </div>
                    <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>Legacy tools (Jadad/EPHPP/RoB 1) are comparison-only, never the primary tool.</p>
                  </div></div>
                ) : (
                <>
                  <div className="card" style={{ marginBottom: 12 }}><div className="bd">
                    <div className="rec-title" style={{ fontSize: 16, margin: 0 }}>{detail.title || detail.record_id}</div>
                    <div className="rec-meta">{[detail.authors, detail.year].filter(Boolean).join(' · ')} · {detail.record_id}</div>
                    <div style={{ marginTop: 8, fontSize: 13 }}>
                      Tool (by design): <strong>{detail.tool}</strong>
                      {overall && <> · overall (worst reconciled domain): <span className={'pill ' + pillClass(overall)}>{overall}</span></>}
                    </div>
                    {blind && <div className="info" style={{ marginTop: 10 }}>Blind round on — the AI's judgements are hidden while you rate. Turn it off to reconcile.</div>}
                  </div></div>

                  {detail.domains.map(d => (
                    <div key={d.key} className="card" style={{ marginBottom: 10 }}><div className="bd">
                      <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--navy)' }}>{d.label}</div>
                      <div className="rob-grid">
                        <div>
                          <div className="dlab">AI (2nd rater)</div>
                          {blind ? <span className="muted" style={{ fontSize: 12 }}>hidden</span>
                            : d.ai_judgment ? <span className={'pill ' + pillClass(d.ai_judgment)}>{d.ai_judgment}</span>
                            : <span className="muted" style={{ fontSize: 12 }}>—</span>}
                          {!blind && d.ai_quote && <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>“{d.ai_quote}”</div>}
                        </div>
                        <div>
                          <div className="dlab">Your judgement</div>
                          <select className="select" value={d.human || ''} onChange={e => judge(d.key, 'human', e.target.value)}>
                            <option value="">—</option>
                            {detail.levels.map(l => <option key={l} value={l}>{l}</option>)}
                          </select>
                        </div>
                        <div>
                          <div className="dlab">Consensus</div>
                          <select className="select" value={d.consensus || ''} onChange={e => judge(d.key, 'consensus', e.target.value)}>
                            <option value="">—</option>
                            {detail.levels.map(l => <option key={l} value={l}>{l}</option>)}
                          </select>
                        </div>
                      </div>
                    </div></div>
                  ))}
                  <p className="muted" style={{ fontSize: 11.5 }}>
                    Each domain needs a verbatim quote behind the AI's call; reconcile every one. The overall rating is at
                    least as severe as the worst domain — and a single ROBINS-I <em>Critical</em> result is excluded from
                    synthesis (the one rating-driven exclusion), but the study stays in the review.
                  </p>

                  {/* Funding & COI — RECORDED, NOT SCORED (Cochrane §7.8.3/§7.8.6). Deliberately OUTSIDE the domain
                      grid + the worst-domain roll-up, which read detail.domains only. */}
                  {detail.coi && (() => {
                    const nc = detail.coi.notable_concern || {}
                    return (
                    <div className="card" style={{ marginBottom: 10, borderLeft: '3px solid var(--maybe)' }}><div className="bd">
                      <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--navy)' }}>Funding &amp; conflicts of interest
                        <span className="muted" style={{ fontWeight: 400, fontSize: 11.5 }}> — recorded, not scored</span></div>
                      <div className="muted" style={{ fontSize: 11.5, margin: '4px 0 10px', lineHeight: 1.5 }}>
                        Cochrane keeps conflicts of interest OUT of the bias domains (§7.8.3) — they do not change any domain
                        rating above. The facts below come from data extraction (reconcile them there); the separate
                        <strong> notable-concern</strong> judgement is yours to set here. It may inform the <em>Selection of
                        the reported result</em> domain only when the study's analysis plan is missing — a merely hypothetical
                        conflict is <strong>not</strong> a notable concern (§7.8.6).
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, fontSize: 12, marginBottom: 12 }}>
                        <div><div className="dlab">Funding source</div><div>{detail.coi.funding_source || <span className="muted">—</span>}</div></div>
                        <div><div className="dlab">Author conflicts</div><div>{detail.coi.author_conflicts || <span className="muted">—</span>}</div></div>
                        <div><div className="dlab">Funder role</div><div>{detail.coi.funder_role || <span className="muted">—</span>}</div></div>
                      </div>
                      <div className="rob-grid">
                        <div>
                          <div className="dlab">AI (2nd rater)</div>
                          {blind ? <span className="muted" style={{ fontSize: 12 }}>hidden</span>
                            : nc.ai_judgment ? <span className={'pill ' + coiPill(nc.ai_judgment)}>{nc.ai_judgment}</span>
                            : <span className="muted" style={{ fontSize: 12 }}>—</span>}
                          {!blind && nc.ai_rationale && <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>{nc.ai_rationale}{nc.ai_who ? ` — ${nc.ai_who}` : ''}{nc.ai_stage ? ` (${nc.ai_stage})` : ''}</div>}
                        </div>
                        <div>
                          <div className="dlab">Your judgement</div>
                          <select className="select" value={nc.human || ''} onChange={e => judge(nc.var, 'human', e.target.value)}>
                            <option value="">—</option>
                            {(nc.levels || []).map(l => <option key={l} value={l}>{l}</option>)}
                          </select>
                        </div>
                        <div>
                          <div className="dlab">Consensus</div>
                          <select className="select" value={nc.consensus || ''} onChange={e => judge(nc.var, 'consensus', e.target.value)}>
                            <option value="">—</option>
                            {(nc.levels || []).map(l => <option key={l} value={l}>{l}</option>)}
                          </select>
                        </div>
                      </div>
                    </div></div>
                    )
                  })()}
                </>
              )}
            </div>
          </div>
        )}
    </div>
  )
}
