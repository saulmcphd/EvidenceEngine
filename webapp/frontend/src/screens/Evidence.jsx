import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// Evidence map — the studies INCLUDED in the review and how they relate. No methodology jargon: a researcher
// sees their own studies, not concepts/playbooks. Relationships are bibliographic for now (shared author /
// source / year); data extraction (step 7) later adds the richer semantic links (shared measure/design/outcome).

const doiUrl = (doi) => { const d = String(doi || '').replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').trim(); return d ? 'https://doi.org/' + d : '' }
const shortAuthor = (s) => {
  const first = String(s.authors || '').split(/[;|]| and /)[0] || ''
  const sur = first.includes(',') ? first.split(',')[0].trim() : (first.trim().split(/\s+/).pop() || '')
  return (sur || (s.title || '').slice(0, 16)) + (s.year ? ' ' + s.year : '')
}

// A simple circular relationship graph — fine for the handful-to-dozens of studies a review includes.
function StudyGraph({ studies, edges }) {
  if (studies.length < 2) return null
  const N = studies.length, W = 660, H = 440, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 70
  const pos = {}
  studies.forEach((s, i) => { const a = (i / N) * 2 * Math.PI - Math.PI / 2; pos[s.id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)] })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 700, background: '#fff', border: '1px solid var(--border)', borderRadius: 8 }}>
      {edges.map((e, i) => {
        const p = pos[e.s], q = pos[e.t]; if (!p || !q) return null
        // a semantic link drawn on unreconciled AI extraction is dashed + amber, never a solid blue "verified" edge
        const stroke = e.semantic ? (e.unreconciled ? '#c99a06' : 'var(--blue)') : '#cdd5e0'
        return <line key={i} x1={p[0]} y1={p[1]} x2={q[0]} y2={q[1]} stroke={stroke} strokeWidth={e.semantic ? 2 : 1.5}
          strokeDasharray={e.unreconciled ? '4 3' : undefined}><title>{e.kind}{e.unreconciled ? ' — from unreconciled AI extraction' : ''}</title></line>
      })}
      {studies.map(s => {
        const [x, y] = pos[s.id]
        return (
          <g key={s.id}>
            <circle cx={x} cy={y} r="8" fill="var(--blue)" stroke="#fff" strokeWidth="1.5"><title>{s.title}</title></circle>
            <text x={x} y={y < cy ? y - 13 : y + 22} textAnchor="middle" fontSize="11" fill="var(--navy)">{shortAuthor(s)}</text>
          </g>
        )
      })}
    </svg>
  )
}

export default function Evidence() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const load = useCallback(() => api('/studies/map').then(setData).catch(e => setErr(String(e))), [])
  useEffect(() => { load() }, [load])

  const studies = data?.studies || []
  const hasEdges = (data?.edges || []).length > 0

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 1000 }}>
      <div className="info" style={{ fontSize: 12.5 }}>
        This is your <strong>evidence map</strong> — the studies included in your review and how they relate. It links
        studies that share an <strong>author</strong>, <strong>source</strong>, or <strong>year</strong>
        {data?.has_extraction
          ? <>, and (from your extracted data) the <strong>same design</strong> or a <strong>shared measure</strong>.</>
          : <>; once you extract data (step 7) it will also link studies by <strong>design</strong> and <strong>measure</strong>.</>}
        {' '}These links are <strong>descriptive</strong> — they do <strong>not</strong> mean the studies can be combined
        or pooled. Which studies are similar enough to combine is a separate judgement you make on PICO similarity during
        synthesis (step 8).
      </div>
      {err && <div className="warn">Couldn’t load the evidence map: {err}</div>}

      {!data ? <div className="muted">Loading…</div>
        : data.count === 0 ? (
          <div className="card"><div className="bd">
            <h2 style={{ marginTop: 0 }}>No included studies yet</h2>
            <p className="muted" style={{ lineHeight: 1.7 }}>
              {data.message || 'Finish screening (or run the AI screener), then return — the studies that pass appear here.'}
            </p>
          </div></div>
        ) : (
          <>
            <div className="recon-cards">
              <div className="rc"><div className="n">{data.count}</div><div className="l">Studies included</div></div>
              <div className="rc"><div className="n" style={{ fontSize: 15 }}>{data.stage || '—'}</div><div className="l">Decided at</div></div>
              <div className="rc"><div className="n" style={{ fontSize: 13 }}>{data.decided_by || '—'}</div><div className="l">Based on</div></div>
            </div>
            {data.reconciled === false && (
              <div className="warn" style={{ fontSize: 12 }}>
                These are the <strong>AI second-screener’s</strong> includes, <strong>not yet reconciled by a human</strong>.
                The AI is a second checker — reconcile its decisions (step 5c) before treating this as your final included set.
              </div>
            )}

            {data.summary && (
              <div className="card"><div className="hd"><h2>At a glance</h2></div><div className="bd">
                <div className="muted" style={{ fontSize: 12.5, lineHeight: 1.7 }}>
                  {data.summary.n} included {data.summary.n === 1 ? 'study' : 'studies'}
                  {data.summary.year_min && <> published <strong>{data.summary.year_min}{data.summary.year_max !== data.summary.year_min ? `–${data.summary.year_max}` : ''}</strong>{data.summary.n_with_year < data.summary.n ? ` (year on ${data.summary.n_with_year})` : ''}</>}.
                  {data.summary.sources?.length > 0 && <> Sources: {data.summary.sources.map(s => `${s.name} (${s.n})`).join(', ')}.</>}
                  {' '}
                  {data.summary.designs?.length > 0
                    ? <>Designs: {data.summary.designs.map(d => `${d.name} (${d.n})`).join(', ')}.</>
                    : <span>Run data extraction (step 7) to summarise designs, measures and sample sizes.</span>}
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                  A descriptive overview of the body of evidence — not a synthesis. Write the full narrative summary (totals,
                  ranges, the dominant study, risk of bias as a body) on the Synthesis step.
                </div>
              </div></div>
            )}

            {studies.length >= 2 && (
              <div className="card"><div className="hd"><h2>How the included studies relate</h2></div><div className="bd">
                {hasEdges
                  ? <>
                      <StudyGraph studies={studies} edges={data.edges} />
                      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                        Each dot is an included study; hover a line to see what links the pair.
                        {(data.n_semantic_edges - (data.n_unreconciled_semantic || 0)) > 0
                          ? ' Blue lines mark a shared design or measure (from your extracted data); grey lines are bibliographic (author / source / year).'
                          : ' Grey lines are bibliographic (author / source / year); extract and reconcile data (step 7) to add solid design and measure links.'}
                        {data.n_unreconciled_semantic > 0 && <> <span style={{ color: '#c99a06' }}><strong>Amber dashed</strong> design/measure links rest on the AI's raw extraction you haven’t reconciled yet — reconcile on Data extraction before relying on them.</span></>}
                        {' '}<strong>These are descriptive links, not combinability</strong> — a shared design or measure does
                        not mean two studies can be pooled. You decide which studies are similar enough to combine on PICO
                        similarity during synthesis (step 8).
                      </div>
                    </>
                  : <div className="muted" style={{ fontSize: 12.5 }}>
                      No shared author, source, or year among the included studies yet — extract data (step 7) to surface
                      relationships by measure, design, and outcome.
                    </div>}
              </div></div>
            )}

            <div className="card"><div className="hd"><h2>Included studies ({data.count})</h2></div><div className="bd" style={{ overflowX: 'auto' }}>
              <table className="ext-table">
                <thead><tr><th>Study</th><th>Year</th><th>Authors</th><th>Source</th>{data.has_extraction && <th>Design</th>}<th>Full text</th></tr></thead>
                <tbody>
                  {studies.map(s => (
                    <tr key={s.id}>
                      <td style={{ maxWidth: 420 }}>{s.title || <span className="muted">{s.id}</span>}</td>
                      <td>{s.year}</td>
                      <td style={{ maxWidth: 200 }} className="muted">{s.authors}</td>
                      <td className="muted">{s.source}</td>
                      {data.has_extraction && <td className="muted">{s.design || '—'}{s.design_unreconciled && <span className="warn" title="AI's raw extraction — not yet reconciled" style={{ marginLeft: 4, fontSize: 10 }}>⚠</span>}</td>}
                      <td>{doiUrl(s.doi) ? <a className="ft-inline" href={doiUrl(s.doi)} target="_blank" rel="noreferrer">link ↗</a> : <span className="muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div></div>
          </>
        )}
    </div>
  )
}
