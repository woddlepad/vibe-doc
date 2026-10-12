import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { slides } from './slides'
import { themes, type Theme } from './themes'

const W = 1920
const H = 1080

interface Route {
  variant: number | null
  slide: number
}

function parse(): Route {
  const m = location.hash.match(/^#\/(\d)(?:\/(\d))?/)
  if (!m) return { variant: null, slide: 0 }
  const v = Math.min(Math.max(Number(m[1]), 1), themes.length)
  const s = Math.min(Math.max(Number(m[2] ?? 1), 1), slides.length) - 1
  return { variant: v, slide: s }
}

function go(variant: number | null, slide = 0) {
  location.hash = variant ? `#/${variant}/${slide + 1}` : '#/'
}

function useRoute() {
  const [route, setRoute] = useState(parse)
  useEffect(() => {
    const on = () => setRoute(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

/* A fixed 1920x1080 canvas, scaled to fit its box. */
function Stage({ children, fit = 'window' }: { children: ReactNode; fit?: 'window' | 'parent' }) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      setScale(Math.min(r.width / W, r.height / H))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={box} className={`stage-box stage-${fit}`}>
      <div className="stage" style={{ width: W, height: H, transform: `translate(-50%, -50%) scale(${scale})` }}>
        {children}
      </div>
    </div>
  )
}

function ThemeRoot({ theme, children }: { theme: Theme; children: ReactNode }) {
  return (
    <div className={`deck layout-${theme.layout}`} style={theme.vars as CSSProperties}>
      {children}
    </div>
  )
}

function Deck({ variant, slide }: { variant: number; slide: number }) {
  const theme = themes[variant - 1]
  const Current = slides[slide]
  const [idle, setIdle] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(e.key)) go(variant, Math.min(slide + 1, slides.length - 1))
      else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(e.key)) go(variant, Math.max(slide - 1, 0))
      else if (e.key === 'Home') go(variant, 0)
      else if (e.key === 'End') go(variant, slides.length - 1)
      else if (/^[1-9]$/.test(e.key) && Number(e.key) <= themes.length) go(Number(e.key), slide)
      else if (e.key === 'Escape') go(null)
      else if (e.key === 'f') {
        if (document.fullscreenElement) document.exitFullscreen()
        else document.documentElement.requestFullscreen()
      } else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [variant, slide])

  useEffect(() => {
    let t = window.setTimeout(() => setIdle(true), 2200)
    const wake = () => {
      setIdle(false)
      window.clearTimeout(t)
      t = window.setTimeout(() => setIdle(true), 2200)
    }
    window.addEventListener('mousemove', wake)
    return () => {
      window.removeEventListener('mousemove', wake)
      window.clearTimeout(t)
    }
  }, [])

  return (
    <div className="viewer" style={{ background: theme.layout === 'nocturne' ? '#07090D' : '#1C1E21' }}>
      <Stage>
        <ThemeRoot theme={theme}>
          <Current key={`${variant}-${slide}`} theme={theme} />
        </ThemeRoot>
      </Stage>
      <nav className={`chrome ${idle ? 'idle' : ''}`} aria-label="Deck controls">
        <button onClick={() => go(null)}>All variants</button>
        <div className="chrome-variants">
          {themes.map((t) => (
            <button key={t.id} aria-current={t.id === variant} onClick={() => go(t.id, slide)}>
              {t.name}
            </button>
          ))}
        </div>
        <div className="chrome-steps">
          <button aria-label="Previous slide" disabled={slide === 0} onClick={() => go(variant, slide - 1)}>
            Back
          </button>
          <span>
            {slide + 1} of {slides.length}
          </span>
          <button aria-label="Next slide" disabled={slide === slides.length - 1} onClick={() => go(variant, slide + 1)}>
            Next
          </button>
        </div>
      </nav>
    </div>
  )
}

function Index() {
  const [Title] = slides
  return (
    <main className="index">
      <header className="index-head">
        <h1>rsi-doc pitch deck</h1>
        <p>Seven directions, same eleven slides. Open one, then use the arrow keys. Press 1 to 7 to switch direction, F for full screen.</p>
      </header>
      <div className="index-grid">
        {themes.map((t) => (
          <a key={t.id} className="index-card" href={`#/${t.id}/1`}>
            <div className="index-thumb">
              <Stage fit="parent">
                <ThemeRoot theme={t}>
                  <Title theme={t} />
                </ThemeRoot>
              </Stage>
            </div>
            <div className="index-name">
              <span>{t.name}</span>
            </div>
          </a>
        ))}
      </div>
    </main>
  )
}

export default function App() {
  const { variant, slide } = useRoute()
  return (
    <>
      {variant ? <Deck variant={variant} slide={slide} /> : <Index />}
    </>
  )
}
