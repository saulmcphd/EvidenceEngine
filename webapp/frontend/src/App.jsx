import { useState } from 'react'
import Setup from './screens/Setup.jsx'
import Protocol from './screens/Protocol.jsx'
import Search from './screens/Search.jsx'
import BlindScreening from './screens/BlindScreening.jsx'
import FullText from './screens/FullText.jsx'
import Reconcile from './screens/Reconcile.jsx'
import RoB from './screens/RoB.jsx'
import Extract from './screens/Extract.jsx'
import Synthesis from './screens/Synthesis.jsx'
import Reliability from './screens/Reliability.jsx'
import Report from './screens/Report.jsx'
import Evidence from './screens/Evidence.jsx'
import Help from './screens/Help.jsx'

const STEPS = [
  { key: 'setup', n: '1', label: 'Setup' },
  { key: 'protocol', n: '2', label: 'Protocol' },
  { key: 'search', n: '3–4', label: 'Search & records' },
  { key: 's5a', n: '5a', label: 'Abstract screening' },
  { key: 's5b', n: '5b', label: 'Full-text screening' },
  { key: 's5c', n: '5c', label: 'Reconciliation' },
  { key: 'rob', n: '6', label: 'Risk of bias' },
  { key: 'extract', n: '7', label: 'Data extraction' },
  { key: 'synthesis', n: '8', label: 'Synthesis' },
  { key: 'reliability', n: '✓', label: 'Reliability' },
  { key: 'report', n: '9', label: 'Report / Export' },
  { key: 'okf', n: '10', label: 'Evidence map' },
]

const TITLES = {
  setup: ['Setup', 'Define your review once · set your eligibility criteria · configure the AI · your data stays local'],
  protocol: ['Protocol & registration', 'Generate your protocol from your setup · PRISMA-P document + PROSPERO · honest blanks for anything not yet decided'],
  search: ['Search & records', 'Exports → de-duplicated master set · stable IDs · blind screener orders'],
  s5a: ['Blind screening — title & abstract', 'You decide before seeing the AI · recall-first'],
  s5b: ['Blind screening — full text', 'Definitive include/exclude · reason + verbatim quote'],
  s5c: ['Reconciliation & arbitration', 'Blind lifted · settle every human-vs-AI disagreement'],
  rob: ['Risk of bias', 'One profile per study · RoB 2 / ROBINS-I · AI second rater, you reconcile'],
  extract: ['Data extraction', 'AI second extractor · you reconcile every value · hallucination-checked'],
  synthesis: ['Synthesis', 'Bring the included studies together · evidence table + narrative synthesis · weigh quality, not counts'],
  reliability: ['Reliability', 'How good is the AI second screener? · recall-first · DEMO until a real run'],
  report: ['Report / Export', 'Paste-into-your-paper artefacts · every number gated on a real file · DRAFT when missing'],
  okf: ['Evidence map', 'The studies included in your review · and how they relate'],
  help: ['Help / Ask', 'Ask about the review process or this app · answered from the curated methodology library · your own AI'],
}

export default function App() {
  const [step, setStep] = useState('setup')   // first-time reviewers start at step 1, not mid-pipeline
  const meta = TITLES[step] || [STEPS.find(s => s.key === step)?.label || '', '']
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="dot"><span /></div>
          <div>
            <div className="name">EvidenceEngine</div>
            <div className="sub">systematic-review</div>
          </div>
        </div>
        <div className="rail-label">Steps</div>
        <nav className="nav">
          {STEPS.map(s => (
            <div key={s.key} className={'nav-item' + (s.key === step ? ' active' : '')} onClick={() => setStep(s.key)}>
              <span className="badge">{s.n}</span>
              <span>{s.label}</span>
            </div>
          ))}
        </nav>
        <div className="rail-label">Help</div>
        <nav className="nav">
          <div className={'nav-item' + ('help' === step ? ' active' : '')} onClick={() => setStep('help')}>
            <span className="badge">?</span>
            <span>Help / Ask</span>
          </div>
        </nav>
        <div className="rail-foot">Runs on your machine.<br />Your data &amp; API key stay local.</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <h1>{meta[0]}</h1>
          {meta[1] ? <span className="sub">{meta[1]}</span> : null}
        </header>
        <div className="content">
          {step === 'setup'
            ? <Setup />
            : step === 'protocol'
            ? <Protocol />
            : step === 'search'
            ? <Search />
            : step === 's5a'
            ? <BlindScreening />
            : step === 's5b'
            ? <FullText />
            : step === 's5c'
            ? <Reconcile />
            : step === 'rob'
            ? <RoB />
            : step === 'extract'
            ? <Extract />
            : step === 'synthesis'
            ? <Synthesis />
            : step === 'reliability'
            ? <Reliability />
            : step === 'report'
            ? <Report />
            : step === 'okf'
            ? <Evidence />
            : step === 'help'
            ? <Help />
            : <div className="placeholder">
                <strong>{STEPS.find(s => s.key === step)?.label}</strong><br />
                Coming next — same shape as 5a: you complete it (or upload it), the AI second-checks, you reconcile.
              </div>}
        </div>
      </main>
    </div>
  )
}
