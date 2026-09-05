import { useState } from 'react'
import type { Ref } from 'react'
import type { ParetoDatum } from '../../lib/statsTypes'
import { EmptyChart, INK, formatPercent, niceTicks, seriesColor } from './primitives'

/** Figure 3 — what each gate saves against what it catches.
 *
 * The whole paper is one tradeoff, and this is that tradeoff as a picture: how
 * often a gate skipped, against how often it re-analysed when conformance had
 * really changed. A gate that is further right saves more; a gate that is
 * higher misses less. A gate with something both above it and to its right was
 * beaten on both counts at once and there is no reason to choose it.
 *
 * Two honesty rules, because a scatter plot invites over-reading:
 *   - both axes carry 95% intervals, drawn as crosshair bars, so a difference
 *     smaller than the uncertainty is visibly smaller than the uncertainty;
 *   - "dominated" is only *labelled* on the chart when the backend also found
 *     the intervals separated. Dominance on point estimates alone is left to
 *     the table, where it can be read with its caveats.
 *
 * Every point is directly labelled with its gate name. Colour is decorative
 * here and carries nothing a reader would lose in greyscale.
 */
export function ParetoChart({
  data,
  svgRef,
}: {
  data: ParetoDatum[]
  svgRef?: Ref<SVGSVGElement>
}) {
  const [hovered, setHovered] = useState<string | null>(null)

  const usable = data.filter(
    (datum) => datum.skip_rate !== null && datum.recall !== null,
  )
  if (usable.length === 0) {
    return <EmptyChart message="Needs an oracle before recall can be measured." />
  }

  const width = 620
  const height = 380
  const margin = { top: 18, right: 26, bottom: 46, left: 62 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom

  const x = (value: number) => margin.left + value * plotWidth
  // Recall is plotted over its full 0-1 range rather than zoomed to the data:
  // a zoomed axis would make a two-point difference look decisive.
  const y = (value: number) => margin.top + (1 - value) * plotHeight
  const ticks = niceTicks(1, 5)

  return (
    <div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label="Skip rate against recall, one point per gate"
      >
        <rect width={width} height={height} fill={INK.surface} />

        {/* Grid and axes */}
        {ticks.map((tick) => (
          <g key={`v${tick}`}>
            <line
              x1={x(tick)}
              y1={margin.top}
              x2={x(tick)}
              y2={margin.top + plotHeight}
              stroke={INK.grid}
              strokeWidth={1}
            />
            <text
              x={x(tick)}
              y={margin.top + plotHeight + 18}
              textAnchor="middle"
              fontSize="10"
              fill={INK.muted}
            >
              {formatPercent(tick, 0)}
            </text>
          </g>
        ))}
        {ticks.map((tick) => (
          <g key={`h${tick}`}>
            <line
              x1={margin.left}
              y1={y(tick)}
              x2={margin.left + plotWidth}
              y2={y(tick)}
              stroke={INK.grid}
              strokeWidth={1}
            />
            <text x={margin.left - 8} y={y(tick) + 3} textAnchor="end" fontSize="10" fill={INK.muted}>
              {formatPercent(tick, 0)}
            </text>
          </g>
        ))}

        <text
          x={margin.left + plotWidth / 2}
          y={height - 8}
          textAnchor="middle"
          fontSize="11"
          fill={INK.secondary}
        >
          Share of checks skipped  →  cheaper
        </text>
        <text
          x={14}
          y={margin.top + plotHeight / 2}
          textAnchor="middle"
          fontSize="11"
          fill={INK.secondary}
          transform={`rotate(-90 14 ${margin.top + plotHeight / 2})`}
        >
          Real changes caught  →  safer
        </text>

        {usable.map((point, index) => {
          const cx = x(point.skip_rate as number)
          const cy = y(point.recall as number)
          const colour = seriesColor(index)
          const active = hovered === point.gate
          const beaten = point.robustly_dominated_by.length > 0

          return (
            <g
              key={point.gate}
              onMouseEnter={() => setHovered(point.gate)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Interval bars: horizontal for skip rate, vertical for recall. */}
              {point.skip_low !== null && point.skip_high !== null && (
                <line
                  x1={x(point.skip_low)}
                  y1={cy}
                  x2={x(point.skip_high)}
                  y2={cy}
                  stroke={colour}
                  strokeWidth={1.5}
                  opacity={0.5}
                />
              )}
              {point.recall_low !== null && point.recall_high !== null && (
                <line
                  x1={cx}
                  y1={y(point.recall_low)}
                  x2={cx}
                  y2={y(point.recall_high)}
                  stroke={colour}
                  strokeWidth={1.5}
                  opacity={0.5}
                />
              )}

              <circle
                cx={cx}
                cy={cy}
                r={active ? 8 : 6}
                fill={point.on_frontier ? colour : INK.surface}
                stroke={colour}
                strokeWidth={2}
              />
              {/* A hollow marker means "beaten on both axes"; the written note
                  below the chart says so too, so the shape is never the only
                  carrier of that meaning. */}
              {beaten && (
                <text x={cx} y={cy + 3.5} textAnchor="middle" fontSize="9" fill={colour}>
                  ×
                </text>
              )}

              <text
                x={cx + 11}
                y={cy - 8}
                fontSize="11"
                fontWeight={point.on_frontier ? 600 : 400}
                fill={INK.primary}
              >
                {point.gate}
              </text>
              <text x={cx + 11} y={cy + 4} fontSize="9" fill={INK.muted}>
                {formatPercent(point.skip_rate, 0)} skipped · {formatPercent(point.recall, 0)} caught
              </text>
            </g>
          )
        })}
      </svg>

      <ul className="mt-2 space-y-1 text-xs text-muted">
        {usable
          .filter((point) => point.dominated_by.length > 0)
          .map((point) => (
            <li key={point.gate}>
              <span className="font-mono text-ink-2">{point.gate}</span> is beaten on both counts
              by <span className="font-mono text-ink-2">{point.dominated_by.join(', ')}</span>
              {point.robustly_dominated_by.length > 0
                ? ' — and the intervals do not overlap, so the difference is not just noise.'
                : ' — but the intervals overlap, so treat this as suggestive rather than settled.'}
            </li>
          ))}
        {usable.every((point) => point.dominated_by.length === 0) && (
          <li>
            No gate is beaten on both counts: each one buys its extra savings with real accuracy,
            so the choice is a genuine trade rather than an obvious answer.
          </li>
        )}
      </ul>
    </div>
  )
}
