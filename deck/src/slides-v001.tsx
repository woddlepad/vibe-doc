import { useState } from 'react'
import { addedCheck, baseline, candidates, flips, harnessChanges, improved, models } from './data'
import { Slide } from './slides'
import type { Theme } from './themes'
import visit from './visit-mqx-104.json'

const pct = (x: number) => `${Math.round(x * 1000) / 10}%`

/* ---------- 6: what the optimizer changed ---------- */

export function Changes({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="changes" n={8}>
      <h2>It rewrote two text files. Nothing else.</h2>
      <div className="changes">
        <ul className="inventory">
          {harnessChanges.map((c) => (
            <li key={c.file} className={`inv-${c.status}`}>
              <svg width="18" height="18" aria-hidden>
                <circle cx="9" cy="9" r="7" className="inv-mark" />
              </svg>
              <span className="inv-file">{c.file}</span>
              <span className="inv-what">{c.what}</span>
              <span className="inv-status">{c.status}</span>
            </li>
          ))}
        </ul>
        <figure className="excerpt">
          <figcaption>Added to system.md</figcaption>
          <div className="excerpt-title">Before you submit (mandatory check)</div>
          <ol>
            {addedCheck.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ol>
        </figure>
      </div>
      <p className="foot">
        Written by {models.optimizer} from one missed training case. The exam found hearing loss, the patient said his hearing was fine,
        and the doctor believed the patient.
      </p>
    </Slide>
  )
}

/* ---------- 7: one real consultation, before and after ---------- */

interface Step {
  who: string
  text: string
  result?: string
  key?: boolean
}

// The moments that matter, trimmed from the real transcript (ellipses mark cuts).
const abridged: Record<'before' | 'after', Step[]> = {
  before: [
    { who: 'doctor', text: 'Can you tell me about your cough: how long have you had it…?' },
    { who: 'patient', text: 'It’s been about 11 years now, on and off. I bring up a lot of thick sputum, yellow-green in color.' },
    { who: 'exam', text: 'Chest auscultation', result: 'Crackles and wheezing over the right middle lobe.' },
    { who: 'test', text: 'High-resolution CT of the chest', result: 'Normal / unremarkable.' },
    { who: 'gap', text: '5 more questions, 6 more tests' },
    { who: 'dx', text: 'Chronic bacterial bronchitis, without radiographic bronchiectasis' },
  ],
  after: [
    { who: 'doctor', text: 'Can you tell me about your cough? How long have you had it…?' },
    { who: 'patient', text: 'It’s been about 11 years, on and off. I bring up a lot of thick, foamy, yellow-green phlegm.' },
    { who: 'exam', text: 'Chest auscultation', result: 'Crackles and wheezing over the right middle lobe.' },
    { who: 'test', text: 'High-resolution CT of the chest', result: 'Normal / unremarkable.' },
    { who: 'test', text: 'Chest X-ray', result: 'Irregular opacities in the right middle lobe and diffuse airway thickening.', key: true },
    { who: 'dx', text: 'Bronchiectasis, localized to the right middle lobe' },
  ],
}

function Bubble({ step, correct }: { step: Step; correct: boolean }) {
  if (step.who === 'doctor' || step.who === 'patient') {
    return (
      <div className={`bubble bubble-${step.who}`}>
        <span className="bubble-who">{step.who === 'doctor' ? 'Doctor' : 'Patient'}</span>
        {step.text}
      </div>
    )
  }
  if (step.who === 'exam' || step.who === 'test') {
    return (
      <div className={`record ${step.key ? 'record-key' : ''}`}>
        <span className="record-kind">{step.who === 'exam' ? 'Exam' : 'Test'}</span>
        <span className="record-req">{step.text}</span>
        <span className="record-result">{step.result}</span>
      </div>
    )
  }
  if (step.who === 'gap') return <div className="gap">{step.text}</div>
  return (
    <div className={`dx ${correct ? 'dx-right' : 'dx-wrong'}`}>
      <span className="dx-head">
        <svg width="20" height="20" aria-hidden>
          {correct ? <path d="M4 10.5 L8.5 15 L16 5.5" /> : <path d="M5 5 L15 15 M15 5 L5 15" />}
        </svg>
        {correct ? 'Correct' : 'Missed'}
      </span>
      {step.text}
    </div>
  )
}

function Thread({ side }: { side: 'before' | 'after' }) {
  const v = visit[side]
  const [full, setFull] = useState(false)
  const steps: Step[] = full ? v.steps : abridged[side]
  return (
    <div className="thread">
      <div className="thread-head">
        <div>
          <div className="thread-title">{side === 'before' ? 'Before' : 'After'}</div>
          <div className="thread-meta">
            {v.version}, {v.questions} questions and {v.tests} tests
          </div>
        </div>
        <button className="thread-toggle" onClick={() => setFull(!full)} aria-pressed={full}>
          {full ? 'Show highlights' : 'Show full visit'}
        </button>
      </div>
      <div className={`thread-body ${full ? 'thread-full' : ''}`}>
        {steps.map((s, i) => (
          <Bubble key={i} step={s} correct={v.correct} />
        ))}
      </div>
    </div>
  )
}

export function Visit({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="visit" n={9}>
      <div className="visit-head">
        <h2>Same patient, before and after.</h2>
        <p className="visit-key">Answer key: {visit.gold}. A held-out case the optimizer never saw.</p>
      </div>
      <div className="threads">
        <Thread side="before" />
        <Thread side="after" />
      </div>
    </Slide>
  )
}

/* ---------- 8: the result ---------- */

export function Result({ theme }: { theme: Theme }) {
  const n = baseline.n
  const lo = 28
  const hi = 36
  const x = (c: number) => ((c - lo) / (hi - lo)) * 100
  return (
    <Slide theme={theme} kind="result" n={10}>
      <h2>Four ideas, one kept.</h2>
      <div className="result">
        <div className="result-left">
          <div className="result-big">
            <span className="result-from">{pct(baseline.accuracy)}</span>
            <svg width="72" height="28" aria-hidden className="result-arrow">
              <path d="M2 14 H66 M54 4 L68 14 L54 24" />
            </svg>
            <span className="result-to">{pct(improved.accuracy)}</span>
          </div>
          <p className="result-cap">
            on {n} unseen cases. {Math.round(improved.confidence * 100)}% bootstrap confidence the new version is better.
          </p>
          <div className="cands">
            {candidates.map((c) => (
              <div key={c.name} className={`cand cand-${c.outcome.replace(' ', '-')}`}>
                <div className="cand-idea">{c.idea}</div>
                <div className="cand-track">
                  <div className="cand-base" style={{ left: `${x(baseline.correct)}%` }} />
                  {c.correct !== null && <div className="cand-dot" style={{ left: `${x(c.correct)}%` }} />}
                </div>
                <div className="cand-out">
                  {c.correct !== null && <span className="cand-score">{c.correct}/40</span>}
                  {c.outcome}
                  {c.screen && <span className="cand-note">{c.screen}</span>}
                </div>
              </div>
            ))}
            <div className="cand-scale">
              <span>{lo}</span>
              <span className="cand-scale-base" style={{ left: `${x(baseline.correct)}%` }}>
                baseline
              </span>
              <span>{hi} of 40 correct</span>
            </div>
          </div>
        </div>
        <div className="result-right">
          <div className="flip-group">
            <div className="flip-title">Fixed {flips.fixed.length}</div>
            {flips.fixed.map((f, i) => (
              <div key={i} className="flip">
                <span className="flip-gold">{f.gold}</span>
                <span className="flip-change">
                  <s>{f.before}</s> {f.after}
                </span>
              </div>
            ))}
          </div>
          <div className="flip-group">
            <div className="flip-title">Broke {flips.broke.length}</div>
            {flips.broke.map((f, i) => (
              <div key={i} className="flip">
                <span className="flip-gold">{f.gold}</span>
                <span className="flip-change">
                  <s>{f.before}</s> {f.after}
                </span>
              </div>
            ))}
          </div>
          <dl className="costs">
            <div>
              <dt>Questions per visit</dt>
              <dd>
                {baseline.meanQuestions.toFixed(1)} → {improved.meanQuestions.toFixed(1)}
              </dd>
            </div>
            <div>
              <dt>Seconds per visit</dt>
              <dd>
                {baseline.secondsPerVisit} → {improved.secondsPerVisit}
              </dd>
            </div>
            <div>
              <dt>Cost of 40 visits</dt>
              <dd>
                ${improved.baselineDollarsPerDevRun.toFixed(2)} → ${improved.dollarsPerDevRun.toFixed(2)}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </Slide>
  )
}
