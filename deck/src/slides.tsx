import type { ReactNode } from 'react'
import { Backdrop } from './Backdrop'
import { HoopPlate } from './Hoop'
import { DotPlot, OutcomeLegend, Pips, SplitBar, Waffle } from './charts'
import { baseline, gate, models, split, visits } from './data'
import type { Theme } from './themes'
import { Changes, Result, Visit } from './slides-v001'
import { Dataset, Record } from './slides-data'

interface Portrait {
  src: string
  side: 'left' | 'right'
  alt: string
}

// Which slides carry a portrait, for the Monograph people variants.
const portraits: Record<'some' | 'many', Partial<Record<string, Portrait>>> = {
  some: {
    problem: { src: '/people/patient.webp', side: 'left', alt: 'A patient smiling by a window' },
  },
  many: {
    title: { src: '/people/portrait-quiet.webp', side: 'right', alt: 'A calm portrait' },
    problem: { src: '/people/conversation.webp', side: 'left', alt: 'Two people talking across a table' },
    gate: { src: '/people/clinician.webp', side: 'right', alt: 'A clinician listening' },
  },
}

export function portraitFor(theme: Theme, kind: string) {
  return theme.people ? portraits[theme.people][kind] : undefined
}

export const TOTAL = 11

export function Slide({ theme, kind, n, children }: { theme: Theme; kind: string; n: number; children: ReactNode }) {
  const hero = kind === 'title'
  const portrait = portraitFor(theme, kind)
  return (
    <section className={`slide s-${kind} ${portrait ? `has-portrait portrait-on-${portrait.side}` : ''}`}>
      {portrait ? (
        <figure className={`portrait portrait-${portrait.side}`}>
          <img src={portrait.src} alt={portrait.alt} />
        </figure>
      ) : null}
      {hero && theme.titleArt === 'hoop' ? (
        <HoopPlate />
      ) : (
        !(hero && portrait) && <Backdrop className={`art ${hero ? 'art-hero' : 'art-ambient'}`} spec={hero ? theme.hero : theme.ambient} />
      )}
      <div className="content">
        {children}
        {!hero && <div className="folio">
            {n} / {TOTAL}
          </div>}
      </div>
    </section>
  )
}

function Title({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="title" n={1}>
      <div className="title-block">
        <h1>A doctor that learns from its misses</h1>
        <p className="lede">An AI diagnostician that rewrites its own playbook, and keeps a change only when it proves better.</p>
      </div>
      <div className="byline">rsi-doc, October 2026</div>
    </Slide>
  )
}

function Problem({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="problem" n={2}>
      <h2>Diagnosis is an interview, not a quiz.</h2>
      <div className="clinic">
        <div className="actor">
          <div className="actor-name">Patient</div>
          <div className="actor-note">Knows only their own story</div>
        </div>
        <svg className="link" width="120" height="44" aria-hidden>
          <path d="M4 12 H116 M106 4 L116 12 L106 20" />
          <path d="M116 32 H4 M14 24 L4 32 L14 40" />
        </svg>
        <div className="actor actor-main">
          <div className="actor-name">Doctor</div>
          <div className="actor-note">Asks, examines, orders tests</div>
          <div className="budget">
            <div className="budget-row">
              <Pips total={baseline.budgetQuestions} used={0} />
              <span>{baseline.budgetQuestions} questions</span>
            </div>
            <div className="budget-row">
              <Pips total={baseline.budgetTests} used={0} shape="square" />
              <span>{baseline.budgetTests} exams or tests</span>
            </div>
          </div>
        </div>
        <svg className="link" width="120" height="44" aria-hidden>
          <path d="M4 22 H116 M106 14 L116 22 L106 30" />
        </svg>
        <div className="actor">
          <div className="actor-name">Judge</div>
          <div className="actor-note">Checks one answer against the key</div>
        </div>
      </div>
      <p className="foot">215 board-exam cases from AgentClinic, each a hidden patient.</p>
    </Slide>
  )
}

function Baseline({ theme }: { theme: Theme }) {
  const pct = Math.round(baseline.accuracy * 1000) / 10
  return (
    <Slide theme={theme} kind="baseline" n={5}>
      <div className="split-2">
        <div className="col-text">
          <h2>Most misses are near misses.</h2>
          <div className="hero-stat">
            <span className="hero-num">{pct}%</span>
            <span className="hero-cap">
              of {baseline.n} unseen cases, baseline
              <br />
              95% interval {Math.round(baseline.ci95[0] * 100)} to {Math.round(baseline.ci95[1] * 100)}%
            </span>
          </div>
          <dl className="pairs">
            <div>
              <dt>Answer key</dt>
              <dd>Chronic lymphocytic leukemia</dd>
              <dt>Doctor said</dt>
              <dd>CLL / small lymphocytic lymphoma</dd>
            </div>
            <div>
              <dt>Answer key</dt>
              <dd>Takotsubo cardiomyopathy</dd>
              <dt>Doctor said</dt>
              <dd>Acute coronary syndrome</dd>
            </div>
          </dl>
        </div>
        <div className="col-chart">
          <Waffle visits={visits} />
          <OutcomeLegend visits={visits} />
        </div>
      </div>
    </Slide>
  )
}

function Behaviour({ theme }: { theme: Theme }) {
  return (
    <Slide theme={theme} kind="behaviour" n={6}>
      <h2>More testing didn’t rescue the misses.</h2>
      <div className="multiples">
        <DotPlot visits={visits} field="questions" max={baseline.budgetQuestions} title="Questions asked per visit" />
        <DotPlot visits={visits} field="tests" max={baseline.budgetTests} title="Exams and tests ordered per visit" />
      </div>
      <p className="foot">
        {baseline.secondsPerVisit} seconds and about one cent per visit. The gap is reasoning, not information.
      </p>
    </Slide>
  )
}

function Angle({ theme }: { theme: Theme }) {
  const R = 250
  const cx = 540
  const cy = 430
  const nodes = [
    { a: -90, step: 'Run', note: 'Doctor works through training cases', who: models.doctor },
    { a: 0, step: 'Study', note: 'Optimizer reads every failed transcript', who: models.optimizer },
    { a: 90, step: 'Rewrite', note: 'Edits the prompt, lessons, skills and budgets', who: models.optimizer },
    { a: 180, step: 'Prove', note: 'Scored on 40 cases it has never seen', who: `judged by ${models.judge}` },
  ]
  const pt = (deg: number, r = R) => [cx + r * Math.cos((deg * Math.PI) / 180), cy + r * Math.sin((deg * Math.PI) / 180)]
  const arc = (from: number, to: number) => {
    const [x1, y1] = pt(from + 14)
    const [x2, y2] = pt(to - 14)
    return `M${x1} ${y1} A${R} ${R} 0 0 1 ${x2} ${y2}`
  }
  return (
    <Slide theme={theme} kind="angle" n={7}>
      <div className="split-2 angle-grid">
        <div className="col-text">
          <h2>Our angle: improve the playbook, not the model.</h2>
          <p className="lede">The doctor stays {models.doctor}. Only its harness changes, so every gain is a better way of working.</p>
        </div>
        <div className="loop" style={{ width: 1080, height: 860 }}>
          <svg width={1080} height={860} aria-hidden>
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" className="arrowhead" />
              </marker>
            </defs>
            {nodes.map((n, i) => (
              <path key={n.step} d={arc(n.a, nodes[(i + 1) % 4].a + (i === 3 ? 360 : 0))} className="ring" markerEnd="url(#arrow)" />
            ))}
            {nodes.map((n) => {
              const [x, y] = pt(n.a)
              return <circle key={n.step} cx={x} cy={y} r={9} className="node" />
            })}
          </svg>
          {nodes.map((n, i) => {
            const [x, y] = pt(n.a, R + 40)
            return (
              <div key={n.step} className={`loop-label at-${n.a}`} style={{ left: x, top: y }}>
                <div className="loop-step">
                  <span className="loop-i">{i + 1}</span>
                  {n.step}
                </div>
                <div className="loop-note">{n.note}</div>
                <div className="loop-who">{n.who}</div>
              </div>
            )
          })}
          <div className="harness" style={{ left: cx, top: cy }}>
            <div className="harness-files">
              <span>system.md</span>
              <span>lessons.md</span>
              <span>skills/</span>
              <span>config.json</span>
            </div>
            <div className="harness-cap">The harness</div>
          </div>
        </div>
      </div>
    </Slide>
  )
}

function Gate({ theme }: { theme: Theme }) {
  const narrow = Boolean(portraitFor(theme, 'gate'))
  return (
    <Slide theme={theme} kind="gate" n={11}>
      <h2>A change is kept only when it wins on cases it never saw.</h2>
      <SplitBar
        width={narrow ? 1040 : 1560}
        parts={[
          { n: split.train, label: 'train', note: 'The optimizer learns from these', cls: 'seg-train' },
          { n: split.dev, label: 'dev', note: 'Decides promotion', cls: 'seg-dev' },
          { n: split.test, label: 'test', note: 'Opened once, at the end', cls: 'seg-test' },
        ]}
      />
      <div className="rules">
        <div>
          <div className="rule-k">Locked model</div>
          <div className="rule-v">{models.doctor} in every version</div>
        </div>
        <div>
          <div className="rule-k">Frozen clinic</div>
          <div className="rule-v">Patient, examiner and judge never change</div>
        </div>
        <div>
          <div className="rule-k">
            Leaks {baseline.leaksBefore} → {baseline.leaksAfter}
          </div>
          <div className="rule-v">Answers said aloud are scored wrong</div>
        </div>
        <div>
          <div className="rule-k">The bar</div>
          <div className="rule-v">
            {Math.round(gate.minConfidence * 100)}% confidence it beats the parent, and at least {gate.minGain} more case
          </div>
        </div>
      </div>
    </Slide>
  )
}

export const slides = [Title, Problem, Dataset, Record, Baseline, Behaviour, Angle, Changes, Visit, Result, Gate]
