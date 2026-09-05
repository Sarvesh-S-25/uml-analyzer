import { useState } from 'react'
import type { Ref } from 'react'
import type { SkipDatum } from '../../lib/statsTypes'
import { EmptyChart, INK, STATUS, formatPercent, niceTicks, seriesColor } from './primitives'

/** Figure 1 — how much each gate skipped, and what that cost.
 *
 * The bar is the saving; the tag at its end is the price. They are drawn in one
 * figure because they are meaningless apart: a gate that never skips has a
 * perfect miss rate and saves nothing, and a gate that skips everything is free
 * and useless. Putting them in separate charts is how that gets quoted wrongly.
 *
 * The miss count is a **number on the bar**, not a second colour. Colour here
 * carries only status — safe, or leaky — and always alongside a glyph and a
 * written count, because the reserved status palette puts green and red close
 * together under deuteranopia.
 */
export function BarChart({
  data,
  svgRef,
}: {
  data: SkipDatum[]
  svgRef?: Ref<SVGSVGElement>
}) {
  const [hovered, setHovered] = useState<number | null>(null)

  const usable = data.filter((datum) => datum.skip_rate !== null)
  if (usable.length === 0) return <EmptyChart message="No runs recorded yet." />

  const rowHeight = 46
  const width = 620
  const margin = { top: 14, right: 132, bottom: 30, left: 116 }
  const plotWidth = width - margin.left - margin.right
  const height = margin.top + margin.bottom + data.length * rowHeight

  const ticks = niceTicks(1, 5)
  const x = (value: number) => value * plotWidth

  return (
    <div>
      <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} className="w-full" role="img"
           aria-label="Share of runs skipped by each gate, with the number of missed changes">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={margin.left + x(tick)} x2={margin.left + x(tick)} y1={margin.top}
                  y2={height - margin.bottom} stroke={INK.grid} strokeWidth={1} />
            <text x={margin.left + x(tick)} y={height - margin.bottom + 16} textAnchor="middle"
                  fontSize="11" fill={INK.muted}>
              {formatPercent(tick, 0)}
            </text>
          </g>
        ))}
        <text x={margin.left + plotWidth / 2} y={height - 2} textAnchor="middle" fontSize="11"
              fill={INK.muted}>
          share of runs skipped
        </text>

        {data.map((datum, index) => {
          const y = margin.top + index * rowHeight
          const barHeight = 20
          const value = datum.skip_rate ?? 0
          const active = hovered === index
          const leaky = (datum.missed ?? 0) > 0
          const status = datum.missed === null ? INK.muted : leaky ? STATUS.warning : STATUS.good

          return (
            <g key={datum.gate} onMouseEnter={() => setHovered(index)}
               onMouseLeave={() => setHovered(null)}>
              <text x={margin.left - 10} y={y + barHeight - 3} textAnchor="end" fontSize="12"
                    fill={active ? INK.primary : INK.secondary} fontFamily="ui-monospace, monospace">
                {datum.gate}
              </text>

              {/* The saving. */}
              <rect x={margin.left} y={y + 2} width={Math.max(2, x(value))} height={barHeight}
                    rx={4} fill={seriesColor(0)} opacity={active ? 1 : 0.9} />

              {/* The 95% interval, drawn only where one exists. */}
              {datum.low !== null && datum.high !== null && (
                <g stroke={INK.primary} strokeWidth={1.5} opacity={0.7}>
                  <line x1={margin.left + x(datum.low)} x2={margin.left + x(datum.high)}
                        y1={y + 2 + barHeight / 2} y2={y + 2 + barHeight / 2} />
                  <line x1={margin.left + x(datum.low)} x2={margin.left + x(datum.low)}
                        y1={y + 5} y2={y + barHeight} />
                  <line x1={margin.left + x(datum.high)} x2={margin.left + x(datum.high)}
                        y1={y + 5} y2={y + barHeight} />
                </g>
              )}

              <text x={margin.left + x(value) + 8} y={y + barHeight - 3} fontSize="12"
                    fill={INK.secondary} className="tabular-nums">
                {formatPercent(datum.skip_rate)}
              </text>

              {/* The price, in words, on the row it belongs to. */}
              <text x={width - margin.right + 78} y={y + barHeight - 3} textAnchor="end"
                    fontSize="11" fill={status}>
                {datum.missed === null
                  ? 'misses not measured'
                  : datum.missed === 0
                    ? '✓ missed nothing'
                    : `! missed ${datum.missed}`}
              </text>
            </g>
          )
        })}
      </svg>

      <p className="mt-1 min-h-[2rem] rounded border border-hairline bg-surface-2 px-3 py-2 text-xs text-ink-2">
        {hovered !== null && data[hovered] ? (
          <>
            <span className="font-mono text-ink">{data[hovered].gate}</span> — skipped{' '}
            {formatPercent(data[hovered].skip_rate)} of {data[hovered].runs} runs
            {data[hovered].low !== null && (
              <> (between {formatPercent(data[hovered].low, 0)} and {formatPercent(data[hovered].high, 0)} if repeated)</>
            )}
            {data[hovered].missed !== null && (
              <>, missing {data[hovered].missed} real change{data[hovered].missed === 1 ? '' : 's'}</>
            )}
            .
          </>
        ) : (
          <span className="text-muted">
            Bar length is the saving. The tag on the right is what it cost.
          </span>
        )}
      </p>
    </div>
  )
}
