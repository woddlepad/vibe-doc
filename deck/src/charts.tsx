import { useId, useState, type ReactNode } from 'react'
import type { Outcome, Visit } from './data'

interface Tip {
  x: number
  y: number
  body: ReactNode
}

function Tooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null
  return (
    <div className="tip" style={{ left: tip.x, top: tip.y }}>
      {tip.body}
    </div>
  )
}

const outcomeLabel: Record<Outcome, string> = {
  correct: 'Correct',
  hedged: 'Right idea, hedged answer',
  wrong: 'Wrong diagnosis',
}

function VisitTip({ v }: { v: Visit }) {
  return (
    <>
      <div className="tip-head">{outcomeLabel[v.outcome]}</div>
      <div className="tip-row">
        <span>Answer key</span>
        {v.gold}
      </div>
      <div className="tip-row">
        <span>Doctor said</span>
        {v.said}
      </div>
      <div className="tip-row">
        <span>Asked</span>
        {v.questions} questions, {v.tests} tests
      </div>
    </>
  )
}

function Hatch({ id }: { id: string }) {
  return (
    <defs>
      <pattern id={id} width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="10" height="10" className="m-hedged-bg" />
        <line x1="0" y1="0" x2="0" y2="10" className="m-hedged-line" strokeWidth="4" />
      </pattern>
    </defs>
  )
}

const fillFor = (o: Outcome, hatch: string) => (o === 'hedged' ? `url(#${hatch})` : undefined)

const order: Outcome[] = ['correct', 'hedged', 'wrong']

/* 40 visits, one square each. */
export function Waffle({ visits, cols = 8, cell = 76, gap = 12 }: { visits: Visit[]; cols?: number; cell?: number; gap?: number }) {
  const [tip, setTip] = useState<Tip | null>(null)
  const hatch = 'h' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const sorted = [...visits].sort((a, b) => order.indexOf(a.outcome) - order.indexOf(b.outcome))
  const rows = Math.ceil(sorted.length / cols)
  const w = cols * cell + (cols - 1) * gap
  const h = rows * cell + (rows - 1) * gap
  return (
    <div className="chart" style={{ width: w }} onMouseLeave={() => setTip(null)}>
      <svg width={w} height={h} role="img" aria-label="Baseline outcome for each of 40 dev cases">
        <Hatch id={hatch} />
        {sorted.map((v, i) => {
          const x = (i % cols) * (cell + gap)
          const y = Math.floor(i / cols) * (cell + gap)
          return (
            <rect
              key={v.id}
              x={x}
              y={y}
              width={cell}
              height={cell}
              rx={4}
              className={`m-${v.outcome} hit`}
              fill={fillFor(v.outcome, hatch)}
              onMouseEnter={() => setTip({ x: x + cell / 2, y: y - 12, body: <VisitTip v={v} /> })}
            />
          )
        })}
      </svg>
      <Tooltip tip={tip} />
    </div>
  )
}

export function OutcomeLegend({ visits }: { visits: Visit[] }) {
  const hatch = 'h' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const count = (o: Outcome) => visits.filter((v) => v.outcome === o).length
  return (
    <ul className="legend">
      {order.map((o) => (
        <li key={o}>
          <svg width="22" height="22" aria-hidden>
            <Hatch id={hatch} />
            <rect width="22" height="22" rx="3" className={`m-${o}`} fill={fillFor(o, hatch)} />
          </svg>
          <span className="legend-n">{count(o)}</span>
          <span className="legend-l">{outcomeLabel[o]}</span>
        </li>
      ))}
    </ul>
  )
}

/* Dot plot: one dot per visit, stacked by value, correct vs missed rows. */
export function DotPlot({
  visits,
  field,
  max,
  title,
  width = 720,
}: {
  visits: Visit[]
  field: 'questions' | 'tests'
  max: number
  title: string
  width?: number
}) {
  const [tip, setTip] = useState<Tip | null>(null)
  const r = 9
  const step = 2 * r + 3
  const padL = 140
  const plotW = width - padL - 30
  const x = (v: number) => padL + (v / max) * plotW
  const groups = [
    { key: 'hit', label: 'Correct', items: visits.filter((v) => v.outcome === 'correct'), cls: 'm-correct' },
    { key: 'miss', label: 'Missed', items: visits.filter((v) => v.outcome !== 'correct'), cls: 'm-wrong' },
  ]
  const tallest = (a: Visit[]) => Math.max(...Object.values(a.reduce<Record<number, number>>((m, v) => ((m[v[field]] = (m[v[field]] ?? 0) + 1), m), {})))
  const mean = (a: Visit[]) => a.reduce((s, v) => s + v[field], 0) / a.length
  let top = r + 4
  const rows = groups.map((g) => {
    const base = top + (tallest(g.items) - 1) * step
    const axis = base + r + 8
    top = axis + 84
    return { ...g, base, axis, m: mean(g.items) }
  })
  const h = top - 30
  return (
    <div className="chart" style={{ width }} onMouseLeave={() => setTip(null)}>
      <div className="chart-title">{title}</div>
      <svg width={width} height={h} role="img" aria-label={title}>
        {rows.map((g) => {
          const stacks: Record<number, number> = {}
          return (
            <g key={g.key}>
              <text x={0} y={g.base + 7} className="row-label">
                {g.label}
              </text>
              <line x1={padL} x2={x(max)} y1={g.axis} y2={g.axis} className="axis" />
              {Array.from({ length: max + 1 }, (_, i) => (
                <line key={i} x1={x(i)} x2={x(i)} y1={g.axis} y2={g.axis + 6} className="axis" />
              ))}
              {g.items.map((v) => {
                const n = (stacks[v[field]] = (stacks[v[field]] ?? 0) + 1) - 1
                const cx = x(v[field])
                const cy = g.base - n * step
                return (
                  <circle
                    key={v.id}
                    cx={cx}
                    cy={cy}
                    r={r}
                    className={`${g.cls} dot hit`}
                    onMouseEnter={() => setTip({ x: cx, y: cy - r - 10, body: <VisitTip v={v} /> })}
                  />
                )
              })}
              <path d={`M${x(g.m)} ${g.axis + 12} l7 11 h-14 z`} className="mean-mark" />
              <text x={x(g.m) + 14} y={g.axis + 24} className="mean-label">
                avg {g.m.toFixed(1)}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="chart-scale" style={{ marginLeft: padL, width: plotW }}>
        <span>0</span>
        <span>{max} allowed</span>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}

/* Budget pips: how much of the allowance a visit uses on average. */
export function Pips({ total, used, shape = 'circle', size = 22, gap = 10 }: { total: number; used: number; shape?: 'circle' | 'square'; size?: number; gap?: number }) {
  const w = total * size + (total - 1) * gap
  return (
    <svg width={w} height={size} aria-label={`${used} of ${total}`}>
      <defs>
        <clipPath id={`pip-${total}-${used}`}>
          <rect x={0} y={0} width={Math.floor(used) * (size + gap) + (used % 1) * size} height={size} />
        </clipPath>
      </defs>
      {Array.from({ length: total }, (_, i) =>
        shape === 'circle' ? (
          <circle key={i} cx={i * (size + gap) + size / 2} cy={size / 2} r={size / 2 - 1.5} className="pip" />
        ) : (
          <rect key={i} x={i * (size + gap) + 1.5} y={1.5} width={size - 3} height={size - 3} rx={3} className="pip" />
        ),
      )}
      <g clipPath={`url(#pip-${total}-${used})`}>
        {Array.from({ length: total }, (_, i) =>
          shape === 'circle' ? (
            <circle key={i} cx={i * (size + gap) + size / 2} cy={size / 2} r={size / 2 - 1.5} className="pip-on" />
          ) : (
            <rect key={i} x={i * (size + gap) + 1.5} y={1.5} width={size - 3} height={size - 3} rx={3} className="pip-on" />
          ),
        )}
      </g>
    </svg>
  )
}

/* The 215 cases, split three ways. */
export function SplitBar({ parts, width = 1560 }: { parts: { n: number; label: string; note: string; cls: string }[]; width?: number }) {
  const total = parts.reduce((s, p) => s + p.n, 0)
  const gap = 6
  const usable = width - gap * (parts.length - 1)
  let x = 0
  return (
    <div className="split" style={{ width }}>
      <svg width={width} height={64} role="img" aria-label="Case split">
        {parts.map((p) => {
          const w = (p.n / total) * usable
          const el = <rect key={p.label} x={x} y={0} width={w} height={64} rx={4} className={p.cls} />
          x += w + gap
          return el
        })}
      </svg>
      <div className="split-labels">
        {parts.map((p) => (
          <div key={p.label} style={{ width: (p.n / total) * usable, marginRight: gap }}>
            <div className="split-n">
              {p.n} <span>{p.label}</span>
            </div>
            <div className="split-note">{p.note}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
