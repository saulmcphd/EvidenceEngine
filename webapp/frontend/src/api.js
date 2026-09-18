// Tiny fetch wrapper for the local FastAPI backend (same origin in production; proxied in dev).
export async function api(path, opts = {}) {
  const res = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if (!res.ok) throw new Error('API ' + res.status + ' on ' + path)
  return res.json()
}
