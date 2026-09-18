import { useEffect, useState } from 'react'
import { api } from '../api.js'

// "My reviews" — the multi-review manager (top of Setup). Keep MANY reviews and switch between them; the current
// review is saved automatically on every New/Open (nothing is lost), Delete is recoverable (goes to a trash), and
// the shared methodology library is never touched. Backend: /api/reviews (review_store.py). Switching a review
// changes the whole app's data, so New/Open do a full page reload to re-load every screen for the opened review.
export default function ReviewManager() {
  const [data, setData] = useState(null)          // { active, reviews, trash }
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [newName, setNewName] = useState('')
  const [confirm, setConfirm] = useState(null)    // { action: 'new'|'switch'|'delete', id? }
  const [renaming, setRenaming] = useState(null)  // { id, name }
  const [showTrash, setShowTrash] = useState(false)

  const load = () => api('/reviews').then(d => { if (d.ok === false) setErr(d.message || ''); else setData(d) }).catch(e => setErr(String(e)))
  useEffect(() => { load() }, [])

  const run = async (path, body, { reload = false, after = null } = {}) => {
    setBusy(true); setErr('')
    try {
      const r = await api(path, { method: 'POST', body })
      // On a server-side error, also dismiss the confirm prompt so the destructive button unmounts (no instant
      // re-click / double-submit of a failed op — the adversarial review's finding).
      if (r && r.ok === false) { setErr(r.message || 'That action could not be completed.'); setBusy(false); setConfirm(null); return }
      if (reload) { window.location.reload(); return }   // a review switch re-loads every screen's data
      await load()
      if (after) after()
    } catch (e) { setErr(String(e)) }
    setBusy(false); setConfirm(null)
  }

  if (!data) return null
  const { active, reviews, trash } = data
  const rowStyle = { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderBottom: '1px solid var(--border)' }
  const dangerBtn = { color: 'var(--exc)', borderColor: 'var(--exc)' }

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="hd"><h2>My reviews</h2></div>
      <div className="bd">
        <div className="info" style={{ marginBottom: 12 }}>
          Keep several systematic reviews and switch between them. Your current review is <strong>saved automatically</strong> whenever
          you open another or start a new one — nothing is lost. Deleting a review moves it to a <strong>recoverable trash</strong>.
          The methodology library is shared across all your reviews.
        </div>
        {err && <div className="warn" style={{ marginBottom: 12 }}>{err}</div>}

        {/* The review you're working in now */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: '1px solid var(--blue)', borderRadius: 8, background: 'rgba(37,99,235,0.05)' }}>
          <span className="pill inc">Open now</span>
          {renaming && renaming.id === active.id ? (
            <>
              <input value={renaming.name} onChange={e => setRenaming({ id: active.id, name: e.target.value })}
                style={{ flex: 1 }} aria-label="Review name" />
              <button className="btn primary" disabled={busy}
                onClick={() => run('/reviews/rename', { id: active.id, name: renaming.name }, { after: () => setRenaming(null) })}>Save name</button>
              <button className="btn" onClick={() => setRenaming(null)}>Cancel</button>
            </>
          ) : (
            <>
              <strong style={{ flex: 1 }}>{active.name}</strong>
              <span className="muted" style={{ fontSize: 12 }}>{active.n_records} record{active.n_records === 1 ? '' : 's'}</span>
              <button className="btn" onClick={() => setRenaming({ id: active.id, name: active.name })}>Rename</button>
            </>
          )}
        </div>

        {/* Your other saved reviews */}
        {reviews.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Saved reviews</div>
            {reviews.map(r => (
              <div key={r.id} style={rowStyle}>
                <strong style={{ flex: 1 }}>{r.name}</strong>
                <span className="muted" style={{ fontSize: 12 }}>{r.n_records} record{r.n_records === 1 ? '' : 's'}</span>
                {confirm && confirm.action === 'switch' && confirm.id === r.id ? (
                  <>
                    <span style={{ fontSize: 12 }}>Save your current review and open this one?</span>
                    <button className="btn primary" disabled={busy} onClick={() => run('/reviews/switch', { id: r.id }, { reload: true })}>Open</button>
                    <button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
                  </>
                ) : confirm && confirm.action === 'delete' && confirm.id === r.id ? (
                  <>
                    <span style={{ fontSize: 12, color: 'var(--exc)' }}>Move to trash? You can restore it.</span>
                    <button className="btn" style={dangerBtn} disabled={busy} onClick={() => run('/reviews/delete', { id: r.id })}>Confirm delete</button>
                    <button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
                  </>
                ) : (
                  <>
                    <button className="btn primary" onClick={() => setConfirm({ action: 'switch', id: r.id })}>Open</button>
                    <button className="btn" onClick={() => setConfirm({ action: 'delete', id: r.id })}>Delete</button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Start a new review */}
        <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input className="input" placeholder="New review name (optional)" value={newName} onChange={e => setNewName(e.target.value)}
            style={{ flex: 1, minWidth: 180, padding: '12px 14px', fontSize: 14 }} aria-label="New review name" />
          {confirm && confirm.action === 'new' ? (
            <>
              <span style={{ fontSize: 12 }}>Save your current review and start a new blank one?</span>
              <button className="btn primary" disabled={busy} onClick={() => run('/reviews/new', { name: newName }, { reload: true })}>Create</button>
              <button className="btn" onClick={() => setConfirm(null)}>Cancel</button>
            </>
          ) : (
            <button className="btn primary" onClick={() => setConfirm({ action: 'new' })}>+ New review</button>
          )}
        </div>

        {/* Recoverable trash */}
        {trash.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <button className="btn" onClick={() => setShowTrash(s => !s)}>{showTrash ? 'Hide' : 'Show'} deleted reviews ({trash.length})</button>
            {showTrash && trash.map(t => (
              <div key={t.trash_name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px' }}>
                <span className="muted" style={{ flex: 1 }}>{t.name}</span>
                <button className="btn" disabled={busy} onClick={() => run('/reviews/restore', { trash_name: t.trash_name })}>Restore</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
