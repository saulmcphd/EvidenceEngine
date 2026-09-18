import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api.js'
import SearchTerms from './SearchTerms.jsx'

// §2 Search & records — turn raw database exports into the de-duplicated master set with stable REC_NNNN
// ids + per-screener BLIND randomised orders, by REUSING master_records.py (POST /api/upload). Plus the
// search-strategy builder, the researcher-facing downloads, the search log, and an optional gap check.
// (Entry point B — "already screened elsewhere? upload it" — now lives on the Abstract screening step.)
// The screening_orders.csv this writes is exactly what Stage 5a + the fatigue study read.

const doiUrl = (doi) => { const d = String(doi || '').replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').trim(); return d ? 'https://doi.org/' + d : '' }

// Whole calendar months between an ISO date (YYYY-MM-DD) and today; null if unparseable.
const monthsSinceISO = (iso) => {
  const d = new Date(String(iso || '').slice(0, 10) + 'T00:00:00')
  if (isNaN(d.getTime())) return null
  const now = new Date()
  let m = (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth())
  if (now.getDate() < d.getDate()) m -= 1
  return m < 0 ? 0 : m
}

// Search currency (Cochrane C37, mandatory): a review should be published within ~12 months of the initial
// search (6 preferred), and the remedy for an ageing search is to RERUN ALL DATABASES and screen the delta.
// So we flag on each database's MOST-RECENT search (a rerun logged as a new row refreshes that database), then
// take the database whose latest search is oldest — un-rerun databases still surface, but a full rerun clears it.
const searchCurrency = (entries) => {
  const byDb = new Map()                   // normalised database name -> its most-recent search age (months)
  for (const e of (entries || [])) {
    const age = monthsSinceISO(e.date)
    if (age === null) continue
    const key = String(e.database || '').trim().toLowerCase() || '(unnamed)'
    const prev = byDb.get(key)
    if (prev === undefined || age < prev) byDb.set(key, age)   // keep the smallest age = latest search
  }
  if (!byDb.size) return { level: 'none' }
  const months = Math.max(...byDb.values())    // the database searched longest ago governs currency
  const level = months > 12 ? 'stale' : months > 6 ? 'ageing' : 'current'
  return { level, months }
}
const CURRENCY_STYLE = {
  current: { fg: '#15803d', bg: '#dcfce7', label: 'Search is current' },
  ageing: { fg: '#b45309', bg: '#fef3c7', label: 'Search is ageing' },
  stale: { fg: '#b91c1c', bg: '#fee2e2', label: 'Search is out of date' },
}

const DOWNLOADS = [
  ['master_records.ris', 'Master records (RIS)', 'Import into Mendeley / Zotero / EndNote to screen by hand.'],
  ['master_records.csv', 'Master records (CSV)', 'The spreadsheet the AI screener reads (the internal join spine).'],
  ['screening_orders.csv', 'Per-screener orders (CSV)', 'One blind randomised order per screener (the fatigue study reads this).'],
  ['stage_counts.json', 'PRISMA counts (JSON)', 'Identified / duplicates removed / after-dedup — feeds the PRISMA diagram.'],
]

// Search log — one row per search session: date, database, string, and number of hits.
// PRISMA requires every search to be reproducible; logging it here means you have it when writing up.
function SearchLog() {
  const [entries, setEntries] = useState([])
  const EMPTY = { date: '', database: '', iface: '', coverage: '', string: '', n_hits: '', limits: '' }
  const [draft, setDraft] = useState(EMPTY)
  const [adding, setAdding] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => { api('/search-log').then(d => setEntries(d.entries || [])).catch(() => {}) }, [])

  const persist = (next) => {
    api('/search-log', { method: 'POST', body: { entries: next } })
      .then(() => { setSaved(true); setTimeout(() => setSaved(false), 2000) }).catch(() => {})
  }
  const addRow = () => {
    if (!draft.database.trim() && !draft.string.trim()) return
    const next = [...entries, { ...draft, date: draft.date || new Date().toISOString().slice(0, 10) }]
    setEntries(next); persist(next); setDraft(EMPTY); setAdding(false)
  }
  const remove = (i) => { const next = entries.filter((_, j) => j !== i); setEntries(next); persist(next) }

  const cur = searchCurrency(entries)

  // Client-side CSV so the button always matches what's on screen (the backend also writes the same
  // search-record-table.csv to disk on save, as the reproducibility artefact).
  const downloadCsv = () => {
    const cols = [['date', 'Date searched'], ['database', 'Database (full name)'], ['iface', 'Interface / version'],
      ['coverage', 'Coverage dates'], ['string', 'Search string (exact, as run)'], ['n_hits', 'Hits (n)'],
      ['limits', 'Limits applied + justification']]
    const esc = (v) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s }
    const rows = [cols.map(c => c[1]).join(',')]
    entries.forEach(e => rows.push(cols.map(c => esc(e[c[0]])).join(',')))
    const blob = new Blob(['\ufeff' + rows.join('\r\n')], { type: 'text/csv;charset=utf-8' })  // BOM → Excel
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'search-record-table.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card">
      <div className="hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Search log</h2>
        <span className="muted" style={{ fontSize: 11.5 }}>
          PRISMA requires every search to be reproducible — log each session here.{saved && <span style={{ color: 'var(--inc)', fontWeight: 600, marginLeft: 8 }}>✓ saved</span>}
        </span>
      </div>
      <div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Record each search as you run it (it’s nearly impossible to reconstruct later — Cochrane C36). Capture the
          <strong> full database name + interface/version</strong> and its <strong>coverage dates</strong> (the same
          database differs by interface — a 1948– vs 1996– MEDLINE gives different results), the <strong>date you ran
          it</strong>, the <strong>exact string</strong>, the <strong>hits</strong>, and any <strong>limits</strong>
          applied (with a justification — C35). Feeds the Methods write-up + PRISMA items 6–7 (information sources &amp; search strategy). One row per database per date.
        </div>
        {cur.level !== 'none' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <span style={{ background: CURRENCY_STYLE[cur.level].bg, color: CURRENCY_STYLE[cur.level].fg,
              fontWeight: 600, fontSize: 12, padding: '3px 10px', borderRadius: 12, whiteSpace: 'nowrap' }}>
              {CURRENCY_STYLE[cur.level].label} · {cur.months === 0 ? 'all databases searched this month' : `oldest database last searched ${cur.months} month${cur.months === 1 ? '' : 's'} ago`}
            </span>
            <span className="muted" style={{ fontSize: 11, lineHeight: 1.5 }}>
              {cur.level === 'stale'
                ? 'A review should be published within ~12 months of the initial search (Cochrane C37, mandatory). Rerun every database and screen the new records before writing up — then log each rerun as a new row here to refresh this.'
                : cur.level === 'ageing'
                ? 'Cochrane advises publishing within ~12 months of the initial search (6 preferred). Plan to rerun the databases and screen the new records before writing up; log each rerun as a new row here.'
                : 'Within the ~12-month currency window (Cochrane C37). If screening runs long, rerun before writing up and log the rerun here.'}
            </span>
          </div>
        )}
        {entries.length > 0 && (
          <div style={{ overflowX: 'auto', marginBottom: 10 }}>
            <table className="ext-table">
              <thead><tr><th>Date</th><th>Database / interface</th><th>Coverage</th><th>Search string</th><th>Hits</th><th>Limits &amp; justification</th><th></th></tr></thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{e.date || '—'}</td>
                    <td style={{ fontSize: 12 }}>{e.database || '—'}{e.iface && <div className="muted" style={{ fontSize: 10.5 }}>{e.iface}</div>}</td>
                    <td style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>{e.coverage || <span className="muted">—</span>}</td>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 11, maxWidth: 340 }}>{e.string || '—'}</td>
                    <td style={{ fontSize: 12 }}>{e.n_hits ?? '—'}</td>
                    <td style={{ fontSize: 11, maxWidth: 160 }}>{e.limits || <span className="muted">none</span>}</td>
                    <td><span style={{ color: 'var(--exc)', cursor: 'pointer', fontSize: 11 }} onClick={() => remove(i)}>×</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!adding ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" onClick={() => setAdding(true)}>＋ Log a search</button>
            {entries.length > 0 && (
              <button className="btn" onClick={downloadCsv} title="A one-row-per-search table for your methods appendix (Cochrane §4.5)">⬇ Download search-record table (CSV)</button>
            )}
          </div>
        ) : (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr 1fr', gap: 8, alignItems: 'end' }}>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Date searched</h3>
                <input className="input" type="date" value={draft.date} onChange={e => setDraft(d => ({ ...d, date: e.target.value }))} />
              </label>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Database (full name)</h3>
                <input className="input" placeholder="e.g. MEDLINE" value={draft.database} onChange={e => setDraft(d => ({ ...d, database: e.target.value }))} />
              </label>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Interface / version</h3>
                <input className="input" placeholder="e.g. Ovid" value={draft.iface} onChange={e => setDraft(d => ({ ...d, iface: e.target.value }))} />
              </label>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr 90px', gap: 8, alignItems: 'end', marginTop: 8 }}>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Coverage dates</h3>
                <input className="input" placeholder="e.g. 1946–present" value={draft.coverage} onChange={e => setDraft(d => ({ ...d, coverage: e.target.value }))} />
              </label>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Search string (exact, as run)</h3>
                <input className="input mono" style={{ fontSize: 11 }} placeholder='e.g. ("term1" OR "term2"/) AND ("term3" OR "term4") …' value={draft.string} onChange={e => setDraft(d => ({ ...d, string: e.target.value }))} />
              </label>
              <label className="fld" style={{ marginBottom: 0 }}><h3>Hits (n)</h3>
                <input className="input" type="number" min="0" value={draft.n_hits} onChange={e => setDraft(d => ({ ...d, n_hits: e.target.value }))} />
              </label>
            </div>
            <label className="fld" style={{ marginBottom: 0, marginTop: 8 }}><h3>Limits applied + justification (leave blank if none — MECIR C35 discourages unjustified limits)</h3>
              <input className="input" placeholder="e.g. English only — no translation capacity (a known bias); or: none" value={draft.limits} onChange={e => setDraft(d => ({ ...d, limits: e.target.value }))} />
            </label>
            <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
              <button className="btn primary" onClick={addRow}>Add</button>
              <button className="btn" onClick={() => { setAdding(false); setDraft(EMPTY) }}>Cancel</button>
            </div>
          </div>
        )}
        <div className="muted" style={{ fontSize: 11, marginTop: 10, lineHeight: 1.5 }}>
          Also log <strong>non-database</strong> activity as its own row — reference-list (backward-citation) checking of
          included studies (mandatory, Cochrane C30), plus forward-citation searching and contacting authors — so the
          PRISMA flow and Methods are complete. Save/screenshot each strategy exactly as run (never re-type it — errors creep in).
        </div>
      </div>
    </div>
  )
}

export default function Search() {
  const [state, setState] = useState(null)
  const [files, setFiles] = useState([])
  const [nScreeners, setNScreeners] = useState(5)
  const [seed, setSeed] = useState(42)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const [drag, setDrag] = useState(false)
  const [gap, setGap] = useState(null)
  const [gapBusy, setGapBusy] = useState(false)
  const fileRef = useRef(null)

  const load = useCallback(() => api('/master').then(setState).catch(e => setErr(String(e))), [])
  useEffect(() => { load() }, [load])

  const onFiles = (list) => setFiles([...list].filter(f => /\.(csv|ris|txt)$/i.test(f.name)))

  const build = async () => {
    if (!files.length) return
    setBusy(true); setErr(''); setNote('')
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    fd.append('n_screeners', String(nScreeners)); fd.append('seed', String(seed))
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: fd })
      const d = await res.json()
      if (d.error) setErr(d.message || d.error)
      else { setState(d); setNote(d.note || ''); setFiles([]) }
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const runGap = () => { setGapBusy(true); api('/gapcheck').then(setGap).catch(e => setGap({ available: false, message: String(e) })).finally(() => setGapBusy(false)) }

  const Cards = () => (
    <div className="recon-cards" style={{ marginTop: 14 }}>
      <div className="rc"><div className="n">{state.identified ?? '—'}</div><div className="l">Records identified</div></div>
      <div className="rc dis"><div className="n">{state.duplicates ?? '—'}</div><div className="l">Duplicates removed</div></div>
      <div className="rc"><div className="n">{state.unique ?? '—'}</div><div className="l">Unique master records</div></div>
      <div className="rc"><div className="n">{state.n_screeners ?? '—'}</div><div className="l">Blind screener orders</div></div>
    </div>
  )

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 980 }}>
      <div className="info">
        Upload your database exports and EvidenceEngine removes duplicate papers, gives each a stable ID, and writes the
        files the rest of the pipeline reads — the master list, a RIS for your reference manager, and a separate blind
        randomised order per screener. <strong>De-duplication is assisted, not final:</strong> skim the list for near-duplicates
        the matcher missed before you screen. The AI decides nothing here — it is a second screener later.
      </div>
      {err && <div className="warn">Couldn’t build the master set: {err}</div>}

      {/* 0 — search-term concepts: build/refine the search blocks here (moved off Setup — this is the search step) */}
      <SearchTerms />

      {/* 1 — upload + build */}
      <div className="card">
        <div className="hd"><h2>Upload database exports → master records</h2></div>
        <div className="bd">
          <div className={'dropzone' + (drag ? ' over' : '')}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); onFiles(e.dataTransfer.files) }}
            onClick={() => fileRef.current?.click()}>
            <input ref={fileRef} type="file" multiple accept=".csv,.ris,.txt" style={{ display: 'none' }}
              onChange={e => onFiles(e.target.files)} />
            {files.length
              ? <div><strong>{files.length} file(s) ready:</strong> <span className="muted">{files.map(f => f.name).join(', ')}</span></div>
              : <div className="muted">Drag &amp; drop database export(s) here, or click to choose — <span className="mono">.csv</span> or <span className="mono">.ris</span> (one or more databases).</div>}
          </div>

          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'flex-end', marginTop: 14 }}>
            <label className="fld" style={{ width: 200, marginBottom: 0 }}><h3>Number of blind screeners</h3>
              <input className="input" type="number" min="1" max="26" value={nScreeners}
                onChange={e => setNScreeners(e.target.value)} />
            </label>
            <label className="fld" style={{ width: 220, marginBottom: 0 }}><h3>Random-order number (advanced)</h3>
              <input className="input" type="number" min="0" value={seed} onChange={e => setSeed(e.target.value)} />
            </label>
            <button className="btn primary" disabled={!files.length || busy} onClick={build}>
              {busy ? 'Building…' : 'Build master records'}
            </button>
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
            <strong>≥ 5 screeners</strong> enables the mixed-effects fatigue model (a random intercept per screener);
            3–4 falls back to fixed effects; &lt; 3 is descriptive only. The <strong>random-order number</strong> (a
            “seed”) just makes each screener’s shuffled reading order repeatable, so the study is reproducible — leave it
            as 42 unless you need to recreate a specific order.
          </div>
          {note && <div className="info" style={{ marginTop: 12, fontSize: 12 }}>{note}</div>}
          {state?.has_master && <Cards />}
        </div>
      </div>

      {/* 2 — downloads */}
      <div className="card">
        <div className="hd"><h2>Your files</h2></div>
        <div className="bd">
          {DOWNLOADS.map(([fn, label, why]) => (
            <div key={fn} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: '1px solid var(--line)' }}>
              <div style={{ flex: '0 0 230px' }}><strong style={{ fontSize: 13 }}>{label}</strong><div className="muted" style={{ fontSize: 11.5 }}>{why}</div></div>
              {state?.files?.[fn]
                ? <a className="btn" href={'/api/download/' + fn} download>Download</a>
                : <span className="muted" style={{ fontSize: 12 }}>— not built yet —</span>}
            </div>
          ))}
        </div>
      </div>

      {/* 3 — master manifest */}
      {state?.has_master && (
        <div className="card">
          <div className="hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2>Master records ({state.records_total})</h2>
            {state.records_shown < state.records_total && <span className="muted" style={{ fontSize: 11.5 }}>showing first {state.records_shown}</span>}
          </div>
          <div className="bd" style={{ overflowX: 'auto' }}>
            <table className="ext-table">
              <thead><tr><th>record_id</th><th>Title</th><th>Year</th><th>Authors</th><th>Source</th><th>DOI</th></tr></thead>
              <tbody>
                {state.records.map(r => (
                  <tr key={r.record_id}>
                    <td className="mono">{r.record_id}</td>
                    <td style={{ maxWidth: 380 }}>{r.title}</td>
                    <td>{r.year}</td>
                    <td style={{ maxWidth: 160 }} className="muted">{r.authors}</td>
                    <td className="muted">{r.source_db}</td>
                    <td>{doiUrl(r.doi) ? <a className="ft-inline" href={doiUrl(r.doi)} target="_blank" rel="noreferrer">link ↗</a> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* (entry point B — "already screened elsewhere?" — moved to the Abstract screening step, where it belongs
          as the alternative to screening in the app.) */}

      {/* search log (PRISMA items 6–7 reproducibility) */}
      <SearchLog />

      {/* 6 — optional gap check */}
      <div className="card">
        <div className="hd"><h2>Gap check <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>(optional · needs internet)</span></h2></div>
        <div className="bd">
          <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
            A quick coverage audit: queries OpenAlex for your review topic and lists recent papers <strong>not already in
            your master set</strong> — candidate studies your search may have missed, to check by hand. This is a
            relevance-ranked sample, <strong>not</strong> an exhaustive Boolean search, and isn’t a substitute for the
            full search strategy.
          </div>
          <button className="btn" disabled={!state?.has_master || gapBusy} onClick={runGap}>{gapBusy ? 'Checking…' : 'Run gap check'}</button>
          {gap && !gap.available && <div className="warn" style={{ marginTop: 10 }}>{gap.message}</div>}
          {gap && gap.available && (
            <div style={{ marginTop: 12 }}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Topic “{gap.topic}” · OpenAlex returned {gap.openalex_returned} · {gap.candidates.length} not in your {gap.in_master} master records:</div>
              {gap.candidates.length
                ? <table className="ext-table"><thead><tr><th>Title</th><th>Year</th><th>Venue</th><th>DOI</th></tr></thead>
                    <tbody>{gap.candidates.map((c, i) => (
                      <tr key={i}><td style={{ maxWidth: 420 }}>{c.title}</td><td>{c.year}</td><td className="muted" style={{ maxWidth: 160 }}>{c.venue}</td>
                        <td>{doiUrl(c.doi) ? <a className="ft-inline" href={doiUrl(c.doi)} target="_blank" rel="noreferrer">link ↗</a> : <span className="muted">—</span>}</td></tr>
                    ))}</tbody></table>
                : <div className="info" style={{ fontSize: 12 }}>No new candidates in this sample — your master set already covers the top OpenAlex hits.</div>}
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{gap.note}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
