import { useState } from 'react'
import type { Ref } from 'react'
import type { DriftSeries } from '../../lib/statsTypes'
import { EmptyChart, INK, Legend, formatNumber, niceTicks, seriesColor } from './primitives'

/** Figure 2 — design violations building up over a project's history.
 *
 * A line going up means the code and the diagram are drifting apart. Flat means
 * they are keeping pace.
 *
 * Up to three projects take the validated categorical hues. Beyond three,
 * colour cannot separate them safely on this surface in any ordering, so every
 * line is drawn muted and identity moves to a direct label at the right-hand
 * end of each line — which is where the eye is already looking.
 */
export function DriftChart({
  series,
  svgRef,
}: {
  series: DriftSeries[]
  svgRef?: Ref<SVGSVGElement>
}) {
  const [hovered, setHovered] = useState<string | null>(null)

  const usable = series.filter((entry) => entry.points.length >= 2)
  if (usable.length === 0) {
    return (
      <EmptyChart message="Needs at least two analyses of the same project. Analyse again after the code changes." />
    )
  }

  const width = 620
  const height = 260
  const margin = { top: 12, right: 108, bottom: 40, left: 46 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom

  const allPoints = usable.flatMap((entry) => entry.points)
  const maxIndex = Math.max(1, ...allPoints.map((point) => point.commit_index))
  const maxValue = Math.max(1, ...allPoints.map((point) => point.violations))
  const ticks = niceTicks(maxValue, 4)
  const scaleMax = ticks[ticks.length - 1] || 1

  const x = (index: number) => margin.left + (index / maxIndex) * plotWidth
  const y = (value: number) => margin.top + plotHeight - (value / scaleMax) * plotHeight

  const useColour = usable.length <= 3

  return (
    <div>
      <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} className="w-full" role="img"
           aria-label="Design violations accumulating over commits, one line per project">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={margin.left} x2={margin.left + plotWidth} y1={y(tick)} y2={y(tick)}
                  stroke={INK.grid} strokeWidth={1} />
            <text x={margin.left - 8} y={y(tick) + 4} textAnchor="end" fontSize="11"
                  fill={INK.muted}>
              {formatNumber(tick, 0)}
            </text>
          </g>
        ))}

        <text x={margin.left + plotWidth / 2} y={height - 6} textAnchor="middle" fontSize="11"
              fill={INK.muted}>
          commits analysed
        </text>
        <text x={12} y={margin.top + plotHeight / 2} fontSize="11" fill={INK.muted}
              transform={`rotate(-90 12 ${margin.top + plotHeight / 2})`} textAnchor="middle">
          violations
        </text>

        {usable.map((entry, index) => {
          const active = hovered === entry.project
          const colour = useColour ? seriesColor(index) : INK.secondary
          const path = entry.points
            .map((point, i) => `${i === 0 ? 'M' : 'L'} ${x(point.commit_index)} ${y(point.violations)}`)
            .join(' ')
          const last = entry.points[entry.points.length - 1]

          return (
            <g key={entry.project} onMouseEnter={() => setHovered(entry.project)}
               onMouseLeave={() => setHovered(null)}>
              <path d={path} fill="none" stroke={colour} strokeWidth={active ? 2.5 : 2}
                    strokeLinejoin="round" strokeLinecap="round"
                    opacity={hovered && !active ? 0.3 : 1} />
              {/* A 2px surface ring keeps the end marker readable where lines cross. */}
              <circle cx={x(last.commit_index)} cy={y(last.violations)} r={4} fill={colour}
                      stroke={INK.surface} strokeWidth={2}
                      opacity={hovered && !active ? 0.3 : 1} />
              <text x={x(last.commit_index) + 10} y={y(last.violations) + 4} fontSize="11"
                    fill={active ? INK.primary : INK.secondary}
                    opacity={hovered && !active ? 0.4 : 1}>
                {entry.project.length > 12 ? `${entry.project.slice(0, 11)}…` : entry.project}
              </text>
            </g>
          )
        })}
      </svg>

      {useColour && (
        <Legend
          items={usable.map((entry, index) => ({
            label: entry.project,
            color: seriesColor(index),
          }))}
        />
      )}

      <p className="mt-1 text-xs text-muted">
        A line going up means the code and the diagram are drifting apart. Flat means they are
        keeping pace.
      </p>
    </div>
  )
}
