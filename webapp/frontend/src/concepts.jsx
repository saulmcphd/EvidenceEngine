// Shared concept-grouped highlighting + concept-coverage (used by 5a and 5b).
// Deterministic, criteria/search-term driven → blind-safe (NOT an AI signal). Each eligibility
// CONCEPT (e.g. "Adult attachment") carries its full synonym set; matches are tinted by concept so the
// reviewer sees which criterion a word belongs to.

export function highlightByConcept(text, concepts) {
  if (!text) return null
  if (!concepts || !concepts.length) return text
  const inc = concepts.filter(c => c.role === 'include')
  const exc = concepts.filter(c => c.role === 'exclude')
  const entries = []
  const seen = new Set()
  for (const c of [...inc, ...exc]) {                 // include concepts first → win on overlap
    for (const t of c.terms || []) {
      const k = String(t).toLowerCase()
      if (String(t).length >= 2 && !seen.has(k)) { seen.add(k); entries.push({ t, color: c.color, text: c.text }) }
    }
  }
  if (!entries.length) return text
  entries.sort((a, b) => b.t.length - a.t.length)     // longest term first so "secure attachment" beats "attachment"
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // word-boundary + optional plural: matches "romantic relationship(s)" / "couple(s)" but not "ecr" inside "secret"
  const re = new RegExp('(?<![a-z0-9])(' + entries.map(e => esc(e.t)).join('|') + ')(es|s)?(?![a-z0-9])', 'gi')
  const map = new Map(entries.map(e => [e.t.toLowerCase(), e]))
  const out = []
  let last = 0, m, i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(<span key={i++}>{text.slice(last, m.index)}</span>)
    const e = map.get(m[1].toLowerCase())
    out.push(<mark key={i++} className="hl" style={{ background: e.color, color: e.text }}>{m[0]}</mark>)
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(<span key={i++}>{text.slice(last)}</span>)
  return out
}

// "Concepts mentioned" strip: which inclusion criteria's vocabulary appears, and which exclusion
// concepts are triggered. It flags vocabulary PRESENCE, not an eligibility decision — the reviewer
// still reads the context (e.g. "social support was NOT measured" still mentions support).
export function CoverageStrip({ coverage }) {
  if (!coverage || !coverage.length) return null
  const inc = coverage.filter(c => c.role === 'include')
  const exc = coverage.filter(c => c.role === 'exclude' && c.matched)
  return (
    <div className="coverage">
      <span className="cov-label">Concepts mentioned</span>
      {inc.map(c => (
        <span key={c.id} className={'cov-chip' + (c.matched ? '' : ' off')}
          title={c.hits && c.hits.length ? c.hits.join(', ') : 'no matching term in this record'}
          style={c.matched ? { background: c.color, color: c.text, borderColor: c.color } : undefined}>
          {c.matched ? '✓' : '○'} {c.label}
        </span>
      ))}
      {exc.map(c => (
        <span key={c.id} className="cov-chip" title={c.hits.join(', ')}
          style={{ background: c.color, color: c.text, borderColor: c.color }}>⚠ {c.label}</span>
      ))}
    </div>
  )
}
