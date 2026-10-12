import { ImageDithering } from '@paper-design/shaders-react'

// Title art for the Monograph hoop variant: a dithered photo of a hoop with two
// shot trajectories drawn over it, one off the rim and one through the net.
// Geometry is in slide pixels (1920x1080); the plate fills the right 760px.
const PLATE_X = 1160

export function HoopPlate() {
  return (
    <>
      <div className="art art-hero hoop-plate">
        <ImageDithering
          style={{ position: 'absolute', inset: 0 }}
          image="/hoop.webp"
          colorBack="#1F1C18"
          colorFront="#F3EEE4"
          colorHighlight="#F3EEE4"
          type="8x8"
          size={2}
          colorSteps={2}
          fit="cover"
        />
      </div>
      <svg className="shots" width="1920" height="1080" viewBox="0 0 1920 1080" aria-hidden>
        <defs>
          <mask id="draw-miss" maskUnits="userSpaceOnUse">
            <path className="draw draw-1" pathLength={1} d={MISS} />
            <path className="draw draw-2" pathLength={1} d={BOUNCE} />
          </mask>
          <mask id="draw-make" maskUnits="userSpaceOnUse">
            <path className="draw draw-3" pathLength={1} d={MAKE} />
          </mask>
        </defs>
        <g mask="url(#draw-miss)">
          <path className="shot shot-miss" d={MISS} />
          <path className="shot shot-miss" d={BOUNCE} />
        </g>
        <circle className="shot-contact" cx={RIM_LEFT.x} cy={RIM_LEFT.y} r={11} />
        <g mask="url(#draw-make)">
          <path className="shot shot-make" d={MAKE} />
        </g>
      </svg>
    </>
  )
}

// Rim, measured on the photo (center 0.655, 0.32 of the frame) and mapped
// through the plate's cover crop.
const RIM = { x: PLATE_X + 498, y: 338 }
const RIM_LEFT = { x: RIM.x - 150, y: RIM.y + 30 }

const MISS = `M 990 1120 C 1150 420, 1330 150, ${RIM_LEFT.x} ${RIM_LEFT.y}`
const BOUNCE = `M ${RIM_LEFT.x} ${RIM_LEFT.y} Q 1430 250, 1270 820`
const MAKE = `M 1050 1120 C 1250 330, 1560 -60, ${RIM.x} ${RIM.y - 6} L ${RIM.x + 6} 620`
