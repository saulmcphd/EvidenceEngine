import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// Stage 8 — Synthesis. Bring the included studies' findings together. Grounded in
// concept-synthesis-without-meta-analysis (Cochrane Ch.12 / McLeod Step 8) + concept-dual-screening: an evidence
// table assembled from the extraction audit + a GUIDED narrative-synthesis workspace. HUMAN-FIRST spine: you write
// each section; the AI can give an INDEPENDENT second-opinion draft (its own store, never overwriting yours); you
// compare and Accept (reconcile) it, which flips human_verified on the AI draft's provenance node. The AI is a
// second drafter, never the sole synthesist. GRADE certainty is always a human judgement (not AI-drafted).

const SOF_CERTAINTY = ['High', 'Moderate', 'Low', 'Very low']   // GRADE levels, graded per outcome (never averaged)

export default function Synthesis() {
  const [st, setSt] = useState(null)
  const [fields, setFields] = useState({})
  const [aiDrafts, setAiDrafts] = useState({})
  const [sof, setSof] = useState([])
  const [busy, setBusy] = useState(false)
  const [drafting, setDrafting] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => api('/synthesis/state')
    .then(d => { setSt(d); setFields(d.fields || {}); setSof(d.sof || []); setAiDrafts(d.ai_drafts || {}) })
    .catch(e => setErr(String(e))), [])
  useEffect(() => { load() }, [load])

  const setF = (k, v) => setFields(f => ({ ...f, [k]: v }))
  const addSofRow = () => setSof(s => [...s, { outcome: '', n_studies: '', certainty: '', reason: '' }])
  const setSofCell = (i, k, v) => setSof(s => s.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  const delSofRow = (i) => setSof(s => s.filter((_, j) => j !== i))

  const save = () => Promise.all([
    api('/synthesis/fields', { method: 'POST', body: { fields } }),
    api('/synthesis/sof', { method: 'POST', body: { rows: sof } }),
  ]).then(() => { setMsg('Saved your synthesis notes.'); load() }).catch(e => setErr(String(e)))

  // Independent AI second-opinion draft. Persist the current text first so "only empty" is accurate and the AI
  // drafts blind of any section you're mid-typing. The draft lands in a SEPARATE store — never your text.
  const getAiDrafts = async (onlyEmpty = true, sections = null) => {
    setDrafting(true); setErr(''); setMsg('')
    try {
      await api('/synthesis/fields', { method: 'POST', body: { fields } })
      const body = { only_empty: onlyEmpty }
      if (sections) body.sections = sections
      const d = await api('/synthesis/ai-draft', { method: 'POST', body })
      if (d.ok) { setAiDrafts(d.ai_drafts || {}); setMsg(d.message) } else { setErr(d.message || 'AI draft failed.') }
    } catch (e) { setErr(String(e)) }
    setDrafting(false)
  }
  const getAiDraftFor = (key) => getAiDrafts(false, [key])   // second opinion for one section, even if you wrote one

  const acceptDraft = async (key) => {
    setErr(''); setMsg('')
    try {
      const d = await api('/synthesis/accept', { method: 'POST', body: { key } })
      if (d.ok) {
        setFields(f => ({ ...f, [key]: (d.fields || {})[key] || '' }))   // only the accepted key; keep unsaved edits elsewhere
        setAiDrafts(d.ai_drafts || {})
        setMsg('Accepted the AI draft as your text — you can still edit it, then Save.')
      } else { setErr(d.message || 'Could not accept the draft.') }
    } catch (e) { setErr(String(e)) }
  }

  const generate = async () => {
    setBusy(true); setErr(''); setMsg('')
    try {
      await api('/synthesis/fields', { method: 'POST', body: { fields } })
      await api('/synthesis/sof', { method: 'POST', body: { rows: sof } })
      const d = await api('/synthesis/generate', { method: 'POST', body: {} })
      if (d.ok) { setMsg(d.message); load() } else { setErr(d.message || 'Generation failed.') }
    } catch (e) { setErr(String(e)) }
    setBusy(false)
  }

  if (!st) return <div className="card"><div className="bd muted">Loading the synthesis workspace…</div></div>
  const t = st.table || {}
  const ai = st.ai || {}
  const canDraft = ai.key_present && t.n_included

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 1080 }}>
      <div className="info">
        The synthesis brings the findings of your <strong>included studies</strong> together to answer the review
        question — it does <strong>not</strong> just summarise each study in turn. You write the narrative below; you
        can also ask the AI for an <strong>independent second-opinion draft</strong> per section to compare against —
        but <strong>you</strong> accept and reconcile it, the AI is never the sole author. The golden rule:{' '}
        <strong>weigh the strength and quality of the evidence, never count votes</strong> (don’t tally
        “X of Y studies were positive”), and “we don’t know” is a legitimate finding.
      </div>
      {err && <div className="warn">{err}</div>}

      {/* evidence table */}
      <div className="card">
        <div className="hd"><h2>Characteristics of included studies</h2></div>
        <div className="bd">
          <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
            {t.n_included
              ? <>{t.n_included} included {t.n_included === 1 ? 'study' : 'studies'} (set decided by {t.decided_by}{t.reconciled ? '' : ' — not yet reconciled'}). {t.has_extraction ? 'Filled from your extraction data; blank cells were not extracted.' : 'No extraction data yet — run Data extraction (step 7) to fill the columns.'}</>
              : <>No included studies with data yet. Complete screening (5a–5c) and Data extraction (step 7) first; this table and the synthesis fill from there.</>}
          </div>
          {t.any_unreconciled && (
            <div className="warn" style={{ fontSize: 12, marginBottom: 10 }}>
              ⚠ Cells marked <strong>⚠</strong> below are the AI's <strong>raw extraction</strong>, which you have not yet
              reviewed/reconciled — they are provisional, not the review's data. Reconcile them on the
              <strong> Data extraction</strong> screen before you rely on this table or draft the synthesis.
            </div>
          )}
          {t.rows && t.rows.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table className="ext-table">
                <thead><tr><th>Reference</th><th>Design</th><th>Population</th><th>Intervention / Exposure</th><th>Outcome</th><th>Results</th></tr></thead>
                <tbody>
                  {t.rows.map(r => {
                    const Cell = (v, unrec) => v
                      ? <>{v}{unrec && <span className="warn" title="AI's raw extraction — not yet reconciled" style={{ marginLeft: 4, padding: '0 4px', borderRadius: 3, fontSize: 10 }}>⚠</span>}</>
                      : <span className="muted">—</span>
                    return (
                      <tr key={r.record_id}>
                        <td><strong>{r.reference}</strong></td>
                        <td>{Cell(r.design, r.design_unreconciled)}</td>
                        <td style={{ maxWidth: 180 }}>{Cell(r.population, r.population_unreconciled)}</td>
                        <td style={{ maxWidth: 180 }}>{Cell(r.intervention, r.intervention_unreconciled)}</td>
                        <td style={{ maxWidth: 160 }}>{Cell(r.outcome, r.outcome_unreconciled)}</td>
                        <td style={{ maxWidth: 240 }}>{Cell(r.results, r.results_unreconciled)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* narrative workspace */}
      <div className="card">
        <div className="hd"><h2>Narrative synthesis</h2></div>
        <div className="bd">
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Work through the sections below — each carries the methodology guidance. Leave any blank and it becomes a
            “to-do” in the written file. {msg && <span style={{ color: 'var(--inc)', fontWeight: 600 }}>{msg}</span>}
          </div>

          {(st.sections || []).map(s => {
            const d = aiDrafts[s.key]
            const isGrade = s.key === 'grade'
            return (
              <div key={s.key} className="fld">
                <h3 style={{ fontWeight: 700, color: 'var(--navy)' }}>{s.label}</h3>
                <span className="muted" style={{ display: 'block', fontWeight: 400, fontSize: 11.5, margin: '2px 0 4px' }}>{s.guidance}</span>
                <textarea className="input" style={{ height: 90 }} value={fields[s.key] || ''} onChange={e => setF(s.key, e.target.value)} />

                {isGrade ? (
                  <>
                    <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>Certainty is graded by you — not AI-drafted.</div>
                    {/* Bind the conclusion verb to the certainty (Cochrane Table 15.6.b) — surfaced right where you grade
                        certainty + write conclusions, so a low-certainty finding is never overstated (F1). */}
                    <div className="info" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.6 }}>
                      <strong>Match the conclusion verb to the certainty</strong> (Cochrane Table 15.6.b) — phrase it per outcome:
                      <div style={{ marginTop: 4 }}>
                        <div><span className="pill inc" style={{ fontSize: 10 }}>High</span> “X <strong>reduces / increases</strong> outcome”</div>
                        <div><span className="pill maybe" style={{ fontSize: 10 }}>Moderate</span> “X <strong>probably / likely</strong> reduces / increases outcome”</div>
                        <div><span className="pill maybe" style={{ fontSize: 10 }}>Low</span> “X <strong>may</strong> reduce / increase outcome” (or “the evidence suggests…”)</div>
                        <div><span className="pill exc" style={{ fontSize: 10 }}>Very low</span> “<strong>the evidence is very uncertain</strong> about the effect of X”</div>
                      </div>
                      <span className="muted">Pick the one direction (reduce <em>or</em> increase) that matches each outcome — “probably” and “likely” are equivalent. The verb weakens as certainty falls; don’t overstate a low-certainty result.</span>
                    </div>
                  </>
                ) : (
                  <div style={{ marginTop: 5 }}>
                    {!d && (
                      <>
                        <button className="btn" disabled={!canDraft || drafting} onClick={() => getAiDraftFor(s.key)}
                          style={{ fontSize: 11.5, padding: '4px 10px' }}>
                          {drafting ? 'Drafting…' : '✦ Get an independent AI draft'}
                        </button>
                        {!canDraft && <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>
                          {ai.key_present ? 'needs included studies with extraction' : `add a ${ai.key_var} key on Setup`}</span>}
                      </>
                    )}
                    {d && (
                      <div className="ai-box" style={{ marginTop: 6 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--navy)', marginBottom: 4 }}>
                          AI draft — independent second opinion
                          <span className="muted" style={{ fontWeight: 400 }}>
                            {' · '}{d.provenance?.ai_model || 'AI'}{d.accepted ? '' : ' · not human-verified'}
                          </span>
                        </div>
                        <div style={{ fontSize: 12.5, whiteSpace: 'pre-wrap', lineHeight: 1.5, color: '#374151' }}>{d.text}</div>
                        <div style={{ marginTop: 6, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                          {d.accepted
                            ? <span className="chip inc" style={{ fontSize: 11 }}>✓ reviewed &amp; reconciled</span>
                            : <button className="btn primary" onClick={() => acceptDraft(s.key)} style={{ fontSize: 11.5, padding: '4px 10px' }}>Use this as my draft</button>}
                          <button className="btn" disabled={drafting} onClick={() => getAiDraftFor(s.key)} style={{ fontSize: 11.5, padding: '4px 10px' }}>↻ Re-draft</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}

          {/* Manual Summary-of-Findings table — sits beneath the GRADE section above */}
          <div style={{ margin: '2px 0 12px', paddingTop: 12, borderTop: '1px solid var(--line)' }}>
            <div style={{ fontWeight: 700, color: 'var(--navy)' }}>Summary of Findings (SoF) table</div>
            <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 8px' }}>
              One row per key outcome (≤7). Grade certainty <strong>per outcome</strong> — don’t average across outcomes
              (Cochrane Ch.14 / GRADE). The reason records what downgraded (risk of bias, inconsistency, indirectness,
              imprecision, publication bias) or upgraded it. Saved with your notes and added to your synthesis write-up beneath the
              GRADE section. <em>This is the lightweight version (certainty per outcome); a full Cochrane SoF also reports
              the assumed comparator risk and the absolute + relative effect (95% CI) for each outcome — add those before
              publication.</em>
            </div>
            {sof.length > 0 && (
              <div style={{ overflowX: 'auto' }}>
                <table className="ext-table">
                  <thead><tr>
                    <th>Outcome</th>
                    <th style={{ width: 92 }}>№ studies</th>
                    <th style={{ width: 128 }}>Certainty</th>
                    <th>Reason for rating</th>
                    <th style={{ width: 30 }} aria-label="delete"></th>
                  </tr></thead>
                  <tbody>
                    {sof.map((r, i) => (
                      <tr key={i}>
                        <td><input className="input" value={r.outcome || ''} placeholder="e.g. Depression at 6 months"
                          onChange={e => setSofCell(i, 'outcome', e.target.value)} /></td>
                        <td><input className="input" type="number" min="0" value={r.n_studies ?? ''}
                          onChange={e => setSofCell(i, 'n_studies', e.target.value)} /></td>
                        <td>
                          <select className="select" value={r.certainty || ''} onChange={e => setSofCell(i, 'certainty', e.target.value)}>
                            <option value="">—</option>
                            {(st.sof_certainty || SOF_CERTAINTY).map(c => <option key={c} value={c}>{c}</option>)}
                          </select>
                        </td>
                        <td><input className="input" value={r.reason || ''} placeholder="what downgraded / upgraded it"
                          onChange={e => setSofCell(i, 'reason', e.target.value)} /></td>
                        <td><button className="btn" title="Delete row" onClick={() => delSofRow(i)}
                          style={{ padding: '3px 9px' }}>✕</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <button className="btn" onClick={addSofRow} style={{ marginTop: 8 }}>＋ Add outcome row</button>
          </div>

          {/* Human-first AI second-opinion control */}
          <div style={{ marginTop: 4, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>
              <strong>Human-first:</strong> write your own synthesis, then (optionally) get an <em>independent</em> AI
              second opinion per section to compare against. The AI never writes into your file on its own — you Accept a
              draft to reconcile it, and GRADE certainty stays your judgement.
            </div>
            <button className="btn" disabled={!canDraft || drafting} onClick={() => getAiDrafts(true)}>
              {drafting ? 'Drafting…' : '✦ Get AI second-opinion drafts for empty sections'} ({ai.provider || '—'})
            </button>
            {!ai.key_present && <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>— add a {ai.key_var} key on Setup</span>}
            {ai.key_present && !t.n_included && <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>— needs included studies with extraction</span>}
          </div>

          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" onClick={save}>Save notes</button>
            <button className="btn primary" onClick={generate} disabled={busy}>{busy ? 'Generating…' : 'Generate synthesis'}</button>
            {st.files?.['synthesis.md'] && <a className="ft-link" href="/api/download/synthesis.md">⬇ Download synthesis</a>}
          </div>
        </div>
      </div>
    </div>
  )
}
