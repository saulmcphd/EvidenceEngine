import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

// Search-strategy builder (writes search_terms.json). Lives on the SEARCH step (step 2), where the search is
// actually built and iterated. You name each concept, list its synonyms, and EvidenceEngine composes the Boolean
// string — synonyms joined with OR inside a concept, concepts joined with AND (Cochrane §4.4; NOT avoided by
// default). The same concept groups drive the per-concept tinted highlighting on the screening screens, and the
// CV-enriched per-database version (MeSH / APA Thesaurus + database syntax) comes from the boolean-search-builder
// (boolean-string.md), surfaced here. Self-contained: fetches/saves its own data.

// Old default concept names described the ROLE, not a real concept, and confusingly rendered as a bold value
// the user didn't know to replace. Treat them as empty on load so the grey "Name this concept…" placeholder shows.
const LEGACY_LABELS = new Set(['inclusion terms', 'exclusion terms'])
const cleanLabel = s => (LEGACY_LABELS.has((s || '').trim().toLowerCase()) ? '' : (s || ''))

const splitTerms = s => s.split(/[\n,]/).map(t => t.trim()).filter(Boolean)
const quoteIfPhrase = t => (/\s/.test(t) ? `"${t}"` : t)

// Mirror the backend palettes (app.py _INC_PALETTE / _EXC_PALETTE) so the live swatch matches what the server
// will assign on save (colours are re-derived server-side by role order).
const INC_PALETTE = [['#dcfce7', '#14532d'], ['#ccfbf1', '#115e59'], ['#e0f2fe', '#075985'], ['#ede9fe', '#5b21b6']]
const EXC_PALETTE = [['#fee2e2', '#7f1d1d'], ['#ffedd5', '#9a3412'], ['#fce7f3', '#9d174d']]
const colorFor = (blocks, idx) => {
  const b = blocks[idx]
  const pal = b.role === 'exclude' ? EXC_PALETTE : INC_PALETTE
  const n = blocks.slice(0, idx).filter(x => x.role === b.role).length
  return pal[n % pal.length]
}

// Compose the generic (database-agnostic) Boolean string from the include blocks: synonyms OR'd within a
// concept, concepts AND'd. Exclude blocks are added as a NOT line ONLY when the user explicitly ticks it
// (Cochrane advises avoiding NOT — it can silently drop relevant records).
const compose = (blocks) => {
  const inc = blocks.filter(b => b.role === 'include')
    .map(b => splitTerms(b.termsText)).filter(t => t.length)
    .map(t => '(' + t.map(quoteIfPhrase).join(' OR ') + ')')
  let s = inc.join(' AND ')
  blocks.filter(b => b.role === 'exclude' && b.useNot).forEach(b => {
    const t = splitTerms(b.termsText)
    if (t.length) s += ' NOT (' + t.map(quoteIfPhrase).join(' OR ') + ')'
  })
  return s
}

let _nid = 0
const newBlock = (role = 'include') => ({ _k: `new${_nid++}`, id: '', label: '', role, termsText: '', useNot: false })

export default function SearchTerms() {
  const [blocks, setBlocks] = useState([])
  const [saved, setSaved] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [err, setErr] = useState('')
  const [strategy, setStrategy] = useState(null)   // { exists, boolean_md }
  const [showStrategy, setShowStrategy] = useState(false)
  const [showExclude, setShowExclude] = useState(false)   // exclusion terms are rare — collapsed by default
  const [copied, setCopied] = useState(false)

  const toBlocks = (concepts) => (concepts || []).map(c => ({
    _k: c.id, id: c.id, label: cleanLabel(c.label), role: c.role, termsText: (c.terms || []).join(', '), useNot: false,
  }))

  const load = useCallback(() => {
    api('/search-terms').then(d => { setBlocks(toBlocks(d.concepts)); setDirty(false) }).catch(() => {})
    api('/search-strategy').then(setStrategy).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const edit = (i, patch) => { setBlocks(bs => bs.map((b, j) => (j === i ? { ...b, ...patch } : b))); setDirty(true) }
  const remove = (i) => { setBlocks(bs => bs.filter((_, j) => j !== i)); setDirty(true) }
  const add = () => { setBlocks(bs => [...bs, newBlock('include')]); setDirty(true) }
  const addExclude = () => { setBlocks(bs => [...bs, newBlock('exclude')]); setDirty(true) }

  const save = () => {
    const concepts = blocks.map(b => ({ id: b.id, label: b.label, role: b.role, terms: splitTerms(b.termsText) }))
    api('/search-terms', { method: 'POST', body: { concepts } })
      .then(d => { setBlocks(toBlocks(d.concepts)); setDirty(false); setSaved(true); setTimeout(() => setSaved(false), 2500) })
      .catch(e => setErr(String(e)))
  }
  const reset = () => api('/search-terms/reset', { method: 'POST' })
    .then(d => { setBlocks(toBlocks(d.concepts)); setDirty(false) }).catch(e => setErr(String(e)))

  const boolStr = compose(blocks)
  const includeCount = blocks.filter(b => b.role === 'include').length
  const copy = () => { navigator.clipboard?.writeText(boolStr).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {}) }

  return (
    <div className="card">
      <div className="hd" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Build your search</h2>
        <span style={{ fontSize: 12 }}>
          {saved && <span style={{ color: 'var(--inc)', fontWeight: 600, marginRight: 8 }}>✓ saved</span>}
          <span style={{ color: dirty ? 'var(--blue)' : 'var(--muted)', cursor: 'pointer', fontWeight: dirty ? 600 : 400 }} onClick={save}>save</span>
          {' · '}<span className="muted" style={{ cursor: 'pointer' }} onClick={reset}>reset to criteria</span>
        </span>
      </div>
      <div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.55 }}>
          Name each concept in your question and list its search words (synonyms). EvidenceEngine combines them into a
          search string: words inside one concept are joined with <strong>OR</strong>, and the concepts are joined with
          <strong> AND</strong> (Cochrane §4.4). These concept groups also drive the coloured <strong>highlighting</strong>
          on the screening screens. This is your <em>draft</em> — build it, test it in a database, refine, and save again.
        </div>
        {err && <div className="warn" style={{ marginBottom: 10 }}>{err}</div>}

        <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--navy)', marginBottom: 8 }}>
          Search concepts <span className="muted" style={{ fontWeight: 400 }}>— one per idea in your question (e.g. Population, Intervention), combined with AND</span>
        </div>
        {/* Include concept blocks — combined with AND */}
        {blocks.map((b, i) => (b.role !== 'include' ? null : (
          <div key={b._k}>
            {includeCount > 1 && blocks.slice(0, i).some(x => x.role === 'include') && (
              <div style={{ textAlign: 'center', fontWeight: 700, fontSize: 11, color: 'var(--muted)', margin: '2px 0' }}>AND</div>
            )}
            <div style={{ border: '1px solid var(--line)', borderRadius: 8, padding: 10, marginBottom: 8 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: colorFor(blocks, i)[0], border: '1px solid var(--line)', flex: '0 0 auto' }} />
                <input className="input" style={{ fontSize: 12.5, fontWeight: 600, padding: '5px 9px' }} placeholder="Name this concept — e.g. Population, Intervention, Outcome"
                  value={b.label} onChange={e => edit(i, { label: e.target.value })} />
                <span title="remove this concept" style={{ color: 'var(--exc)', cursor: 'pointer', fontSize: 15, flex: '0 0 auto' }} onClick={() => remove(i)}>×</span>
              </div>
              <div className="muted" style={{ fontSize: 10.5, marginBottom: 3 }}>Synonyms — comma- or line-separated · joined with <strong>OR</strong></div>
              <textarea className="input" style={{ height: 54, fontFamily: 'var(--mono)', fontSize: 11 }}
                placeholder="synonym, related term, abbreviation, spelling variant, …"
                value={b.termsText} onChange={e => edit(i, { termsText: e.target.value })} />
            </div>
          </div>
        )))}
        <button className="btn" style={{ marginBottom: 12 }} onClick={add}>＋ Add concept</button>

        {/* Composed Boolean string */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <strong style={{ fontSize: 12.5 }}>Your search string <span className="muted" style={{ fontWeight: 400 }}>(generic — adapt per database)</span></strong>
            {boolStr && <button className="btn" style={{ fontSize: 11, padding: '3px 10px' }} onClick={copy}>{copied ? '✓ copied' : 'Copy'}</button>}
          </div>
          {boolStr
            ? <div className="mono" style={{ fontSize: 11.5, background: 'var(--bg-soft, #f8fafc)', border: '1px solid var(--line)', borderRadius: 6, padding: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.6 }}>{boolStr}</div>
            : <div className="muted" style={{ fontSize: 12 }}>Add at least one concept with synonyms and the combined string appears here.</div>}
        </div>

        {/* Terms to exclude — collapsed by default (rare; Cochrane discourages NOT in a search) */}
        {!showExclude ? (
          <div style={{ marginBottom: 12 }}>
            <button className="btn" onClick={() => setShowExclude(true)}>
              {blocks.some(b => b.role === 'exclude')
                ? `✎ Edit exclusion terms (${blocks.filter(b => b.role === 'exclude').length})`
                : '＋ Add exclusion terms (optional — rarely needed)'}
            </button>
          </div>
        ) : (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--navy)', marginBottom: 4 }}>
            Terms to exclude <span className="muted" style={{ fontWeight: 400 }}>(optional)</span>
          </div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>
            Words that usually mean a study is <strong>not</strong> relevant (e.g. a wrong population or an animal study). They
            tint those words red on the screening screens to help you spot them. Cochrane advises <strong>avoiding NOT</strong>
            in the actual search — it can silently drop relevant records — so these are <strong>not</strong> added to your
            search string unless you tick "use as NOT" for a good, documented reason.
          </div>
          {blocks.map((b, i) => (b.role !== 'exclude' ? null : (
            <div key={b._k} style={{ border: '1px solid var(--line)', borderRadius: 8, padding: 10, marginBottom: 8 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                <span style={{ width: 12, height: 12, borderRadius: 3, background: colorFor(blocks, i)[0], border: '1px solid var(--line)', flex: '0 0 auto' }} />
                <input className="input" style={{ fontSize: 12.5, fontWeight: 600, padding: '5px 9px' }} placeholder="Name this exclusion group — e.g. wrong population, animal studies"
                  value={b.label} onChange={e => edit(i, { label: e.target.value })} />
                <span title="remove" style={{ color: 'var(--exc)', cursor: 'pointer', fontSize: 15, flex: '0 0 auto' }} onClick={() => remove(i)}>×</span>
              </div>
              <textarea className="input" style={{ height: 46, fontFamily: 'var(--mono)', fontSize: 11 }}
                placeholder="term to exclude, related term, …"
                value={b.termsText} onChange={e => edit(i, { termsText: e.target.value })} />
              <label className="muted" style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 6, marginTop: 5 }}>
                <input type="checkbox" checked={b.useNot} onChange={e => edit(i, { useNot: e.target.checked })} />
                Add this as a <span className="mono">NOT</span> line in the search (discouraged — justify it)
              </label>
            </div>
          )))}
          <button className="btn" onClick={addExclude}>＋ Add exclusion term</button>
        </div>
        )}

        {/* Per-database strategy (boolean-string.md, CV-enriched) */}
        <div className="info" style={{ marginTop: 6, fontSize: 12 }}>
          The string above is a <strong>generic</strong> combination of your synonyms. A search must be
          <strong> rebuilt per database</strong> with each one's index terms (MeSH for PubMed, the APA Thesaurus for
          PsycINFO) and syntax (Cochrane §4.4). Ask EvidenceEngine to build that full per-database strategy
          {' '}from your eligibility criteria.
          {strategy?.exists
            ? <> {' '}<a style={{ color: 'var(--blue)', cursor: 'pointer', fontWeight: 600 }} onClick={() => setShowStrategy(s => !s)}>{showStrategy ? 'hide' : 'view'} full strategy</a>
                {' · '}<a className="mono" href="/api/download/boolean-string.md" download style={{ color: 'var(--blue)' }}>download</a></>
            : <> {' '}<span className="muted">(not generated yet)</span></>}
        </div>
        {showStrategy && strategy?.boolean_md && (
          <pre className="mono" style={{ fontSize: 11, background: 'var(--bg-soft, #f8fafc)', border: '1px solid var(--line)', borderRadius: 6, padding: 12, marginTop: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 340, overflow: 'auto' }}>{strategy.boolean_md}</pre>
        )}

        <div className="info" style={{ marginTop: 8, fontSize: 12 }}>
          <strong>A search is built by iteration, not in one go.</strong> Draft it, run it in a database, look at what
          comes back, then refine the terms (add synonyms, adjust AND/OR, reconsider databases) and save again — repeat
          until it captures the relevant studies without too much noise, and log each version in the search log below.
          If the results are unmanageably large, it’s legitimate to <strong>tighten the review’s scope</strong> (a
          narrower date range, population, or design) and record why. Ask <strong>Help / Ask</strong> about
          “iterative search strategy” for the full method.
        </div>
      </div>
    </div>
  )
}
