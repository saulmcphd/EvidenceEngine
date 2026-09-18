import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// §9 Report / Export — the paste-into-your-paper artefacts: a gated Methods .docx, a BibTeX file, the
// PRISMA 2020 / PRISMA-trAIce flow, and the screening RIS sets. RECALL-FIRST headline. Every number comes
// from a real file on disk: a missing count reads "not recorded", a missing screening step becomes a blank
// in the Methods (never an assertion), and a DRAFT banner fires when screening artefacts are absent.
// Ports the gated-narrative logic reviewed in the Streamlit dashboard. Nothing here is invented.

const bad = v => v == null || (typeof v === 'number' && Number.isNaN(v))
const pct = (v, d = 0) => bad(v) ? '—' : (Number(v) * 100).toFixed(d) + '%'

const DOWNLOADS = [
  ['methods.docx', 'Methods (Word)', 'Paste into your paper’s Methods — includes the RAISE AI-use disclosure + a PRISMA-counts table.'],
  ['methods.md', 'Methods (Markdown fallback)', 'Only present if Word export was unavailable on this machine.'],
  ['synthesis.md', 'Synthesis narrative (Markdown)', 'The evidence table + your reconciled synthesis sections — paste into your Results/Discussion. Generate it on the Synthesis screen first.'],
  ['references.bib', 'References (BibTeX)', 'Import into your reference manager / LaTeX. One entry per master record.'],
  ['prisma-flow.png', 'PRISMA flow (PNG)', 'Publication-styled PRISMA-trAIce diagram — high-resolution image.'],
  ['prisma-flow.jpg', 'PRISMA flow (JPEG)', 'The same diagram as a JPEG, for documents that prefer it.'],
  ['prisma-flow.docx', 'PRISMA flow (Word)', 'The diagram embedded in an editable Word document.'],
  ['stage_counts.json', 'PRISMA counts (JSON)', 'The numbers behind the flow diagram.'],
  ['human_decisions.csv', 'Blind human decisions (CSV)', 'The compiled blind screening decisions.'],
]

// "4 include + 2 uncertain" from a decision breakdown (excludes are not part of the kept set)
const keptBreakdown = (bd) => {
  const parts = Object.entries(bd || {}).filter(([k]) => k !== 'exclude').map(([k, v]) => `${v} ${k}`)
  return parts.length ? ` (${parts.join(' + ')})` : ''
}

function RisRow({ fn, present, label, why }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
      <div style={{ flex: '0 0 270px' }}><strong style={{ fontSize: 13 }}>{label}</strong><div className="muted" style={{ fontSize: 11.5 }}>{why}</div></div>
      {present
        ? <a className="btn" href={'/api/download/' + fn} download>Download RIS</a>
        : <span className="muted" style={{ fontSize: 12 }}>— not built yet —</span>}
    </div>
  )
}

// The PRISMA flow is rendered server-side (prisma_render.py) to a publication-styled PRISMA 2020 / PRISMA-trAIce
// diagram; we show that exact image inline so the preview == the download. /api/prisma supplies the variant label
// + any arithmetic-consistency warnings. `bust` cache-busts the image per mount so a counts change re-renders.
function PrismaFlow({ p, bust }) {
  if (!p) return <div className="muted">Loading…</div>
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span className="pill maybe">{p.variant}</span>
        {!p.has_counts && <span className="demo-badge">NO COUNTS YET</span>}
      </div>
      {!p.has_counts && (
        <div className="warn" style={{ marginBottom: 10 }}>
          No screening counts on disk yet — run Search &amp; screening so every box is a real number.
        </div>
      )}
      {(p.consistency_warnings || []).map((w, i) => (
        <div className="warn" key={i} style={{ marginBottom: 8, fontSize: 12 }}>⚠ {w}</div>
      ))}
      <img src={'/api/prisma.png?t=' + bust} alt="PRISMA 2020 study-selection flow diagram"
        style={{ maxWidth: '100%', border: '1px solid var(--border)', borderRadius: 8, background: '#fff' }} />
      <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
        Publication-styled <strong>{p.traice ? 'PRISMA-trAIce (AI-assisted)' : 'PRISMA 2020'}</strong> diagram, drawn from your
        real counts. An unrecorded count shows as a blank “(n = )”, never a fake 0.
        {p.traice ? ' Exclusions are split by human vs AI. PRISMA-trAIce is a proposed (not yet endorsed) extension for reporting AI use — cite it as emerging.' : ''} Download it as PNG / JPEG / Word below.
      </div>
    </div>
  )
}

export default function Report() {
  const [state, setState] = useState(null)
  const [prisma, setPrisma] = useState(null)
  const [gen, setGen] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [bust, setBust] = useState(0)        // cache-bust the live PRISMA image after (re)load / generate

  const load = useCallback(() => {
    api('/report/state').then(setState).catch(e => setErr(String(e)))
    api('/prisma').then(setPrisma).catch(() => {})
    setBust(b => b + 1)
  }, [])
  useEffect(() => { load() }, [load])

  const generate = async () => {
    setBusy(true); setGen(null); setErr('')
    try {
      const d = await api('/report', { method: 'POST' })
      setGen(d)
      load()                                   // refresh file presence + recall
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const r = state?.recall
  const g = state?.gates || {}
  const sr = state?.screening_ris || {}
  const gateRow = (ok, label, missing) => (
    <div style={{ display: 'flex', gap: 8, fontSize: 12.5, padding: '4px 0' }}>
      <span style={{ color: ok ? 'var(--inc)' : 'var(--faint)', fontWeight: 700, width: 16 }}>{ok ? '✓' : '○'}</span>
      <span>{ok ? label : <span className="muted">{missing}</span>}</span>
    </div>
  )

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 980 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="demo-badge">DEMO / DRAFT until a real run</span>
      </div>
      <div className="info" style={{ fontSize: 12.5 }}>
        These are the artefacts you paste into your paper — a <strong>Methods</strong> document (with your AI-use
        disclosure), a <strong>BibTeX</strong> reference file, the <strong>PRISMA</strong> flow diagram, and your
        screening sets as RIS. Every number is read straight from your run’s files; a step that hasn’t produced an
        artefact yet appears as a blank to fill in, never as a finished claim.
      </div>
      {err && <div className="warn">Couldn’t load the report page: {err}</div>}

      {/* RECALL-FIRST headline */}
      <div className="card hero"><div className="bd">
        <div className="dlab">Reliability headline — recall (the share of relevant studies the AI kept)</div>
        {!r ? <div className="muted">Loading…</div> : r.estimable ? (
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <div style={{ minWidth: 180 }}>
              <div className="hero-num">{pct(r.recall, 1)}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                95% CI {pct(r.ci?.[0], 1)} – {pct(r.ci?.[1], 1)}{r.n_positives != null ? ` · on ${r.n_positives} relevant studies` : ''}
                {r.small_sample ? ' · small sample — interpret with caution' : ''}
              </div>
            </div>
            {r.passes != null && (
              <div style={{ minWidth: 160 }}>
                <div className="dlab">Acceptance ({r.independent ? 'a-priori' : 'default'} {pct(r.threshold)})</div>
                <div style={{ marginTop: 6 }}>
                  <span className={'pill ' + (r.passes ? 'inc' : 'exc')} style={{ fontSize: 13, padding: '4px 12px' }}>
                    {r.passes ? '✓ PASS' : '✕ NOT MET'}
                  </span>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  judged on the one-sided 95% lower bound = {pct(r.onesided_lower, 1)}.
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.6 }}>
            Recall is <strong>not estimable yet</strong> — no reliability metrics on disk. Run the comparison on the
            <strong> Reliability</strong> step (or upload your screened decisions), then return: the Methods document
            will then carry the recall + CI. We never headline F1 or accuracy (they mislead on this imbalanced task — RAISE).
          </div>
        )}
      </div></div>

      {/* What the Methods will say — the gating checklist (makes the honesty visible) */}
      <div className="card"><div className="hd"><h2>What the Methods document will state</h2></div><div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
          Each sentence is written only if the step left an artefact on disk. Missing steps become blanks to fill in —
          so the generated Methods can’t over-claim what was actually run.
        </div>
        {gateRow(state?.n_records > 0, `${state?.n_records ?? 0} master records → BibTeX + RIS`, 'Master records — build them on Search & records')}
        {gateRow(g.have_human, 'Blind human screening recorded', 'Blind human screening — not yet performed')}
        {gateRow(g.have_ai, 'AI second-screener audit on disk', 'AI second-screener run — not yet performed')}
        {gateRow(g.have_reconciliation, 'Human reconciliation of disagreements', 'Reconciliation — not yet performed')}
        {gateRow(g.have_metrics, 'Reliability vs blind human (recall + CI)', 'Reliability comparison — not yet run')}
        {gateRow(state?.disclosure_generated, 'AI-use disclosure filled with this run’s models (in the Methods document)', 'AI-use disclosure — press Generate to fill it with this run’s models')}
        {!(g.have_human || g.have_ai) && (
          <div className="warn" style={{ marginTop: 10, fontSize: 12 }}>
            <strong>DRAFT:</strong> no screening artefacts found — the generated Methods text is the <em>intended design</em>,
            clearly banner-marked, not a record of what was run.
          </div>
        )}
        <button className="btn primary" style={{ marginTop: 14 }} disabled={busy} onClick={generate}>
          {busy ? 'Generating…' : 'Generate Methods + BibTeX + PRISMA'}
        </button>
        {gen && (
          gen.ok === false
            ? <div className="warn" style={{ marginTop: 12 }}>{gen.message}</div>
            : <div className="info" style={{ marginTop: 12, fontSize: 12 }}>
                ✓ {gen.message}
                {gen.is_draft && <div style={{ marginTop: 4 }}><strong>DRAFT banner</strong> was added to the Methods document.</div>}
                {(gen.consistency_warnings || []).map((w, i) => <div className="muted" key={i} style={{ marginTop: 4 }}>⚠ {w}</div>)}
              </div>
        )}
      </div></div>

      {/* PRISMA flow */}
      <div className="card"><div className="hd"><h2>PRISMA 2020 study-selection flow</h2></div><div className="bd">
        <PrismaFlow p={prisma} bust={bust} />
      </div></div>

      {/* Screening exports (RIS) — the AI's search set + each arm's kept set, for a reference manager */}
      <div className="card"><div className="hd"><h2>Screening exports (RIS) <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>— for your reference manager</span></h2></div><div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 10, lineHeight: 1.5 }}>
          Import any of these into Mendeley / Zotero / EndNote. “Kept” = the studies a rater did <strong>not</strong> exclude
          (includes + uncertains carried forward) — the set to retrieve full text for. The AI is a <strong>second screener</strong>:
          its kept set is for you to check and reconcile, never to accept blindly.
        </div>
        <RisRow fn="master_records.ris" present={state?.files?.['master_records.ris']}
          label="Database search"
          why="The full de-duplicated set of records from your database search — the input that both you and the AI screened." />
        <RisRow fn="included_ai.ris" present={state?.files?.['included_ai.ris']}
          label="AI screened"
          why={`The studies the AI second-screener kept after ${sr.ai_stage || 'screening'} (did not exclude) — ${sr.ai_kept ?? 0} kept${keptBreakdown(sr.ai_breakdown)}.` +
               (sr.ai_kept ? ' Press Generate to (re)write it.' : ' Run the AI screener, then Generate.')} />
        <RisRow fn="included_human.ris" present={state?.files?.['included_human.ris']}
          label="Human screened"
          why={`The studies you kept in your screening${sr.human_stage ? ` (at ${sr.human_stage})` : ''} — ${sr.human_kept ?? 0} kept${keptBreakdown(sr.human_breakdown)}.` +
               (sr.human_kept ? ' Press Generate to (re)write it.' : ' Screen (or upload your decisions), then Generate.')} />
        <RisRow fn="disagreements.ris" present={state?.files?.['disagreements.ris']}
          label="Disagreements"
          why={(sr.disagreement_comparable === false
                  ? "You and the AI haven't both screened the same records at the same stage yet, so there's nothing to compare. "
                  : `Records where you and the AI disagreed${sr.disagreement_stage ? ` (at ${sr.disagreement_stage})` : ''} — ${sr.disagreements ?? 0} (${sr.ai_keep_human_drop ?? 0} the AI kept but you excluded, ${sr.human_keep_ai_drop ?? 0} you kept but the AI excluded). These are the ones to reconcile — the "AI kept but you excluded" set is the recall-risk one to check first. `)
               + (sr.disagreements ? 'Press Generate to (re)write it.' : 'Appears once both you and the AI have screened the same records.')} />
        <RisRow fn="consensus_included.ris" present={state?.files?.['consensus_included.ris']}
          label="Consensus included"
          why={`Your reconciled included set after settling disagreements — ${sr.consensus_included ?? 0} studies. This is the review's actual included set (not the AI's, not yours alone).` +
               (sr.consensus_included ? ' Press Generate to (re)write it.' : ' Appears after the Reconciliation step (5c).')} />
      </div></div>

      {/* Downloads */}
      <div className="card"><div className="hd"><h2>Downloads</h2></div><div className="bd">
        {DOWNLOADS.map(([fn, label, why]) => (
          <div key={fn} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line)' }}>
            <div style={{ flex: '0 0 250px' }}><strong style={{ fontSize: 13 }}>{label}</strong><div className="muted" style={{ fontSize: 11.5 }}>{why}</div></div>
            {state?.files?.[fn]
              ? <a className="btn" href={'/api/download/' + fn} download>Download</a>
              : <span className="muted" style={{ fontSize: 12 }}>— not built yet —</span>}
          </div>
        ))}
      </div></div>
    </div>
  )
}
