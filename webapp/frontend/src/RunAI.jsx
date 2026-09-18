import { useState } from 'react'
import { api } from './api.js'

// Entry point A — the in-app "Run the AI second screener" action for Stage 5a (title/abstract) and 5b (full
// text). The human screens BLIND first; this triggers the tested LiteLLM screener (temperature=0) over the
// provider/model chosen on Setup, writing the audit the Reconciliation screen already reads. The AI is a SECOND
// screener, never the sole reviewer — the human reconciles every call (concept-dual-screening; the two screening
// playbooks). Mirrors the RoB/extraction Run buttons so screening is no longer the one stage that needs a terminal.
export default function RunAI({ stage, onDone, compact }) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [pilot, setPilot] = useState(false)
  const [n, setN] = useState(10)
  const isFull = stage === 'fulltext'
  const endpoint = isFull ? '/fulltext/run' : '/screening/run'
  const what = isFull ? 'full-text' : 'title/abstract'
  const pilotN = Math.floor(Number(n))
  const pilotValid = !pilot || pilotN >= 1          // a ticked pilot with a blank/0/≤0 count must NOT run everything

  const run = async () => {
    if (pilot && !pilotValid) return                // guard: don't silently launch a full (paid) run
    setBusy(true); setRes(null)
    try {
      const d = await api(endpoint, { method: 'POST', body: { limit: pilot ? pilotN : 0 } })
      setRes(d)
      if (d.ok && onDone) onDone(d)
    } catch (e) { setRes({ ok: false, message: String(e) }) }
    setBusy(false)
  }

  return (
    <div className={compact ? '' : 'card'} style={compact ? { marginTop: 10 } : { marginTop: 12 }}>
      <div className={compact ? '' : 'bd'}>
        {!compact && <strong style={{ fontSize: 13 }}>Run the AI second screener</strong>}
        <p className="muted" style={{ fontSize: 12, lineHeight: 1.6, margin: compact ? '0 0 8px' : '6px 0 10px' }}>
          The AI screens the same {what} records <strong>independently</strong>, using the provider you chose on
          Setup. Your blind decisions stay hidden from it. When it finishes, open <strong>Reconciliation</strong> to
          compare the two calls and settle each disagreement — the AI is a second check, and you make every final call.
        </p>
        <label style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
          <input type="checkbox" checked={pilot} onChange={e => setPilot(e.target.checked)} />
          Pilot on the first
          <input className="input" type="number" min="1" style={{ width: 58 }} value={n}
            onChange={e => setN(e.target.value)} disabled={!pilot} />
          records only
          <span className="muted"> — recommended before a full run (Cochrane pilots the criteria on a handful first)</span>
        </label>
        <div>
          <button className="btn primary" disabled={busy || (pilot && !pilotValid)} onClick={run}>
            {busy ? 'The AI is screening…' : (pilot ? `Run the AI on the first ${pilotValid ? pilotN : '…'}` : 'Run the AI second screener')}
          </button>
          {pilot && !pilotValid && <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>enter how many to pilot (1 or more)</span>}
        </div>
        {res && (
          res.ok
            ? <div className="info" style={{ marginTop: 10, fontSize: 12 }}>
                ✓ The AI finished screening the {what} records{res.pilot ? ` (pilot of ${res.pilot})` : ''}. Open{' '}
                <strong>Reconciliation</strong> to compare its calls with yours and settle any disagreements.
              </div>
            : <div className="warn" style={{ marginTop: 10, fontSize: 12 }}>
                {res.message || 'The AI screening run did not complete.'}
                {res.log && (
                  <details style={{ marginTop: 6 }}>
                    <summary className="muted" style={{ cursor: 'pointer' }}>technical details</summary>
                    <pre className="crit" style={{ marginTop: 6, whiteSpace: 'pre-wrap', fontSize: 11 }}>{res.log}</pre>
                  </details>
                )}
              </div>
        )}
      </div>
    </div>
  )
}
