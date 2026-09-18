import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api.js'

// §8 Reliability — RECALL-FIRST. How good is the AI second screener? Lead with recall + 95% CI; everything
// else is small + secondary (RAISE 2 / concept-recall-first-screening). All DEMO until a real blind run.
// Reuses reliability.py via the backend (run_screening / fatigue_model). Grades BOTH screening stages — a
// title/abstract (5a) panel AND a full-text (5b) panel side by side (playbook-reliability line 166). The
// full-text arm drops 'awaiting' (couldn't get/read = not an include/exclude judgement). On the sample
// (blank human decisions) recall is honestly NOT ESTIMABLE; a labelled SYNTHETIC example shows the layout.

const bad = v => v == null || (typeof v === 'number' && Number.isNaN(v)) || (typeof v === 'string' && (v.trim() === '' || v.trim().toLowerCase() === 'nan')) || Number.isNaN(Number(v))
const pct = (v, d = 0) => bad(v) ? '—' : (Number(v) * 100).toFixed(d) + '%'
const num = (v, d = 2) => bad(v) ? '—' : Number(v).toFixed(d)

// a tiny interval visual: CI bar + point + a 0 marker, for the fatigue coefficient
function IntervalBar({ lo, hi, point }) {
  if (lo == null || hi == null) return null
  const vals = [lo, hi, point, 0].filter(v => v != null)
  let min = Math.min(...vals), max = Math.max(...vals)
  const pad = (max - min) * 0.15 || 0.1; min -= pad; max += pad
  const x = v => ((v - min) / (max - min) * 100)
  return (
    <div className="ci-track">
      <div className="ci-zero" style={{ left: x(0) + '%' }} title="no effect (0)" />
      <div className="ci-bar" style={{ left: x(lo) + '%', width: (x(hi) - x(lo)) + '%' }} />
      {point != null && <div className="ci-dot" style={{ left: x(point) + '%' }} />}
    </div>
  )
}

// Recall broken down by subgroup (study design, source database, abstract length), read from rel.per_stratum.
// A strong AVERAGE recall can hide poor recall in one kind of study (RAISE Part 2 §2.1); small subgroups get
// wide CIs + a ⚠, and subgroups too small/absent are SHOWN as such, never dropped (prefer-completeness-no-silent-narrowing).
function StratifiedTable({ per }) {
  // Surface a join/compute error rather than silently vanishing (prefer-completeness-no-silent-narrowing).
  if (per && per._error) return (
    <div className="card" style={{ marginBottom: 10 }}><div className="bd">
      <div className="dlab" style={{ marginBottom: 4 }}>Recall by subgroup (stratified)</div>
      <div className="muted" style={{ fontSize: 11.5 }}>Subgroup recall could not be computed: {per._error}</div>
    </div></div>
  )
  const panels = Object.entries(per || {}).filter(([k]) => !k.startsWith('_'))
  if (!panels.length) return null
  return (
    <div className="card" style={{ marginBottom: 10 }}><div className="bd">
      <div className="dlab" style={{ marginBottom: 6 }}>Recall by subgroup (stratified)</div>
      <div className="muted" style={{ fontSize: 11, marginBottom: 8, lineHeight: 1.55 }}>
        A strong <em>average</em> recall can mask much poorer recall on one type of study (RAISE Part 2 §2.1). Each
        subgroup is small, so read these as <strong>exploratory</strong> — note the wide intervals and the ⚠ on
        small subgroups; every recall here is still capped by the blind-human reference.
      </div>
      {panels.map(([key, p]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 3 }}>{p.label}</div>
          {!p.available ? <div className="muted" style={{ fontSize: 11.5 }}>{p.note}</div> : (
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
              <thead><tr style={{ textAlign: 'left', color: 'var(--muted)', fontSize: 11 }}>
                <th style={{ padding: '3px 8px 3px 0' }}>Subgroup</th><th>Recall</th>
                <th style={{ padding: '0 8px' }}>95% CI</th><th>Relevant (n)</th>
                <th style={{ padding: '0 8px' }}>Missed</th><th>Gate</th>
              </tr></thead>
              <tbody>
                {p.strata.map((s, i) => (
                  <tr key={i} style={{ borderTop: '1px solid rgba(0,0,0,.08)' }}>
                    <td style={{ padding: '3px 8px 3px 0' }}>{s.stratum}
                      {s.small && <span title="small sample — wide CI, interpret with caution" style={{ color: 'var(--exc)' }}> ⚠</span>}</td>
                    <td style={{ fontWeight: 600 }}>{s.estimable ? pct(s.recall, 1) : '—'}</td>
                    <td className="muted" style={{ padding: '0 8px' }}>{s.estimable && s.ci ? `${pct(s.ci[0], 1)}–${pct(s.ci[1], 1)}` : (s.note || 'not estimable')}</td>
                    <td>{s.positives ?? s.n ?? '—'}</td>
                    <td style={{ padding: '0 8px', color: s.missed_FN ? 'var(--exc)' : undefined }}>{s.missed_FN ?? '—'}</td>
                    <td>{s.estimable ? <span className={'pill ' + (s.passes ? 'inc' : 'exc')} style={{ fontSize: 10.5, padding: '1px 7px', opacity: s.small ? 0.6 : 1 }}>{s.passes ? 'pass' : 'not met'}{s.small ? ' (small n)' : ''}</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </div>
      ))}
    </div></div>
  )
}

// One screening-stage panel: recall HERO + acceptance gate + secondary measures, read entirely from `rel`
// (the /api/reliability payload for that stage). Rendered twice — once for 5a, once for 5b — so the two
// stages never share a number. The a-priori/default threshold + its provenance are page-level (one bar).
function StagePanel({ title, subtitle, rel, independent, onExample }) {
  const m = rel?.metrics
  const acc = m?.acceptance || {}
  const ci = m?.recall_95ci_twosided || [null, null]
  const recall = m?.recall_HEADLINE
  const passes = acc.passes_headline
  const thr = acc.recall_threshold ?? rel?.threshold
  const kap = m?.kappa_secondary || {}
  return (
    <div className="card"><div className="hd" style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <h2 style={{ margin: 0 }}>{title}</h2>
      <span className="muted" style={{ fontSize: 12 }}>{subtitle}</span>
    </div><div className="bd">
      {!rel ? <div className="muted">Loading…</div>
        : rel.needs_data ? (
          <div>
            <p className="muted" style={{ lineHeight: 1.7, marginTop: 0 }}>{rel.message}</p>
            <button className="btn" onClick={onExample}>Show a worked example (synthetic)</button>
          </div>
        ) : rel.ok === false ? (
          <div className="warn">{rel.message || 'Could not compute reliability from the files on disk.'}
            <span style={{ display: 'block', marginTop: 6 }}><button className="btn" onClick={onExample}>Show a worked example (synthetic)</button></span></div>
        ) : (
          <>
            {/* HERO — recall */}
            <div className="card hero" style={{ marginBottom: 12 }}><div className="bd">
              <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 200 }}>
                  <div className="dlab">Recall (sensitivity) — the headline</div>
                  <div className="hero-num">{pct(recall, 1)}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {recall != null
                      ? <>95% CI {pct(ci[0], 1)} – {pct(ci[1], 1)} · on {m.positives_in_human} relevant studies</>
                      : <>Not estimable — no human <em>include</em> decisions on disk yet. Screen some records (or upload your decisions), then return.</>}
                  </div>
                </div>
                {recall != null && (
                  <div style={{ minWidth: 180 }}>
                    <div className="dlab">Acceptance ({independent ? 'a-priori' : 'default'} threshold {pct(thr)})</div>
                    <div style={{ marginTop: 6 }}>
                      <span className={'pill ' + (passes ? 'inc' : 'exc')} style={{ fontSize: 13, padding: '4px 12px' }}>
                        {passes ? '✓ PASS' : '✕ NOT MET'}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                      one-sided 95% lower bound = <strong>{pct(m.recall_95_onesided_lower, 1)}</strong> vs threshold {pct(thr)}.
                      {acc.precision_warning ? ' Few validation positives — wide bound.' : ''}
                    </div>
                  </div>
                )}
              </div>

              {recall != null && (
                <>
                  <div className={'gate ' + (passes ? 'go' : 'nogo')} style={{ marginTop: 16 }}>
                    <strong>{passes ? 'GO' : 'RE-PILOT'}</strong> — recall-led Go/No-Go on the one-sided lower bound.
                    {' '}κ = {num(kap.kappa)} {Array.isArray(kap.ci) ? `(95% CI ${num(kap.ci[0])}–${num(kap.ci[1])})` : ''} is a
                    <em> secondary, prevalence-sensitive</em> agreement check, not the verdict.
                  </div>
                  {/* Reference-standard ceiling at the gate (F8) — concept-gold-standard-reference-caveat / RAISE 2 Appendix 1 */}
                  <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                    <strong>Ceiling:</strong> this recall can only be as good as the reference standard it is scored against —
                    the AI cannot score better than the blind-human decisions (or benchmark) it is compared to (RAISE&nbsp;2,
                    Appendix&nbsp;1). A <strong>GO</strong> means it cleared the bar <em>relative to that reference</em>, not that the
                    screening is proven correct in absolute terms; if the reference itself has errors, so does this number.
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                    <strong>Miss-band:</strong> the AI may have missed roughly <strong>{pct(recall != null ? 1 - recall : null)}</strong> of
                    relevant studies (95% CI {pct(ci[1] != null ? 1 - ci[1] : null)} – {pct(ci[0] != null ? 1 - ci[0] : null)}) —
                    a selection-bias limitation to disclose. {acc.rule_of_three_note ? '⚠ ' + acc.rule_of_three_note : ''}
                  </div>
                </>
              )}
            </div></div>

            {/* SECONDARY (small, muted) */}
            {recall != null && (
              <div className="card" style={{ marginBottom: 10 }}><div className="bd">
                <div className="dlab" style={{ marginBottom: 8 }}>Secondary measures</div>
                <div className="recon-cards">
                  <div className="rc"><div className="n" style={{ fontSize: 18 }}>{num(m.fbeta)}</div><div className="l">F-β (β={num(m.beta, 0)}, recall-weighted)</div></div>
                  <div className="rc"><div className="n" style={{ fontSize: 18, color: 'var(--exc)' }}>{m.missed_relevant_FN}</div><div className="l">Missed relevant (FN)</div></div>
                  <div className="rc"><div className="n" style={{ fontSize: 18 }}>{pct(m.specificity_secondary)}</div><div className="l">Specificity</div></div>
                  <div className="rc"><div className="n" style={{ fontSize: 18 }}>{pct(m.precision)}</div><div className="l">Precision</div></div>
                  <div className="rc"><div className="n" style={{ fontSize: 18 }}>{num(m.auc_secondary)}</div><div className="l">AUC-ROC (ranking, not accuracy)</div></div>
                  <div className="rc"><div className="n" style={{ fontSize: 18 }}>{m.wss_diagnostic?.wss != null ? pct(m.wss_diagnostic.wss) : '—'}</div><div className="l">WSS@95% (ranking diagnostic)</div></div>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>
                  Secondary by design. <strong>F1 = {num(m.f1_secondary)}</strong> and <strong>κ = {num(kap.kappa)}</strong> are
                  reported only for completeness — F1 is the wrong headline for screening and κ is prevalence-sensitive on this
                  imbalanced task (RAISE 2). AUC/WSS use uncalibrated LLM confidence vs single blind-human labels — ranking diagnostics, not a gold standard.
                </div>
              </div></div>
            )}

            {recall != null && rel.per_stratum && <StratifiedTable per={rel.per_stratum} />}

            {rel.awaiting_excluded > 0 && (
              <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
                <strong>{rel.awaiting_excluded}</strong> record(s) marked <em>awaiting</em> (couldn’t obtain / couldn’t read) are
                excluded from this metric — they are not include/exclude judgements (they go to “Studies awaiting classification”).
              </div>
            )}
            {rel?.note && <div className="muted" style={{ fontSize: 11 }}>{rel.note}</div>}
          </>
        )}
    </div></div>
  )
}

export default function Reliability() {
  const [mode, setMode] = useState('disk')        // 'disk' | 'example'
  const [rel, setRel] = useState(null)            // 5a title/abstract panel
  const [relFt, setRelFt] = useState(null)        // 5b full-text panel
  const [fat, setFat] = useState(null)
  const [stab, setStab] = useState(null)
  const [err, setErr] = useState('')
  const [thrMeta, setThrMeta] = useState({
    threshold_set_by: '', threshold_set_date: '',
    coi_declared: false, coi_detail: '',                 // evaluation-level COI (RAISE Part 1 rec 2.8)
    reference_is_published: false, reference_citation: '' // contamination control (published-review reference)
  })
  const [thrSaved, setThrSaved] = useState(false)
  const [probe, setProbe] = useState(null)               // saved/last memorization-probe result
  const [probing, setProbing] = useState(false)
  const reqId = useRef(0)

  const load = useCallback(() => {
    const id = ++reqId.current          // ignore stale responses when the mode changes mid-flight (race guard)
    const ex = mode === 'example'
    const q = ex ? '?example=1' : ''
    setRel(null); setRelFt(null); setFat(null); setStab(null); setErr('')
    // Both screening stages, guarded by the SAME reqId so a mode toggle mid-flight discards stale responses.
    // On a hard failure surface it in that stage's own panel (a null prop would hang the panel on "Loading…").
    api('/reliability' + q).then(d => { if (id === reqId.current) setRel(d) }).catch(e => { if (id === reqId.current) { setErr(String(e)); setRel({ ok: false, message: 'Could not load title/abstract reliability: ' + String(e) }) } })
    api('/reliability?stage=fulltext' + (ex ? '&example=1' : '')).then(d => { if (id === reqId.current) setRelFt(d) }).catch(e => { if (id === reqId.current) setRelFt({ ok: false, message: 'Could not load full-text reliability: ' + String(e) }) })
    api('/fatigue' + q).then(d => { if (id === reqId.current) setFat(d) }).catch(() => {})
    api('/stability' + q).then(d => { if (id === reqId.current) setStab(d) }).catch(() => {})
  }, [mode])
  useEffect(() => { load() }, [load])

  const truthy = v => v === true || ['1', 'true', 'yes', 'y', 'on'].includes(String(v || '').trim().toLowerCase())
  useEffect(() => {
    api('/config').then(d => {
      const c = d.config || {}
      setThrMeta({
        threshold_set_by: c.threshold_set_by || '', threshold_set_date: c.threshold_set_date || '',
        coi_declared: truthy(c.coi_declared), coi_detail: c.coi_detail || '',
        reference_is_published: truthy(c.reference_is_published), reference_citation: c.reference_citation || ''
      })
    }).catch(() => {})
    api('/reliability/memorization-probe').then(d => { if (d && d.present) setProbe(d) }).catch(() => {})
  }, [])

  const saveThrMeta = () => {
    // Re-fetch reliability after saving so the persisted `independent` flag + suppression reason + slide
    // warning (and the metrics note) refresh — otherwise the on-screen a-priori/default claim would lag.
    // Booleans are sent as 'yes'/'' so the backend's string-based config store round-trips them.
    const body = { ...thrMeta, coi_declared: thrMeta.coi_declared ? 'yes' : '',
                   reference_is_published: thrMeta.reference_is_published ? 'yes' : '' }
    api('/config', { method: 'POST', body }).then(() => { setThrSaved(true); setTimeout(() => setThrSaved(false), 2000); load() }).catch(() => {})
  }

  const runProbe = () => {
    setProbing(true)
    api('/reliability/memorization-probe', { method: 'POST', body: { reference_citation: thrMeta.reference_citation } })
      .then(d => { setProbe(d); load() })
      .catch(e => setProbe({ ok: false, message: 'Probe failed: ' + String(e) }))
      .finally(() => setProbing(false))
  }

  // The a-priori / independent claim is TRUE only if a real setter + date are ON RECORD (RAISE Part 2 §1
  // Box 2, p.9). Use the backend's PERSISTED, config-based flag — never the live/unsaved input — so the screen
  // can never assert independence from text the user typed but hasn't saved. (saveThrMeta re-fetches to refresh.)
  const independent = !!rel?.independent
  // Config-derived fallback so the honest REASON survives a fresh/blank review OR a transient fetch error, when
  // rel carries no flags: a recorded setter+date WITH a declared COI is a suppressed-independence state.
  const provRecorded = !!(thrMeta.threshold_set_by.trim() && thrMeta.threshold_set_date.trim())
  const coiFallback = (provRecorded && thrMeta.coi_declared)
    ? 'a conflict of interest was declared (RAISE Part 1 rec 2.8: a declared interest cannot be presented as independent)'
    : ''
  const suppressReason = rel?.independence_suppressed_reason || coiFallback   // WHY independence is withheld, if it is
  const slid = !!rel?.threshold_slide_warning                        // threshold changed after results existed
  const refPublished = !!(rel?.reference_is_published ?? thrMeta.reference_is_published)  // published-review reference (contamination risk)
  const probePresent = !!rel?.memorization_probe_present
  const f = fat?.fatigue
  const fci = f?.cumulative_time_credible_interval || f?.cumulative_time_95ci || [null, null]

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 980 }}>
      {/* DEMO + mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="demo-badge">DEMO — not a validated result</span>
        <span className="pill" title="Grades the AI second screener at both screening stages — title/abstract (5a) and full text (5b) — each in its own panel below.">Screening reliability · 5a + 5b</span>
        {(rel?.synthetic || relFt?.synthetic) && <span className="pill maybe">SYNTHETIC worked example</span>}
        <div className="seg" style={{ marginLeft: 'auto' }}>
          <button className={mode === 'disk' ? 'on' : ''} onClick={() => setMode('disk')}>Use my data</button>
          <button className={mode === 'example' ? 'on' : ''} onClick={() => setMode('example')}>Worked example</button>
        </div>
      </div>

      <div className="info" style={{ fontSize: 12.5 }}>
        We lead with <strong>recall</strong> — the share of genuinely relevant studies the AI correctly kept — because a
        missed study is the costly error. F1 and accuracy are <strong>not</strong> the headline (they mislead on this
        imbalanced task — RAISE). The acceptance test uses the <strong>one-sided 95% lower bound</strong> of recall vs a
        threshold. {independent
          ? <>That bar is recorded as set <strong>a priori, independently of the developer</strong>{thrMeta.threshold_set_by ? <> (by {thrMeta.threshold_set_by})</> : null}.</>
          : suppressReason
            ? <>The bar is <strong>not</strong> reported as independent: {suppressReason}.</>
            : <>Right now the bar is the tool’s <strong>default</strong> — independence is <strong>not yet established</strong>. Record who set it, and when, below to make it a-priori.</>}
        {' '}The same recall-first bar is applied at <strong>both</strong> screening stages below.
      </div>
      {err && <div className="warn">Couldn’t load reliability: {err}</div>}

      {/* Two stage panels, side by side conceptually (stacked on narrow screens). Never share a number. */}
      <StagePanel title="Title/abstract screening (5a)"
        subtitle="AI vs the human’s blind title/abstract decisions"
        rel={rel} independent={independent} onExample={() => setMode('example')} />

      <StagePanel title="Full-text screening (5b)"
        subtitle="AI vs the human’s full-text include/exclude decisions · ‘awaiting’ excluded"
        rel={relFt} independent={independent} onExample={() => setMode('example')} />

      {/* FATIGUE — abstract-stage instrumented human capture (order_index + timestamps); not per-stage */}
      <div className="card"><div className="bd">
        <div className="dlab" style={{ marginBottom: 8 }}>Screening fatigue — does human error rise with time-on-task? (title/abstract capture)</div>
        {!fat ? <div className="muted">Loading…</div>
          : !fat.available ? <div className="info" style={{ fontSize: 12.5 }}>{fat.message} {mode !== 'example' && <button className="btn" style={{ marginLeft: 8 }} onClick={() => setMode('example')}>Show a worked example</button>}</div>
            : (
              <div>
                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 220 }}>
                    <div style={{ fontSize: 13 }}>Time-on-task coefficient: <strong>{num(f.cumulative_time_coef)}</strong></div>
                    <IntervalBar lo={fci[0]} hi={fci[1]} point={f.cumulative_time_coef} />
                    <div className="muted" style={{ fontSize: 11 }}>interval crosses 0 ⇒ no clear fatigue effect; entirely &gt; 0 ⇒ error rises with time.</div>
                  </div>
                  <div style={{ minWidth: 160 }}>
                    {f.fatigue_detected == null
                      ? <span className="muted" style={{ fontSize: 12 }}>verdict unavailable (model did not fit)</span>
                      : <span className={'pill ' + (f.fatigue_detected ? 'exc' : 'maybe')} style={{ fontSize: 12 }}>
                          {f.fatigue_detected ? 'Fatigue detected' : 'No clear fatigue effect'}
                        </span>}
                    <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{f.n_screeners} screeners · {f.n_decisions} decisions</div>
                  </div>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>
                  {(f.method || '').split(' (')[0]}. {f.collinearity_warning || ''}
                  {f.warning ? ' ' + f.warning : ''} Time and list-position are intrinsically collinear, so “fatigue vs learning” is only weakly identified.
                </div>
              </div>
            )}
      </div></div>

      {/* STABILITY — test-retest across repeated identical AI runs (independent of the human arm) */}
      <div className="card"><div className="bd">
        <div className="dlab" style={{ marginBottom: 8 }}>Test-retest stability — does the AI give the same answer on repeated identical runs?</div>
        {!stab ? <div className="muted">Loading…</div>
          : !stab.available ? <div className="info" style={{ fontSize: 12.5 }}>{stab.message} {mode !== 'example' && <button className="btn" style={{ marginLeft: 8 }} onClick={() => setMode('example')}>Show a worked example</button>}</div>
          : (() => {
              const s = stab.stability || {}
              const flipCI = s.flip_rate_95ci || [null, null]
              const cls = s.flip_rate >= 0.05 ? 'exc' : 'maybe'
              const label = s.flip_rate === 0 ? 'No flips — but confirm caching was defeated'
                : s.flip_rate < 0.05 ? 'Minor instability' : 'Notable instability'
              return (
                <div>
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 160 }}>
                      <div className="dlab">Records that flipped</div>
                      <div className="hero-num" style={{ fontSize: 30 }}>{pct(s.flip_rate, 1)}</div>
                      <div className="muted" style={{ fontSize: 11.5 }}>{s.records_that_flipped}/{s.records} records changed decision across {s.runs} runs (95% CI {pct(flipCI[0], 1)}–{pct(flipCI[1], 1)})</div>
                    </div>
                    <div style={{ minWidth: 170 }}>
                      <div className="dlab">Mean pairwise agreement</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--navy)' }}>{pct(s.mean_pairwise_agreement, 1)}</div>
                      <div className="muted" style={{ fontSize: 11.5 }}>min {pct(s.min_pairwise_agreement, 1)} · κ {num(s.mean_pairwise_kappa)}</div>
                    </div>
                    <div style={{ minWidth: 150 }}>
                      <span className={'pill ' + cls} style={{ fontSize: 12 }}>{label}</span>
                    </div>
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>{s.note}</div>
                  {stab.files && <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>runs compared: {stab.files.join(' · ')}</div>}
                </div>
              )
            })()}
      </div></div>

      {/* Threshold provenance — who set the a-priori threshold and when (must be BEFORE seeing results) */}
      <div className="card"><div className="hd"><h2>Acceptance threshold — provenance</h2></div><div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.6 }}>
          The a-priori threshold (the recall cut-off the AI must reach) must be set <strong>before</strong> you
          see any results, by someone independent of the tool developer — otherwise it is no longer truly a-priori
          (grounded in RAISE Part 2, §1 Box 2, p.9 — the Cochrane RCT Classifier had its 99%-recall bar set
          independently of the developers). One bar applies to both screening panels above. Record who set it and when so a referee or reader can verify this.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label className="fld" style={{ marginBottom: 0 }}><h3>Set by (name / role)</h3>
            <input className="input" value={thrMeta.threshold_set_by}
              onChange={e => setThrMeta(m => ({ ...m, threshold_set_by: e.target.value }))}
              placeholder="e.g. review lead / methodologist, independent of the tool developer" />
          </label>
          <label className="fld" style={{ marginBottom: 0 }}><h3>Date set (before any results)</h3>
            <input className="input" type="date" value={thrMeta.threshold_set_date}
              onChange={e => setThrMeta(m => ({ ...m, threshold_set_date: e.target.value }))} />
          </label>
        </div>

        {/* Evaluation-level conflict of interest (RAISE Part 1 rec 2.8). Declaring an interest does NOT restore
            the "independent" label — so ticking this suppresses the a-priori/independent framing everywhere. */}
        <label className="fld" style={{ marginTop: 12, marginBottom: 0, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <input type="checkbox" style={{ marginTop: 3 }} checked={thrMeta.coi_declared}
            onChange={e => setThrMeta(m => ({ ...m, coi_declared: e.target.checked }))} />
          <span style={{ fontSize: 12.5, lineHeight: 1.5 }}>
            The person who set this bar / runs this evaluation has a <strong>financial or non-financial interest</strong> in
            the AI tool or its provider (including being the tool’s developer). <span className="muted">Declaring this is
            required (RAISE Part 1 rec 2.8) — and it means the evaluation cannot be reported as “independent”.</span>
          </span>
        </label>
        {thrMeta.coi_declared && (
          <label className="fld" style={{ marginTop: 8, marginBottom: 0 }}><h3>Describe the interest (for the disclosure)</h3>
            <input className="input" value={thrMeta.coi_detail}
              onChange={e => setThrMeta(m => ({ ...m, coi_detail: e.target.value }))}
              placeholder="e.g. I developed EvidenceEngine / I hold shares in the model provider" />
          </label>
        )}

        {slid && (
          <div className="warn" style={{ fontSize: 12, marginTop: 12 }}>
            ⚠ The acceptance threshold was <strong>changed after results were already computed</strong>. A bar moved
            after seeing results is no longer a-priori, so the evaluation is reported as <strong>not independent</strong>
            (concept-a-priori-threshold-independent-developer: never slide the bar). The change is logged in the run
            record; if this was an honest correction, state that in your write-up.
          </div>
        )}

        <div style={{ marginTop: 10 }}>
          <button className="btn primary" onClick={saveThrMeta}>Save provenance</button>
          {thrSaved && <span style={{ color: 'var(--inc)', fontWeight: 600, marginLeft: 10, fontSize: 12 }}>✓ saved</span>}
        </div>
        <div className={independent ? 'info' : 'warn'} style={{ fontSize: 12, marginTop: 12 }}>
          {independent
            ? <>Independence <strong>established</strong> — the acceptance bar is reported as a-priori and independent of the developer.</>
            : suppressReason
              ? <><strong>Not independent</strong> — {suppressReason}. The bar is applied to the one-sided lower bound, but the evaluation is not reported as independent.</>
              : <>Not yet independent — the bar is currently the tool’s <strong>default{rel?.threshold != null ? ' ' + pct(rel.threshold) : ''}</strong>. Until a setter and date are recorded here, the app reports it as a <strong>default</strong>, not an a-priori gate.
                  {(thrMeta.threshold_set_by.trim() && thrMeta.threshold_set_date.trim())
                    ? <> <strong>Click “Save provenance”</strong> to record what you’ve entered.</> : null}</>}
        </div>
      </div></div>

      {/* Contamination / memorization probe — playbook-reliability Step 2. Only relevant when validating against a
          PUBLISHED review the model may have memorised (e.g. an ASReview benchmark dataset). */}
      <div className="card"><div className="hd"><h2>Contamination check (validating against a published review?)</h2></div><div className="bd">
        <div className="muted" style={{ fontSize: 12, marginBottom: 12, lineHeight: 1.6 }}>
          If your reference standard is an <strong>already-published</strong> systematic review, the AI model may have
          <strong> memorised</strong> it — which would inflate recall and make the AI look better than it is. The honest
          fix is to validate on a <strong>fresh, in-progress</strong> review instead. If you must use a published one,
          run a memorization probe <strong>before</strong> scoring: it records what the model already recalls about that
          review, so a suspiciously high recall can be traced to memorisation (RAISE Part 2 §2 data contamination, pp.16-18).
        </div>
        <label className="fld" style={{ marginBottom: 0, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <input type="checkbox" style={{ marginTop: 3 }} checked={thrMeta.reference_is_published}
            onChange={e => setThrMeta(m => ({ ...m, reference_is_published: e.target.checked }))} />
          <span style={{ fontSize: 12.5, lineHeight: 1.5 }}>My reference standard is a <strong>published review</strong> (contamination risk).</span>
        </label>
        {thrMeta.reference_is_published && (
          <>
            <label className="fld" style={{ marginTop: 8, marginBottom: 0 }}><h3>Which published review (title / DOI)</h3>
              <input className="input" value={thrMeta.reference_citation}
                onChange={e => setThrMeta(m => ({ ...m, reference_citation: e.target.value }))}
                placeholder="e.g. Smith et al. (2020) … / doi:10.xxxx/xxxxx" />
            </label>
            <div style={{ marginTop: 10, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn primary" onClick={saveThrMeta}>Save</button>
              <button className="btn" onClick={runProbe} disabled={probing || !thrMeta.reference_citation.trim()}>
                {probing ? 'Probing the model…' : 'Run memorization probe (before scoring)'}
              </button>
            </div>
          </>
        )}
        {probePresent && <div className="warn" style={{ fontSize: 12, marginTop: 12 }}>
          ⚠ A published-review reference is in use and a memorization probe is on record — treat the recall as
          possibly <strong>contamination-inflated</strong> and disclose the probe (<code>reliability/memorization-probe.md</code>).</div>}
        {probe && (probe.answer || probe.content) && (
          <div className="card" style={{ marginTop: 12 }}><div className="bd">
            <div className="dlab" style={{ marginBottom: 6 }}>What the model recalled (saved before scoring)</div>
            {probe.message && <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>{probe.message}</div>}
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11.5, margin: 0, fontFamily: 'inherit' }}>{probe.answer || probe.content}</pre>
          </div></div>
        )}
        {probe && probe.ok === false && <div className="warn" style={{ fontSize: 12, marginTop: 10 }}>{probe.message}</div>}
      </div></div>
    </div>
  )
}
