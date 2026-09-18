import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ReviewManager from './ReviewManager.jsx'

// §1 Setup — the single place to DEFINE the review and configure the AI, in-app.
// It writes three things, kept deliberately separate:
//   • criteria.txt  — VERBATIM (the one file the AI screener + the human read; never field-parsed)
//   • Outputs/config.json — the structured record (title + question components + RoB tool + provider)
//   • EE/.env       — the API key (written locally, never echoed back)
// The search-term concept editor lives on the SEARCH step (SearchTerms.jsx), where the search is built;
// the protocol generator lives on the PROTOCOL step (Protocol.jsx). Both moved off Setup deliberately.

// Each question framework has its OWN components, so the boxes relabel when the framework changes. Values are
// stored under stable per-component keys, so components shared across frameworks (Population/Comparison/Outcome)
// carry over when you switch (PICO↔PECO). Grounded in concept-question-frameworks.
const FRAMEWORKS = {
  PICO: [['population', 'Population (P)'], ['intervention', 'Intervention (I)'], ['comparison', 'Comparison (C)'], ['outcome', 'Outcome (O)']],
  PECO: [['population', 'Population (P)'], ['exposure', 'Exposure (E)'], ['comparison', 'Comparison (C)'], ['outcome', 'Outcome (O)']],
  PECOS: [['population', 'Population (P)'], ['exposure', 'Exposure (E)'], ['comparison', 'Comparison (C)'], ['outcome', 'Outcome (O)'], ['study_design', 'Study design (S)']],
  PEO: [['population', 'Population (P)'], ['exposure', 'Exposure (E)'], ['outcome', 'Outcome (O)']],
  PIRD: [['population', 'Population (P)'], ['index_test', 'Index test (I)'], ['reference_standard', 'Reference standard (R)'], ['diagnosis', 'Target condition / diagnosis (D)']],
  SPIDER: [['sample', 'Sample (S)'], ['phenomenon', 'Phenomenon of Interest (PI)'], ['design', 'Design (D)'], ['evaluation', 'Evaluation (E)'], ['research_type', 'Research type (R)']],
}
const FRAMEWORK_HINT = {
  PICO: 'Intervention questions — effects of a treatment/programme.',
  PECO: 'Exposure / observational questions — Comparison may be “N/A”.',
  PECOS: 'Exposure questions where study design is part of eligibility.',
  PEO: 'Experience / prevalence questions — no comparator.',
  PIRD: 'Diagnostic-accuracy questions (index test vs reference standard).',
  SPIDER: 'Qualitative / mixed-method questions.',
}
// Grey example text for each question box (shown as a placeholder, so it reads as a prompt, not your answer).
// Each FRAMEWORK gets ONE COHERENT worked example so the whole row reads as a single real question — NOT a jumble
// of topics (the shared-component map below mixed a stroke Population with a PID Exposure). The worked examples are
// verbatim from the SimplyPsychology guide's question types via concept-question-frameworks.md: PICO = Therapy
// (stroke/physiotherapy); PECO/PECOS/PEO = Etiology-Harm (PID → gynaecological cancer); PIRD = Diagnosis (FIT vs
// colonoscopy); SPIDER = a qualitative-experience example. Topic-agnostic (not tied to any real review here).
const FRAMEWORK_EXAMPLE = {
  PICO: {
    population: 'e.g. patients with a recent acute stroke (< 6 weeks) and reduced mobility',
    intervention: 'e.g. a specific physiotherapy approach',
    comparison: 'e.g. no physiotherapy (usual care)',
    outcome: 'e.g. independence in activities of daily living and gait speed',
  },
  PECO: {
    population: 'e.g. women of reproductive age',
    exposure: 'e.g. a history of pelvic inflammatory disease (PID)',
    comparison: 'e.g. women with no history of PID (the unexposed group) — or “N/A”',
    outcome: 'e.g. later gynaecological cancer',
  },
  PECOS: {
    population: 'e.g. women of reproductive age',
    exposure: 'e.g. a history of pelvic inflammatory disease (PID)',
    comparison: 'e.g. women with no history of PID (the unexposed group)',
    outcome: 'e.g. later gynaecological cancer',
    study_design: 'e.g. prospective cohort studies',
  },
  PEO: {
    population: 'e.g. women of reproductive age',
    exposure: 'e.g. a history of pelvic inflammatory disease (PID)',
    outcome: 'e.g. later gynaecological cancer',
  },
  PIRD: {
    population: 'e.g. adults being screened for colon cancer (average risk)',
    index_test: 'e.g. faecal immunochemical testing (FIT)',
    reference_standard: 'e.g. colonoscopy (the reference test it is compared against)',
    diagnosis: 'e.g. colon cancer (the target condition being diagnosed)',
  },
  SPIDER: {
    sample: 'e.g. first-time mothers',
    phenomenon: 'e.g. their experiences of breastfeeding support',
    design: 'e.g. interviews or focus groups',
    evaluation: 'e.g. how helpful they found the support',
    research_type: 'e.g. qualitative or mixed-method studies',
  },
}
// Per-component FALLBACK (used only if a framework/component pair is missing from FRAMEWORK_EXAMPLE above).
const COMPONENT_PLACEHOLDER = {
  population: 'e.g. the specific group of people your question is about (give numeric bounds where you can)',
  intervention: 'e.g. the treatment or programme being tested',
  exposure: 'e.g. the risk factor or exposure of interest',
  comparison: 'e.g. the control / unexposed group — or “N/A” for an observational question',
  outcome: 'e.g. the result or effect you are measuring',
  study_design: 'e.g. randomised trials and prospective cohort studies',
  index_test: 'e.g. the new test whose accuracy you are evaluating',
  reference_standard: 'e.g. the gold-standard test it is compared against',
  diagnosis: 'e.g. the target condition being diagnosed',
  sample: 'e.g. the specific group of people whose experience you are studying',
  phenomenon: 'e.g. the experience, behaviour, or process you are studying',
  design: 'e.g. interviews, focus groups, or diary studies',
  evaluation: 'e.g. the outcome or change you are assessing',
  research_type: 'e.g. qualitative or mixed-method studies',
}
// Which EE/.env variable a model needs (mirrors the backend _env_key_for so the UI can label the field).
function envVarFor(model) {
  const m = String(model || '').toLowerCase()
  if (m.startsWith('ollama') || m.includes('/ollama')) return null   // local Ollama needs no key (check first)
  if (m.includes('gemini')) return 'GEMINI_API_KEY'
  if (m.includes('claude') || m.includes('anthropic')) return 'ANTHROPIC_API_KEY'
  if (m.includes('gpt') || m.includes('openai')) return 'OPENAI_API_KEY'
  return null   // any other keyless/local model
}

// Read / rewrite ONLY the ROB_TOOL line inside the verbatim criteria text (preserving any trailing comment),
// so the RoB-tool select and the criteria editor never disagree about what the §6 step will read.
const AUTO_COMMENT = '# auto = RoB 2 for randomised, ROBINS-I for non-randomised'
const robFromCriteria = text => (text.match(/ROB_TOOL\s*:\s*([^\n#]+)/i)?.[1] || '').trim()
function setRobInCriteria(text, tool) {
  // Replace the WHOLE ROB_TOOL line so a stale "auto = …" comment can't contradict a non-auto value;
  // keep the explanatory comment only when the value is actually 'auto'.
  const line = `ROB_TOOL: ${tool}${tool === 'auto' ? '   ' + AUTO_COMMENT : ''}`
  if (/^[ \t]*ROB_TOOL\s*:.*$/im.test(text)) return text.replace(/^[ \t]*ROB_TOOL\s*:.*$/im, line)
  return text.replace(/\s*$/, '') + `\n${line}\n`
}

function Saved({ when }) {
  if (!when) return null
  return <span style={{ color: 'var(--inc)', fontSize: 12, fontWeight: 600, marginLeft: 10 }}>✓ saved</span>
}

export default function Setup() {
  const [cfg, setCfg] = useState({})
  const [providers, setProviders] = useState([])
  const [models, setModels] = useState({})
  const [providerModels, setProviderModels] = useState({})
  const [keysPresent, setKeysPresent] = useState({})
  const [criteria, setCriteria] = useState('')
  const [elig, setElig] = useState({ inclusion: '', exclusion: '', study_design_features: '', date_range: '', language: '', publication_status: '', examples: '' })
  const [rawMode, setRawMode] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [robTools, setRobTools] = useState({ presets: [], custom: [] })
  const [showUpload, setShowUpload] = useState(false)
  const [toolName, setToolName] = useState('')
  const [toolFile, setToolFile] = useState(null)
  const [saved, setSaved] = useState({})
  const [err, setErr] = useState('')

  const flag = (k) => { setSaved(s => ({ ...s, [k]: Date.now() })); setTimeout(() => setSaved(s => ({ ...s, [k]: 0 })), 2500) }

  useEffect(() => {
    api('/config').then(d => {
      setCfg(d.config || {}); setProviders(d.providers || []); setModels(d.models || {}); setProviderModels(d.provider_models || {}); setKeysPresent(d.keys_present || {})
    }).catch(e => setErr(String(e)))
    api('/criteria').then(d => setCriteria(d.text || '')).catch(() => {})
    api('/criteria/fields').then(d => setElig(e => ({ ...e, ...d, publication_status: d.publication_status || '' }))).catch(() => {})
    api('/rob-tools').then(d => setRobTools({ presets: d.presets || [], custom: d.custom || [] })).catch(() => {})
  }, [])

  const set = (k, v) => setCfg(c => ({ ...c, [k]: v }))
  const setComp = (k, v) => setCfg(c => ({ ...c, components: { ...(c.components || {}), [k]: v } }))
  const providerNames = Object.keys(providerModels)
  const provider = (providerNames.includes(cfg.provider) ? cfg.provider : providerNames[0]) || ''
  const modelOpts = providerModels[provider] || []
  const model = cfg.model || (modelOpts[0] && modelOpts[0].value) || ''
  const envVar = envVarFor(model)
  const framework = cfg.framework || 'PECO'
  const fields = FRAMEWORKS[framework] || FRAMEWORKS.PECO

  // RoB-tool select reflects the criteria text (authoritative), falling back to the saved config.
  const robValue = robFromCriteria(criteria) || cfg.rob_tool || 'auto'
  const robKnown = new Set([...(robTools.presets || []).map(p => p.value), ...(robTools.custom || []).map(c => c.name)])
  const structuredVals = new Set((robTools.presets || []).filter(p => p.structured).map(p => p.value))
  const changeRob = (tool) => { setCriteria(t => setRobInCriteria(t, tool)); set('rob_tool', tool) }

  const saveDetails = () => {
    const body = {
      project_title: cfg.project_title || '', framework, rob_tool: robValue, provider, model,
      // Send the FULL component map (every key the user has touched across frameworks), so switching
      // framework before saving never drops a value the other framework owns (e.g. Intervention when on PECO).
      components: { ...(cfg.components || {}) },
    }
    api('/config', { method: 'POST', body }).then(d => { setCfg(d.config || cfg); flag('details') }).catch(e => setErr(String(e)))
  }
  const saveCriteria = () => api('/criteria', { method: 'POST', body: { text: criteria } })
    .then(() => { flag('criteria'); api('/criteria/fields').then(d => setElig(e => ({ ...e, ...d, publication_status: d.publication_status || '' }))).catch(() => {}) }).catch(e => setErr(String(e)))
  const setE = (k, v) => setElig(s => ({ ...s, [k]: v }))
  const saveElig = () => api('/criteria/fields', { method: 'POST', body: { fields: elig } })
    .then(d => { setCriteria(d.text || ''); flag('criteria') }).catch(e => setErr(String(e)))
  const saveKey = () => api('/apikey', { method: 'POST', body: { provider, model, key: apiKey } })
    .then(d => { setKeysPresent(d.keys_present || {}); setApiKey(''); flag('key') }).catch(e => setErr(String(e)))

  const uploadTool = async () => {
    if (!toolName.trim() || !toolFile) return
    const fd = new FormData(); fd.append('name', toolName.trim()); fd.append('file', toolFile)
    try {
      const res = await fetch('/api/rob-tool/upload', { method: 'POST', body: fd })
      const d = await res.json()
      if (d.ok) { setRobTools(t => ({ ...t, custom: d.custom || [] })); changeRob(d.name); setToolName(''); setToolFile(null); setShowUpload(false) }
      else setErr(d.message || 'Upload failed')
    } catch (e) { setErr(String(e)) }
  }

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 960 }}>
      <ReviewManager />
      <div className="info">
        This is where you set up your review. Fill in your question and eligibility criteria <strong>once</strong> —
        every later step (screening, extraction, and your protocol) reads them from here, so you only define them in
        one place. The AI you pick is a <strong>second checker</strong>: it screens each study <strong>independently</strong> —
        forming its own opinion, like a second reviewer, without seeing your decision first. Where you and the AI
        agree, that becomes your consensus; where you disagree, you settle it yourself or send it to a third
        independent reviewer — the AI is <strong>never the final word</strong>. Everything stays on this computer;
        your files and API key are never uploaded.
      </div>
      {err && <div className="warn">Something went wrong: {err}. Is the backend running?</div>}

      {/* 1 — Review details (config.json) */}
      <div className="card">
        <div className="hd"><h2>Review details</h2></div>
        <div className="bd">
          <label className="fld"><h3>Project / review title</h3>
            <input className="input" value={cfg.project_title || ''} onChange={e => set('project_title', e.target.value)}
              placeholder="e.g. The effect of [intervention] on [outcome] in [population]" />
          </label>
          <label className="fld" style={{ maxWidth: 300 }}><h3>Question framework</h3>
            <select className="select" value={framework} onChange={e => set('framework', e.target.value)}>
              {Object.keys(FRAMEWORKS).map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 12px' }}>
            {FRAMEWORK_HINT[framework]} <span style={{ color: 'var(--faint)' }}>The boxes below relabel to match the framework.</span>
          </div>
          <div className="pico-grid">
            {fields.map(([key, label]) => (
              <label key={key} className="fld"><h3>{label}</h3>
                <textarea className="input" style={{ height: 64 }} value={(cfg.components || {})[key] || ''}
                  placeholder={FRAMEWORK_EXAMPLE[framework]?.[key] || COMPONENT_PLACEHOLDER[key] || ''}
                  onChange={e => setComp(key, e.target.value)} />
              </label>
            ))}
          </div>

          <label className="fld" style={{ maxWidth: 460 }}><h3>Risk-of-bias tool</h3>
            <select className="select" value={robValue} onChange={e => e.target.value === '__upload' ? setShowUpload(true) : changeRob(e.target.value)}>
              <optgroup label="Current Cochrane tools (get a full guided grid at the Risk-of-bias step)">
                {(robTools.presets || []).filter(p => p.group === 'current').map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </optgroup>
              <optgroup label="Design-specific current tools (recorded)">
                {(robTools.presets || []).filter(p => p.group === 'design').map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </optgroup>
              <optgroup label="Legacy comparators (recorded for the protocol)">
                {(robTools.presets || []).filter(p => p.group === 'legacy').map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </optgroup>
              {(robTools.custom || []).length > 0 && (
                <optgroup label="Your uploaded tools">
                  {robTools.custom.map(c => <option key={c.name} value={c.name}>{c.name} (custom)</option>)}
                </optgroup>
              )}
              {!robKnown.has(robValue) && <option value={robValue}>{robValue} (from your saved criteria)</option>}
              <option value="__upload">＋ Upload a custom tool…</option>
            </select>
          </label>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>
            {structuredVals.has(robValue) || robValue === 'auto'
              ? <>The <strong>Risk-of-bias step</strong> will give you a full guided, domain-by-domain grid for this tool (RoB 2 / ROBINS-I).</>
              : <><strong>“{robValue.replace(/ \(.*\)/, '')}” is recorded for your protocol.</strong> The guided domain-by-domain grid is currently built only for RoB 2 / ROBINS-I; a grid for other tools is on the roadmap.</>}
            {' '}Changing this updates your saved criteria — remember to save the criteria below to apply it to the AI.
          </div>

          {showUpload && (
            <div className="card" style={{ background: '#fbfcfd', marginBottom: 12 }}>
              <div className="bd">
                <h2 className="hd-inline">Upload a custom risk-of-bias / quality-appraisal tool</h2>
                <div className="muted" style={{ fontSize: 11.5, marginBottom: 10 }}>
                  We can’t ship every tool, so add your own (e.g. ROBINS-E, QUADAS-2, PROBAST, a domain checklist).
                  The file (PDF / Word / Markdown / text) stays on this machine; the tool name is recorded for the protocol.
                </div>
                <label className="fld" style={{ maxWidth: 360 }}><h3>Tool name</h3>
                  <input className="input" value={toolName} onChange={e => setToolName(e.target.value)} placeholder="e.g. QUADAS-2" />
                </label>
                <input type="file" accept=".pdf,.docx,.doc,.md,.txt,.csv,.json,.rtf" onChange={e => setToolFile(e.target.files?.[0] || null)} style={{ fontSize: 12, marginBottom: 10 }} />
                <div>
                  <button className="btn primary" onClick={uploadTool} disabled={!toolName.trim() || !toolFile}>Upload &amp; select</button>
                  <button className="btn" style={{ marginLeft: 8 }} onClick={() => { setShowUpload(false); setToolFile(null); setToolName('') }}>Cancel</button>
                </div>
              </div>
            </div>
          )}

          <button className="btn primary" onClick={saveDetails}>Save review details</button>
          <Saved when={saved.details} />
        </div>
      </div>

      {/* 2 — eligibility criteria (structured → assembled into criteria.txt) */}
      <div className="card">
        <div className="hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>Eligibility criteria</h2>
          <span className="muted" style={{ fontSize: 12, cursor: 'pointer' }} onClick={() => setRawMode(r => !r)}>
            {rawMode ? '↩ back to boxes' : 'edit raw file (advanced)'}
          </span>
        </div>
        <div className="bd">
          <div className="info" style={{ marginBottom: 12 }}>
            Your rules for which studies are <strong>in</strong> and which are <strong>out</strong>. The AI screener
            and you both apply these, so word each one so a <strong>yes/no</strong> decision is clear (numbers, not
            adjectives — “aged 18+”, not “adults”). Your PICO/PECO above is included automatically — no need to repeat
            it. EvidenceEngine assembles these into your <strong>eligibility criteria</strong> — the one thing the
            screener reads. <Saved when={saved.criteria} />
          </div>

          {rawMode ? (
            <>
              <div className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>
                Raw eligibility criteria (read verbatim by the screener). Editing here overrides
                the boxes; saving re-reads them.
              </div>
              <textarea className="input crit-edit" value={criteria} onChange={e => setCriteria(e.target.value)}
                spellCheck={false} placeholder={'REVIEW_TOPIC:\nFRAMEWORK:\nPICO_P:\n…\nINCLUSION_CRITERIA:\n- …\nEXCLUSION_CRITERIA:\n- …\nROB_TOOL: auto'} />
              <div style={{ marginTop: 12 }}>
                <button className="btn primary" onClick={saveCriteria}>Save criteria</button>
              </div>
            </>
          ) : (
            <>
              <label className="fld"><h3>Inclusion criteria</h3> <span className="muted" style={{ fontWeight: 400 }}>— one per line; a study must meet all of these</span>
                <textarea className="input" style={{ height: 110 }} value={elig.inclusion} onChange={e => setE('inclusion', e.target.value)}
                  placeholder={'One rule per line, e.g.:\nParticipants meet your population definition (give numeric bounds, e.g. aged 18+)\nThe intervention or exposure of interest is present and measured\nMeasures at least one of your chosen outcomes\nEmpirical primary study with quantitative data'} />
              </label>
              <label className="fld"><h3>Exclusion criteria</h3> <span className="muted" style={{ fontWeight: 400 }}>— optional; most reviews leave this empty (anything that fails your inclusion criteria above is already excluded). Only add a rule here for an extra carve-out — a case that technically meets inclusion but you still want out (e.g. a subgroup likely to respond differently)</span>
                <textarea className="input" style={{ height: 70 }} value={elig.exclusion} onChange={e => setE('exclusion', e.target.value)}
                  placeholder={'Usually left blank. Only fill this in for a specific extra carve-out beyond your inclusion criteria, e.g.:\nParticipants recruited from an inpatient/acute setting (even though they otherwise meet the population criteria — response likely differs by setting)'} />
              </label>
              <p className="muted" style={{ fontSize: 11.5, marginTop: -2, marginBottom: 10, lineHeight: 1.55 }}>
                Judge a study on what it <strong>measured</strong>, not on whether it reported a result. A study that
                measured your outcome but didn’t report it is still included — missing results are handled later, in synthesis.
              </p>
              <label className="fld"><h3>Eligible study designs</h3> <span className="muted" style={{ fontWeight: 400 }}>— by features, not just labels (e.g. “randomised; concurrent comparison group; ≥12-week follow-up”)</span>
                <textarea className="input" style={{ height: 56 }} value={elig.study_design_features} onChange={e => setE('study_design_features', e.target.value)}
                  placeholder={'e.g.: Randomly allocated to groups (or a clearly reported quasi-random method, e.g. by birth date); a concurrent comparison group; outcomes assessed ≥12 weeks after baseline. Decide up front whether non-randomised studies count too (Cochrane Ch.3) — and if so, name which features make one eligible.'} />
              </label>
              <div className="pico-grid">
                <label className="fld"><h3>Date range</h3>
                  <input className="input" value={elig.date_range} onChange={e => setE('date_range', e.target.value)} placeholder="e.g. 1974–2018 (only if you can justify the cut-off), or “no limit”" />
                </label>
                <label className="fld"><h3>Language</h3>
                  <input className="input" value={elig.language} onChange={e => setE('language', e.target.value)} placeholder="e.g. English only (note as a limitation)" />
                </label>
              </div>
              <label className="fld"><h3>Publication status</h3>
                <input className="input" value={elig.publication_status} onChange={e => setE('publication_status', e.target.value)}
                  placeholder="e.g. include all publication types (journal articles, dissertations/theses, conference abstracts, preprints); note any format you exclude, with a reason" />
              </label>
              <div className="muted" style={{ fontSize: 11.5, margin: '2px 0 12px', lineHeight: 1.55 }}>
                Default is to <strong>include all publication types</strong> — Cochrane advises against excluding by publication
                status unless you can justify it, because leaving out unpublished or grey literature risks publication bias.
                Restricting language or dates can bias the review too — only do it for a documented reason, and record it.
              </div>
              <button className="btn primary" onClick={saveElig}>Save eligibility criteria</button>
            </>
          )}
        </div>
      </div>

      {/* 3 — provider + API key (.env) */}
      <div className="card">
        <div className="hd"><h2>AI provider &amp; API key</h2></div>
        <div className="bd">
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <label className="fld" style={{ minWidth: 240, flex: 1 }}><h3>Which AI does the second check?</h3>
              <select className="select" value={provider}
                onChange={e => setCfg(c => ({ ...c, provider: e.target.value, model: (providerModels[e.target.value]?.[0]?.value) || '' }))}>
                {providerNames.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
            <label className="fld" style={{ minWidth: 240, flex: 1 }}><h3>Model</h3>
              <select className="select" value={model} onChange={e => set('model', e.target.value)}>
                {modelOpts.map((m, i) => <option key={i} value={m.value}>{m.label}</option>)}
              </select>
            </label>
          </div>
          <div className="muted" style={{ fontSize: 11.5, margin: '6px 0 14px', lineHeight: 1.6 }}>
            This is the AI that independently second-checks your <strong>screening</strong>. It defaults to the
            <strong> cheapest model</strong> for the provider, not the fanciest — screening a title/abstract against
            your criteria doesn’t need a frontier model, and a cheap one costs far less across hundreds of records.
            Options within each provider are ordered cheapest → most expensive (with the per-million-token price
            shown) so you can weigh cost against reasoning strength yourself. If you want more confidence in a
            cheap model before running your full screen, pilot it on ~10–20 records and check its recall on the
            Reliability screen — the same “pilot the criteria” step the eligibility-criteria-drafter skill recommends.
            <br />
            <strong>Note on the data-extraction step:</strong> pulling the numbers out of the PDFs currently always runs
            on <strong>Google Gemini</strong> (it is far cheaper for long documents), so if you plan to use extraction,
            add a Gemini key below even if you chose a different AI for screening.
          </div>
          {envVar ? (
            <>
              <div style={{ marginBottom: 8, fontSize: 12.5 }}>
                {keysPresent[envVar]
                  ? <span style={{ color: 'var(--inc)', fontWeight: 600 }}>✓ A key for {envVar} is already saved on this machine.</span>
                  : <span className="muted">No key saved for {envVar} yet.</span>}
              </div>
              <label className="fld" style={{ maxWidth: 460 }}><h3>{envVar} (your API key)</h3>
                <input className="input mono" type="password" value={apiKey} autoComplete="off"
                  onChange={e => setApiKey(e.target.value)} placeholder={keysPresent[envVar] ? '•••••••• (enter a new key to replace)' : 'paste your key'} />
              </label>
              <button className="btn primary" onClick={saveKey} disabled={!apiKey.trim()}>Save key to local .env</button>
              <Saved when={saved.key} />
              <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
                The key is written only to a local <span className="mono">.env</span> file on this computer. It is
                never displayed back, never uploaded, and never saved into your review's files.
              </div>
            </>
          ) : (
            <div className="info">Local Ollama runs on your machine and needs no API key.</div>
          )}
        </div>
      </div>

    </div>
  )
}
