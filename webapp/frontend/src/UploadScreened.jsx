import { useRef, useState } from 'react'
import RunAI from './RunAI.jsx'

// Entry point B — "I already screened this elsewhere." The alternative to screening in the app, at BOTH
// screening stages (the two-entry-points design; playbook-title-abstract-screening / playbook-full-text-screening
// step 7): upload a screened RIS/Rayyan/CSV → screening_import.py compiles the decisions (abstract →
// human_decisions.csv; fulltext → fulltext_human_decisions.csv), so the user skips in-app screening and goes
// straight to the AI comparison + reconciliation. For full text the card also bulk-stages the PDFs the AI
// second screener reads — without them /api/fulltext/run has nothing to screen. Collapsed by default so it
// doesn't distract from blind screening.
export default function UploadScreened({ stage = 'abstract' }) {
  const [open, setOpen] = useState(false)
  const [screened, setScreened] = useState(null)
  const [pdfRes, setPdfRes] = useState(null)
  const ref = useRef(null)
  const pdfRef = useRef(null)
  const isFull = stage === 'fulltext'
  const run = async () => {
    const f = ref.current?.files?.[0]
    if (!f) return
    setScreened({ busy: true })
    const fd = new FormData(); fd.append('file', f)
    try {
      const res = await fetch('/api/upload-screened?stage=' + stage, { method: 'POST', body: fd })
      setScreened(await res.json())
    } catch (e) { setScreened({ ok: false, message: String(e) }) }
  }
  const stagePdfs = async () => {
    const fs = pdfRef.current?.files
    if (!fs || !fs.length) return
    setPdfRes({ busy: true })
    const fd = new FormData()
    for (const f of fs) fd.append('files', f)
    try {
      const res = await fetch('/api/fulltext/upload-pdfs', { method: 'POST', body: fd })
      setPdfRes(await res.json())
    } catch (e) { setPdfRes({ ok: false, message: String(e) }) }
  }
  const matched = screened?.matched ?? screened?.decisions_recovered ?? 0
  return (
    <div className="card" style={{ marginBottom: 14 }}><div className="bd">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }} onClick={() => setOpen(o => !o)}>
        <strong style={{ fontSize: 13 }}>Already screened {isFull ? 'your full texts ' : ''}elsewhere? <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>upload your decisions instead of screening here</span></strong>
        <span className="muted" style={{ fontSize: 12 }}>{open ? '▾' : '▸'}</span>
      </div>
      {open && (
        <div style={{ marginTop: 10 }}>
          <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
            {isFull ? (
              <>If you made your full-text include/exclude decisions in Rayyan, Covidence or a spreadsheet, upload
              the export (<strong>RIS, Rayyan CSV, or a CSV</strong> with a decision column — Rayyan exclusion-reason
              labels are picked up, and CSV columns named <span className="mono">reason</span> and{' '}
              <span className="mono">supporting_quote</span> are kept too). EvidenceEngine matches each row back to
              your master records and treats the decisions as your full-text screening; if two reviewers voted in
              your tool, every vote is kept. Excludes missing a reason/quote are kept and flagged — you complete
              them at Reconciliation, where every final full-text exclude needs one failed criterion plus a verbatim
              quote. Re-uploading merges (the new file wins per record). Build the master records on{' '}
              <strong>Search &amp; records</strong> first.</>
            ) : (
              <>If you finished title/abstract screening in Mendeley/Zotero/Rayyan, upload the <strong>screened RIS</strong>
              {' '}(or Rayyan CSV). EvidenceEngine recovers each record’s ID and compiles your decisions,
              so you can skip screening here and jump to the AI comparison + reconciliation. Build the master records on
              {' '}<strong>Search &amp; records</strong> first.</>
            )}
          </div>
          <input ref={ref} type="file" accept=".ris,.csv,.txt" style={{ fontSize: 12 }} />
          <button className="btn primary" style={{ marginLeft: 10 }} disabled={screened?.busy} onClick={run}>
            {screened?.busy ? 'Importing…' : 'Import screened decisions'}
          </button>
          {screened && !screened.busy && (
            !screened.ok
              ? <div className="warn" style={{ marginTop: 10 }}>{screened.message || 'Import failed.'}</div>
              : <>
                  {screened.warning && <div className="warn" style={{ marginTop: 10 }}>{screened.warning}</div>}
                  {matched > 0 && (
                    <div className="info" style={{ marginTop: 10, fontSize: 12 }}>
                      ✓ Imported a {screened.kind?.toUpperCase()} export — {matched} decision{matched === 1 ? '' : 's'} matched your master records
                      {screened.human_decisions_rows ? ` (${screened.human_decisions_rows} rows in the file)` : ''}.
                      {isFull && screened.flagged > 0 && <> {screened.flagged} exclude{screened.flagged === 1 ? ' is' : 's are'} missing the reason and/or verbatim quote a final exclude needs — kept and flagged; you’ll complete them at Reconciliation.</>}
                      {' '}Now {isFull ? 'stage the PDFs below, ' : ''}run the AI second screener, then go to <strong>Reconciliation</strong>.
                    </div>
                  )}
                  {matched > 0 && <RunAI stage={stage} compact />}
                </>
          )}
          {isFull && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
              <strong style={{ fontSize: 12.5 }}>Stage the PDFs so the AI can read the papers</strong>
              <div className="muted" style={{ fontSize: 12, margin: '6px 0 8px' }}>
                The AI second screener reads the full papers from this computer. Select all your PDFs at once —
                each file is matched to a record by the record ID in its filename (e.g.{' '}
                <span className="mono">REC_0007.pdf</span>), or by the DOI / title / author-year in the filename.
                A record with no PDF gets no AI second opinion — it still appears at Reconciliation, marked
                “no AI arm”, so your decision on it is never lost.
              </div>
              <input ref={pdfRef} type="file" accept="application/pdf" multiple style={{ fontSize: 12 }} />
              <button className="btn" style={{ marginLeft: 10 }} disabled={pdfRes?.busy} onClick={stagePdfs}>
                {pdfRes?.busy ? 'Staging…' : 'Stage PDFs'}
              </button>
              {pdfRes && !pdfRes.busy && (
                pdfRes.ok
                  ? <div className="info" style={{ marginTop: 8, fontSize: 12 }}>
                      ✓ Staged {pdfRes.saved} PDF{pdfRes.saved === 1 ? '' : 's'}
                      {pdfRes.match_checked
                        ? <> — {pdfRes.matched_records} of your records now have a full text on file.</>
                        : <> ({pdfRes.staged_total} PDFs staged in total — too many records to verify the name-matching instantly; unmatched files will surface as “no AI arm” at Reconciliation).</>}
                      {(pdfRes.unmatched_files || []).length > 0 && <> ⚠ {pdfRes.unmatched_files.length} file{pdfRes.unmatched_files.length === 1 ? '' : 's'} matched no record ({pdfRes.unmatched_files.slice(0, 5).join(', ')}{pdfRes.unmatched_files.length > 5 ? ', …' : ''}) — rename to the record ID (REC_NNNN.pdf) and re-stage.</>}
                      {(pdfRes.oversized || []).length > 0 && <> ⚠ {pdfRes.oversized.length} file{pdfRes.oversized.length === 1 ? '' : 's'} over 200 MB skipped ({pdfRes.oversized.slice(0, 3).join(', ')}).</>}
                      {pdfRes.skipped > 0 && <> ({pdfRes.skipped} non-PDF file{pdfRes.skipped === 1 ? '' : 's'} skipped.)</>}
                    </div>
                  : <div className="warn" style={{ marginTop: 8 }}>{pdfRes.message || 'Staging failed.'}</div>
              )}
            </div>
          )}
        </div>
      )}
    </div></div>
  )
}
