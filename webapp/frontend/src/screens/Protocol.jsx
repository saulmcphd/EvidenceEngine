import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// Stage-1 protocol generator — pick a format, generate the protocol the review will run against.
// Reuses Setup's config.json + criteria.txt + the search; collects extra fields here; writes protocol.docx
// (PRISMA-P 17-item document) and/or prospero-registration.md. The factual spine is deterministic with honest
// ____ blanks; the Background can be drafted by the user's own AI model from their notes. Rendered as a card at
// the bottom of the Setup screen ("Setup & protocol").

// Extra fields the protocol needs beyond what Setup already collects. Grouped for a tidy collapsible form.
const GROUPS = [
  ['Introduction', [
    ['background', 'Background / rationale — a few sentences: what is known, the gap, why the review is needed', true],
    ['objective', 'Objective (one sentence) — left blank, it is auto-built from your PICO/PECO', false],
  ]],
  ['Methods (the parts not already on Setup)', [
    ['info_sources', 'Information sources — databases, registers, grey literature, with planned coverage dates', true],
    ['search_strategy_note', 'Draft search strategy — a draft string for ≥1 database (PRISMA-P item 10). If you build the full search on the Search step, it is pulled in automatically and overrides this.', true],
    ['outcomes_primary', 'Primary outcome(s) — ≤7 critical, with time-frames', true],
    ['outcomes_secondary', 'Secondary outcome(s)', true],
    ['synthesis_plan', 'Data synthesis plan — narrative vs meta-analysis; effect measure; heterogeneity; fixed/random', true],
    ['meta_bias', 'Meta-bias — publication bias across studies + selective reporting within studies', false],
    ['certainty', 'Certainty of evidence — e.g. GRADE', false],
    ['subgroups', 'Subgroup / subset analyses (PROSPERO field)', false],
    ['condition_domain', 'Condition / domain being studied (PROSPERO field)', true],
    ['context', 'Context (PROSPERO field)', false],
  ]],
  ['Administrative', [
    ['protocol_version', 'Protocol version number (PRISMA-P item 4, amendments) — e.g. 1.0; increment when you make amendments', false],
    ['authors', 'Authors — names, affiliations, contributions (PRISMA-P item 3)', true],
    ['guarantor', 'Guarantor (the accountable lead)', false],
    ['funding', 'Funding / sponsor (PRISMA-P item 5)', false],
    ['funder_role', "Funder's role (if any)", false],
    ['conflicts', 'Conflicts of interest', false],
    ['registration', 'Registration — registry + number (once registered)', false],
    ['start_date', 'Anticipated start date', false],
    ['end_date', 'Anticipated end date', false],
    ['timeline', 'Timeline — when each stage will be done', true],
    ['dissemination_plan', 'Dissemination plan — intended target journal, conference, or policy audience; whether a plain-language summary for patients/public is planned (get lived-experience sign-off before publishing)', true],
  ]],
]

export default function Protocol() {
  const [st, setSt] = useState(null)
  const [fields, setFields] = useState({})
  const [formats, setFormats] = useState({ prisma_p: true, prospero: true })
  const [aiBg, setAiBg] = useState(null)          // the AI Background draft + accept state (draft/accept spine)
  const [bgBusy, setBgBusy] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => api('/protocol/state').then(d => {
    setSt(d); setFields(d.fields || {}); setAiBg(d.ai_bg && d.ai_bg.text ? d.ai_bg : null)
  }).catch(e => setErr(String(e))), [])
  useEffect(() => { load() }, [load])

  const setF = (k, v) => setFields(f => ({ ...f, [k]: v }))
  const saveFields = () => api('/protocol/fields', { method: 'POST', body: { fields } })
    .then(() => { setMsg('Saved your protocol details.'); load() }).catch(e => setErr(String(e)))

  // AI Background: draft an independent second opinion (never overwrites your notes), then Accept to reconcile it.
  const getBgDraft = async () => {
    setBgBusy(true); setErr(''); setMsg('')
    try {
      await api('/protocol/fields', { method: 'POST', body: { fields } })   // persist your notes (the blind arm) first
      const d = await api('/protocol/ai-background', { method: 'POST', body: {} })
      if (d.ok) { setAiBg(d.ai_bg); setMsg(d.message) } else setErr(d.message || 'AI draft failed.')
    } catch (e) { setErr(String(e)) }
    setBgBusy(false)
  }
  const acceptBg = async () => {
    setBgBusy(true); setErr(''); setMsg('')
    try {
      const d = await api('/protocol/accept-background', { method: 'POST', body: {} })
      if (d.ok) { setAiBg(d.ai_bg); setMsg(d.message); load() } else setErr(d.message || 'Accept failed.')
    } catch (e) { setErr(String(e)) }
    setBgBusy(false)
  }

  const generate = async () => {
    setBusy(true); setErr(''); setMsg('')
    const chosen = Object.keys(formats).filter(k => formats[k])
    if (!chosen.length) { setErr('Pick at least one format.'); setBusy(false); return }
    try {
      // save first so the generate reads the latest fields, then generate
      await api('/protocol/fields', { method: 'POST', body: { fields } })
      const d = await api('/protocol/generate', { method: 'POST', body: { formats: chosen } })
      if (d.ok) { setMsg(d.message); load() } else { setErr(d.message || 'Generation failed.') }
    } catch (e) { setErr(String(e)) }
    setBusy(false)
  }

  if (!st) return <div className="card"><div className="bd muted">Loading the protocol generator…</div></div>

  const ai = st.ai || {}
  return (
    <div className="card">
      <div className="hd"><h2>Generate your protocol</h2></div>
      <div className="bd">
        <div className="info" style={{ marginBottom: 12 }}>
          Turn your review into a ready-to-use <strong>protocol</strong> — the plan you register and run the review
          against. It pulls from your other steps — the title, question and eligibility criteria from
          <strong> Setup</strong>, and the search strategy from <strong>Search</strong> — and you fill the rest below.
          A protocol is written up front, but it gets richer as you complete later steps, so you can come back and
          <strong> regenerate</strong> it any time. Every section you leave empty appears as a <strong>blank to
          complete</strong> — nothing is invented.
        </div>

        {/* what it can see */}
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          Using from your setup:{' '}
          <Chip ok={!!st.title}>title</Chip>{' '}
          <Chip ok={!!st.framework}>question ({st.framework || '—'})</Chip>{' '}
          <Chip ok={st.has_criteria}>eligibility criteria</Chip>{' '}
          <Chip ok={!!st.rob_tool}>RoB tool ({st.rob_tool || '—'})</Chip>{' '}
          <Chip ok={st.has_search}>draft search</Chip>
        </div>

        {/* pre-registration duplicate check — concept-checking-registries-for-ongoing-reviews */}
        <div style={{ border: '1px solid var(--line)', borderRadius: 9, padding: '12px 14px', margin: '4px 0 14px', background: '#fbfcfd' }}>
          <h2 className="hd-inline" style={{ fontSize: 12.5 }}>Before you register: has this review already been done — or started?</h2>
          <p className="muted" style={{ fontSize: 11.5, margin: '2px 0 8px', lineHeight: 1.5 }}>
            Search the registries for an existing <strong>or in-progress</strong> review before registering yours, so you
            don’t duplicate work someone is mid-way through. A clean result is reassuring, not definitive (not everyone
            registers); a hit isn’t automatically fatal — you might update it, or the question may no longer be current.
          </p>
          <div style={{ fontWeight: 600, color: '#4b5563', fontSize: 12, marginBottom: 6 }}>Registries you searched for existing or in-progress reviews:</div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12.5, marginBottom: 8, alignItems: 'center' }}>
            <label className="ck" style={{ margin: 0 }}><input type="checkbox" checked={!!fields.reg_prospero} onChange={e => setF('reg_prospero', e.target.checked)} /> <span>PROSPERO</span></label>
            <label className="ck" style={{ margin: 0 }}><input type="checkbox" checked={!!fields.reg_osf} onChange={e => setF('reg_osf', e.target.checked)} /> <span>OSF</span></label>
            <label className="ck" style={{ margin: 0 }}><input type="checkbox" checked={!!fields.reg_cdsr} onChange={e => setF('reg_cdsr', e.target.checked)} /> <span>Cochrane CDSR</span></label>
            <input className="input" style={{ width: 150 }} placeholder="other registry" value={fields.reg_other || ''} onChange={e => setF('reg_other', e.target.value)} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <label className="fld" style={{ marginBottom: 0 }}><h3>Date searched</h3>
              <input className="input" type="date" value={fields.registry_search_date || ''} onChange={e => setF('registry_search_date', e.target.value)} />
            </label>
            <label className="fld" style={{ marginBottom: 0 }}><h3>Result</h3>
              <select className="select" value={fields.registry_result || ''} onChange={e => setF('registry_result', e.target.value)}>
                <option value="">—</option>
                <option>No existing or in-progress review found</option>
                <option>Found an existing or in-progress review</option>
              </select>
            </label>
          </div>
          {fields.registry_result === 'Found an existing or in-progress review' && (
            <label className="fld" style={{ marginTop: 8, marginBottom: 0 }}><h3>If found — your decision + rationale</h3>
              <textarea className="input" style={{ height: 60 }}
                placeholder="e.g. proceeding to update it (published 2015; pre-dates method X and studies Y that may change the findings)…"
                value={fields.registry_decision || ''} onChange={e => setF('registry_decision', e.target.value)} />
            </label>
          )}
        </div>

        {/* format picker */}
        <div style={{ fontSize: 11.5, fontWeight: 700, color: '#4b5563', marginBottom: 6 }}>Protocol to generate for you (pick one or both):</div>
        <label className="ck"><input type="checkbox" checked={formats.prisma_p} onChange={e => setFormats(f => ({ ...f, prisma_p: e.target.checked }))} /> <span><strong>PRISMA-P protocol document</strong> (.docx) — the full narrative protocol, structured to the PRISMA-P 17 items.</span></label>
        <label className="ck"><input type="checkbox" checked={formats.prospero} onChange={e => setFormats(f => ({ ...f, prospero: e.target.checked }))} /> <span><strong>PROSPERO registration</strong> — the same content rearranged into PROSPERO's fields, ready to paste into the form.</span></label>

        {/* AI Background — draft-then-accept (human writes notes → AI drafts independently → you Accept to reconcile) */}
        <div style={{ border: '1px solid var(--line)', borderRadius: 9, padding: '12px 14px', marginTop: 10, background: '#fbfcfd' }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--navy)', marginBottom: 4 }}>Background — AI second opinion</div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 8, lineHeight: 1.55 }}>
            You write the Background notes (in <strong>Add protocol details → Introduction</strong> below); your AI drafts an
            independent version from them, grounded in the methodology brain. Nothing the AI writes enters your protocol
            until you <strong>Accept</strong> it — then it is used (tagged AI-assisted) and its provenance record becomes human-verified.
          </div>
          <button className="btn" onClick={getBgDraft} disabled={bgBusy || !ai.key_present || !(fields.background || '').trim()}>
            {bgBusy ? '…' : (aiBg ? '↻ Re-draft' : '✦ Get an independent AI Background draft')}
          </button>
          {!ai.key_present && <span style={{ color: 'var(--maybe)', fontSize: 11.5, marginLeft: 8 }}>No {ai.key_var} key — add one on Setup.</span>}
          {ai.key_present && !(fields.background || '').trim() && <span className="muted" style={{ fontSize: 11.5, marginLeft: 8 }}>Add Background notes first (below).</span>}
          {aiBg && aiBg.text && (
            <div style={{ marginTop: 10, border: '1px solid var(--line)', borderRadius: 8, padding: 10, background: '#fff' }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
                AI draft · {(aiBg.provenance && aiBg.provenance.ai_model) || 'AI'} · {aiBg.accepted ? <span style={{ color: 'var(--inc)', fontWeight: 700 }}>✓ reviewed &amp; reconciled (human-verified)</span> : <strong>not yet human-verified</strong>}
              </div>
              <div style={{ fontSize: 12.5, whiteSpace: 'pre-wrap', lineHeight: 1.55, maxHeight: 220, overflow: 'auto' }}>{aiBg.text}</div>
              {!aiBg.accepted
                ? <button className="btn primary" style={{ marginTop: 8 }} onClick={acceptBg} disabled={bgBusy}>Use this as my Background</button>
                : <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>Accepted — used in the generated protocol, tagged AI-assisted. Re-draft to replace it (you'd Accept again).</div>}
            </div>
          )}
        </div>

        {/* collapsible details */}
        <div style={{ margin: '14px 0 8px' }}>
          <button className="btn" onClick={() => setShowDetails(s => !s)}>
            {showDetails ? '▾ Hide protocol details' : '▸ Add protocol details'} ({Object.values(fields).filter(Boolean).length} filled)
          </button>
        </div>
        {showDetails && (
          <div style={{ borderLeft: '3px solid var(--line)', paddingLeft: 14, marginBottom: 12 }}>
            <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
              All optional. Selection, extraction, data-management and amendment wording are pre-filled with
              EvidenceEngine's actual approach (human + AI second checker, human reconciles) — edit them in the
              generated document if you want.
            </div>
            {GROUPS.map(([title, flds]) => (
              <div key={title} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--navy)', margin: '6px 0' }}>{title}</div>
                {title === 'Introduction' && (
                  <label className="ck" style={{ marginBottom: 8 }}>
                    <input type="checkbox" checked={!!fields.is_update} onChange={e => setF('is_update', e.target.checked)} />
                    <span>This is an <strong>update</strong> of an existing review</span>
                  </label>
                )}
                {fields.is_update && title === 'Introduction' && (
                  <label className="fld"><h3>Update of (which review)</h3>
                    <input className="input" value={fields.update_of || ''} onChange={e => setF('update_of', e.target.value)} />
                  </label>
                )}
                {flds.map(([k, label, area]) => (
                  <label key={k} className="fld"><h3>{label}</h3>
                    {area
                      ? <textarea className="input" style={{ height: 60 }} value={fields[k] || ''} onChange={e => setF(k, e.target.value)} />
                      : <input className="input" value={fields[k] || ''} onChange={e => setF(k, e.target.value)} />}
                  </label>
                ))}
              </div>
            ))}
            <button className="btn" onClick={saveFields}>Save details</button>
          </div>
        )}

        <div style={{ marginTop: 6 }}>
          <button className="btn primary" onClick={generate} disabled={busy}>{busy ? 'Generating…' : 'Generate protocol'}</button>
        </div>

        {msg && <div className="info" style={{ marginTop: 12 }}>{msg}</div>}
        {err && <div className="warn" style={{ marginTop: 12 }}>Something went wrong: {err}</div>}

        {/* still-blank list */}
        {st.missing && st.missing.length > 0 && (
          <div className="warn" style={{ marginTop: 12 }}>
            <strong>{st.missing.length} section(s) still blank</strong> (they appear as “____” to fill in):
            <div style={{ marginTop: 4 }}>{st.missing.join(' · ')}</div>
          </div>
        )}

        {/* downloads */}
        {(st.files?.['protocol.docx'] || st.files?.['protocol.md'] || st.files?.['prospero-registration.md']) && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: '#4b5563', marginBottom: 6 }}>DOWNLOADS</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {st.files['protocol.docx'] && <a className="ft-link" href="/api/download/protocol.docx">⬇ PRISMA-P protocol (.docx)</a>}
              {st.files['protocol.md'] && !st.files['protocol.docx'] && <a className="ft-link" href="/api/download/protocol.md">⬇ PRISMA-P protocol (.md)</a>}
              {st.files['prospero-registration.md'] && <a className="ft-link" href="/api/download/prospero-registration.md">⬇ PROSPERO registration</a>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Chip({ ok, children }) {
  return <span style={{
    display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600,
    padding: '1px 8px', borderRadius: 999, marginRight: 2,
    background: ok ? 'var(--inc-bg)' : '#f3f4f6', color: ok ? 'var(--inc)' : 'var(--faint)',
  }}>{ok ? '✓' : '○'} {children}</span>
}
