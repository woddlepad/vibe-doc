export type ShaderSpec =
  | {
      kind: 'mesh'
      colors: string[]
      positions: number
      waveX: number
      waveXShift: number
      waveY: number
      waveYShift: number
      mixing: number
      grainMixer: number
      grainOverlay: number
      rotation?: number
      scale?: number
    }
  | {
      kind: 'dither'
      colorBack: string
      colorFront: string
      shape: 'simplex' | 'warp' | 'dots' | 'wave' | 'ripple' | 'swirl' | 'sphere'
      type: 'random' | '2x2' | '4x4' | '8x8'
      size: number
      scale?: number
      frame?: number
      offsetX?: number
      offsetY?: number
    }
  | {
      kind: 'grain'
      colorBack: string
      colors: string[]
      shape: 'wave' | 'dots' | 'truchet' | 'corners' | 'ripple' | 'blob' | 'sphere'
      softness: number
      intensity: number
      noise: number
      scale?: number
      frame?: number
      offsetX?: number
      offsetY?: number
    }

export type Layout = 'specimen' | 'nocturne' | 'lightbox' | 'monograph'

export interface Theme {
  id: number
  name: string
  layout: Layout
  vars: Record<string, string>
  hero: ShaderSpec
  ambient: ShaderSpec
  /** How many slides carry a portrait photo (Monograph family only). */
  people?: 'some' | 'many'
  /** Replace the title plate with special art. */
  titleArt?: 'hoop'
}

export const themes: Theme[] = [
  {
    id: 1,
    name: 'Specimen',
    layout: 'specimen',
    vars: {
      '--bg': '#ECEDE9',
      '--panel': '#ECEDE9',
      '--ink': '#16191D',
      '--muted': '#5E646B',
      '--faint': '#A7ACAF',
      '--rule': '#D2D5D0',
      '--track': '#DCDFDA',
      '--accent': '#3D5B7C',
      '--accent-soft': '#A9B9CA',
      '--serif': "'Newsreader Variable', Georgia, serif",
      '--sans': "'Hanken Grotesk Variable', system-ui, sans-serif",
      '--display-weight': '380',
      '--display-tracking': '-0.025em',
    },
    hero: {
      kind: 'mesh',
      colors: ['#F2F2EE', '#C4CDD2', '#8FA1AE', '#E3E5DF', '#B7BFB6'],
      positions: 38,
      waveX: 0.7,
      waveXShift: 0.2,
      waveY: 0.85,
      waveYShift: 0.55,
      mixing: 0.85,
      grainMixer: 0.12,
      grainOverlay: 0.22,
    },
    ambient: {
      kind: 'mesh',
      colors: ['#E6E8E3', '#BCC6CC', '#94A5B1', '#DDE0DA'],
      positions: 38,
      waveX: 0.6,
      waveXShift: 0.3,
      waveY: 0.9,
      waveYShift: 0.4,
      mixing: 0.9,
      grainMixer: 0.12,
      grainOverlay: 0.22,
    },
  },
  {
    id: 2,
    name: 'Nocturne',
    layout: 'nocturne',
    vars: {
      '--bg': '#10131A',
      '--panel': '#10131A',
      '--ink': '#ECE8E1',
      '--muted': '#959AA3',
      '--faint': '#4D535E',
      '--rule': '#262B35',
      '--track': '#1F242D',
      '--accent': '#B8C9DB',
      '--accent-soft': '#56677A',
      '--serif': "'Cormorant Garamond Variable', Georgia, serif",
      '--sans': "'Manrope Variable', system-ui, sans-serif",
      '--display-weight': '420',
      '--display-tracking': '-0.015em',
    },
    hero: {
      kind: 'dither',
      colorBack: '#10131A',
      colorFront: '#5A6678',
      shape: 'sphere',
      type: '4x4',
      size: 3,
      scale: 0.9,
      frame: 4200,
    },
    ambient: {
      kind: 'dither',
      colorBack: '#10131A',
      colorFront: '#181D27',
      shape: 'warp',
      type: '4x4',
      size: 3,
      scale: 1.2,
      frame: 9000,
    },
  },
  {
    id: 3,
    name: 'Lightbox',
    layout: 'lightbox',
    vars: {
      '--bg': '#3A4046',
      '--panel': '#F1F2F2',
      '--ink': '#111417',
      '--muted': '#5B6167',
      '--faint': '#A8AEB3',
      '--rule': '#D8DCDF',
      '--track': '#E1E4E6',
      '--accent': '#2F5D5A',
      '--accent-soft': '#9DB8B5',
      '--serif': "'Libre Caslon Display', Georgia, serif",
      '--sans': "'Libre Franklin Variable', system-ui, sans-serif",
      '--display-weight': '400',
      '--display-tracking': '-0.02em',
    },
    hero: {
      kind: 'grain',
      colorBack: '#1B1F23',
      colors: ['#E3E8EA', '#9AA7B0', '#5D6A73'],
      shape: 'wave',
      softness: 0.85,
      intensity: 0.35,
      noise: 0.25,
      scale: 1,
      frame: 0,
    },
    ambient: {
      kind: 'grain',
      colorBack: '#1B1F23',
      colors: ['#C3CBD0', '#7F8C95', '#4B565E'],
      shape: 'corners',
      softness: 0.85,
      intensity: 0.35,
      noise: 0.25,
      scale: 1.4,
      frame: 0,
    },
  },
  {
    id: 4,
    name: 'Monograph',
    layout: 'monograph',
    vars: {
      '--bg': '#F3EEE4',
      '--panel': '#F3EEE4',
      '--ink': '#1F1C18',
      '--muted': '#6B655B',
      '--faint': '#B8AF9F',
      '--rule': '#E0D8C8',
      '--track': '#E8E0D2',
      '--accent': '#3F4A7A',
      '--accent-soft': '#B7BCD6',
      '--serif': "'Spectral', Georgia, serif",
      '--sans': "'Work Sans Variable', system-ui, sans-serif",
      '--display-weight': '300',
      '--display-tracking': '-0.03em',
    },
    hero: {
      kind: 'dither',
      colorBack: '#F3EEE4',
      colorFront: '#1F1C18',
      shape: 'warp',
      type: '8x8',
      size: 2,
      scale: 0.7,
      frame: 5200,
    },
    ambient: {
      kind: 'dither',
      colorBack: '#F3EEE4',
      colorFront: '#1F1C18',
      shape: 'warp',
      type: '8x8',
      size: 2,
      scale: 0.35,
      frame: 3000,
    },
  },
]

const monograph = themes[3]
themes.push(
  { ...monograph, id: 5, name: 'Monograph, one portrait', people: 'some' },
  { ...monograph, id: 6, name: 'Monograph, people', people: 'many' },
  { ...monograph, id: 7, name: 'Monograph, hoop', titleArt: 'hoop' },
)
