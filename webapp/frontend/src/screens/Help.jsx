import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Help / Ask — an OKF-grounded Q&A assistant for first-time reviewers. The user's own LLM (their key, local)
// reads the curated concept index, picks the few most relevant notes, and answers grounded in + citing those
// notes. No methodology jargon; every answer links the verified notes it used. If the brain doesn't cover the
// question it says so rather than inventing methodology.

// Minimal, safe rich-text: preserve line breaks and render **bold** — no HTML injection, no markdown dep.
function rich(text) {
  return String(text || '').split('\n').map((line, i) => {
    if (!line.trim()) return <div key={i} style={{ height: '0.55em' }} />
    const parts = line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
      seg.startsWith('**') && seg.endsWith('**')
        ? <strong key={j}>{seg.slice(2, -2)}</strong>
        : <span key={j}>{seg}</span>)
    return <div key={i} style={{ marginBottom: 2 }}>{parts}</div>
  })
}

// The AI-provenance footer for a note — so a reader sees a note is AI-drafted and NOT yet human-verified
// (concept-ai-provenance: the same bookkeeping the project enforces on every node).
function NoteProvenance({ p }) {
  if (!p || !p.ai_model) return null
  const verified = String(p.human_verified).toLowerCase() === 'true'
  return (
    <div style={{ marginTop: 8, fontSize: 10.5, color: 'var(--faint)', fontFamily: 'var(--mono)',
                  borderTop: '1px dashed var(--border)', paddingTop: 6, lineHeight: 1.5 }}>
      <span className={'pill ' + (verified ? 'inc' : 'maybe')} style={{ fontSize: 10, padding: '1px 7px' }}>
        {verified ? '✓ human-verified' : 'AI-drafted · not yet human-verified'}
      </span>
      <div style={{ marginTop: 4 }}>
        drafted by {p.ai_model}{p.ai_provider ? ` (${p.ai_provider})` : ''}
        {p.prompt_version ? ` · prompt ${p.prompt_version}` : ''}
      </div>
    </div>
  )
}

function Source({ s }) {
  const [open, setOpen] = useState(false)
  const [node, setNode] = useState(null)   // { body, provenance } | 'error'
  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && node === null) {
      api('/help/node/' + s.slug)
        .then(d => setNode({ body: d.body || '(empty note)', provenance: d.provenance }))
        .catch(() => setNode('error'))
    }
  }
  return (
    <div style={{ borderTop: '1px solid var(--border)', padding: '8px 0' }}>
      <div onClick={toggle} style={{ cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <span style={{ color: 'var(--blue)', fontWeight: 700, fontSize: 12 }}>{open ? '▾' : '▸'}</span>
        <div>
          <div style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--navy)' }}>{s.title}</div>
          <div className="muted" style={{ fontSize: 11.5 }}>{s.description}</div>
        </div>
      </div>
      {open && (
        <div style={{ background: '#fbfcfd', border: '1px solid var(--border)', borderRadius: 7,
                      padding: '10px 12px', marginTop: 8 }}>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.6, color: '#374151',
                        maxHeight: 320, overflowY: 'auto' }}>
            {node === null ? <span className="muted">Loading…</span>
              : node === 'error' ? 'Could not load this note.'
              : node.body}
          </div>
          {node && node !== 'error' && <NoteProvenance p={node.provenance} />}
        </div>
      )}
    </div>
  )
}

export default function Help() {
  const [state, setState] = useState(null)
  const [q, setQ] = useState('')
  const [turns, setTurns] = useState([])   // newest first: {q, a, sources, nav_ok}
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [cat, setCat] = useState(null)     // active browse category (review stage)
  const [filter, setFilter] = useState('') // filter box over the common questions
  const taRef = useRef(null)

  useEffect(() => {
    api('/help/state').then(s => {
      setState(s)
      if (s?.categories?.length) setCat(s.categories[0].key)
    }).catch(e => setErr(String(e)))
  }, [])

  const ask = async (text) => {
    const question = (text ?? q).trim()
    if (!question || busy || state?.key_present === false) return   // no API key → don't even round-trip
    setBusy(true); setErr('')
    try {
      const r = await api('/help/ask', { method: 'POST', body: { question } })
      if (r.ok) {
        setTurns(t => [{ q: question, a: r.answer, sources: r.sources || [], nav_ok: r.nav_ok }, ...t])
        setQ('')
      } else {
        setErr(r.message || 'The assistant could not answer that.')
      }
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
      taRef.current?.focus()
    }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() }
  }

  const noKey = state && state.key_present === false
  const categories = state?.categories || []
  const activeCat = categories.find(c => c.key === cat) || categories[0]
  const flt = filter.trim().toLowerCase()
  // While the filter box has text, search across EVERY category (and label each hit with its stage);
  // otherwise show just the active tab's questions.
  const shown = flt
    ? categories.flatMap(c => c.questions
        .filter(qq => qq.toLowerCase().includes(flt))
        .map(qq => ({ q: qq, cat: c.label })))
    : (activeCat ? activeCat.questions.map(qq => ({ q: qq, cat: null })) : [])

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 880 }}>
      <div className="info">
        Ask anything about doing a systematic review — the method, the reporting, or how to use this app. Answers come
        from a <strong>curated methodology library</strong> (built from Cochrane, PRISMA and RAISE guidance) and each
        answer <strong>links the notes it used</strong>, so you can check it. Your question is sent to{' '}
        <strong>your own AI provider</strong> ({state?.provider || 'set on Setup'}) using your local key — nothing is
        stored online. If the library doesn’t cover your question, the assistant will say so rather than guess.
      </div>

      {noKey && (
        <div className="warn" style={{ fontSize: 12.5 }}>
          No API key found for <strong>{state.provider}</strong>. Add your key on the <strong>Setup &amp; protocol</strong>{' '}
          screen first — it’s saved locally on your computer and never leaves it.
        </div>
      )}

      <div className="card"><div className="bd" style={{ padding: 16 }}>
        <textarea
          ref={taRef}
          className="input"
          style={{ height: 76, resize: 'vertical', lineHeight: 1.5 }}
          placeholder="e.g. What is recall and why does it matter more than precision in screening?"
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={onKey}
          disabled={busy || noKey}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
          <button className="btn primary" onClick={() => ask()} disabled={busy || !q.trim() || noKey}>
            {busy ? 'Asking…' : 'Ask'}
          </button>
          <span className="muted" style={{ fontSize: 11.5 }}>
            Enter to send · Shift+Enter for a new line
            {state?.n_concepts ? ` · ${state.n_concepts} notes in the library` : ''}
          </span>
        </div>

      </div></div>

      {/* Browse common questions by review stage — a first-time reviewer often doesn't know what to ask. */}
      {categories.length > 0 ? (
        <div className="card"><div className="bd" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <h2 style={{ fontWeight: 600, fontSize: 15, margin: 0 }}>Common questions</h2>
            <input className="input" style={{ maxWidth: 260, height: 34, fontSize: 12.5 }}
              placeholder="Filter these questions…" value={filter}
              onChange={e => setFilter(e.target.value)} />
          </div>

          {!flt && (
            <div className="crit-tabs" style={{ marginTop: 12 }}>
              {categories.map(c => (
                <button key={c.key} className={'crit-tab' + (c.key === cat ? ' active' : '')}
                        onClick={() => setCat(c.key)}>{c.label}</button>
              ))}
            </div>
          )}
          {!flt && activeCat?.blurb && (
            <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>{activeCat.blurb}</div>
          )}

          <div style={{ display: 'grid', gap: 6, marginTop: 12 }}>
            {shown.length === 0 && (
              <div className="muted" style={{ fontSize: 12 }}>
                No common question matches “{filter}”. Type your own question in the box above.
              </div>
            )}
            {shown.map((item, i) => (
              <button key={i} className="help-q" onClick={() => ask(item.q)} disabled={busy || noKey}>
                <span style={{ color: 'var(--blue)', fontWeight: 700, marginRight: 8 }}>?</span>
                <span>{item.q}</span>
                {item.cat && <span className="muted" style={{ fontSize: 10.5, marginLeft: 8 }}>· {item.cat}</span>}
              </button>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>
            Click a question to get a grounded answer, or type your own above.
          </div>
        </div></div>
      ) : (state?.examples?.length > 0 && turns.length === 0 && (
        <div className="card"><div className="bd" style={{ padding: 16 }}>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>Try one of these:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {state.examples.map((ex, i) => (
              <button key={i} className="crit-tab" onClick={() => ask(ex)} disabled={busy || noKey}
                      style={{ fontWeight: 500 }}>{ex}</button>
            ))}
          </div>
        </div></div>
      ))}

      {err && <div className="warn" style={{ fontSize: 12.5 }}>{err}</div>}

      {turns.map((t, i) => (
        <div className="card" key={turns.length - i}>
          <div className="hd"><h2 style={{ fontWeight: 600 }}>{t.q}</h2></div>
          <div className="bd" style={{ padding: 16 }}>
            <div style={{ fontSize: 13.5, lineHeight: 1.65, color: 'var(--ink, #1f2937)' }}>{rich(t.a)}</div>
            <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
              AI-generated help — check it against the linked notes below; it can sound confident and still be wrong.
            </div>
            {t.sources?.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="muted" style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 2 }}>
                  Sources used {t.nav_ok === false ? '(keyword match — the AI’s note picker was unavailable)' : '(click to read the note)'}
                </div>
                {t.sources.map(s => <Source key={s.slug} s={s} />)}
              </div>
            )}
            {(!t.sources || t.sources.length === 0) && (
              <div className="muted" style={{ fontSize: 11.5, marginTop: 12 }}>
                No specific methodology note matched this question.
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
