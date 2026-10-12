import { Dithering, GrainGradient, StaticMeshGradient } from '@paper-design/shaders-react'
import type { ShaderSpec } from './themes'

const fill = { position: 'absolute', inset: 0, width: '100%', height: '100%' } as const

// Every shader is rendered static (speed 0) so slides read like printed plates.
export function Backdrop({ spec, className }: { spec: ShaderSpec; className?: string }) {
  if (spec.kind === 'mesh') {
    const { kind: _, ...p } = spec
    return (
      <div className={className}>
        <StaticMeshGradient style={fill} speed={0} frame={0} {...p} />
      </div>
    )
  }
  if (spec.kind === 'dither') {
    const { kind: _, ...p } = spec
    return (
      <div className={className}>
        <Dithering style={fill} speed={0} {...p} />
      </div>
    )
  }
  const { kind: _, ...p } = spec
  return (
    <div className={className}>
      <GrainGradient style={fill} speed={0} {...p} />
    </div>
  )
}
