import { useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { edgeStyle, layoutGraph } from '../lib/layout'
import type { GraphData } from '../lib/types'
import { statusStyle } from '../lib/theme'
import { downloadSvgElement } from './charts/primitives'
import { Button, EmptyState } from './ui'

/** The design graph, drawn once and then still.
 *
 * No physics, no drift, no dragging. The layout is computed by
 * `lib/layout.ts` from the graph alone, so the same project always produces the
 * same picture — which is what makes it usable as a paper figure and what lets
 * you see at a glance that something moved between two runs.
 *
 * Interaction is limited on purpose: zoom, pan, and click a box to see only what
 * it connects to. Everything else was noise.
 *
 * Conformance status is carried three ways — the border colour, a glyph in the
 * corner of the box, and the written label in the legend — because the reserved
 * status palette puts green and red close together under deuteranopia, and a
 * printed figure may be greyscale.
 */
export function GraphView({
  data,
  height = 460,
  caption,
  projectName = 'design-graph',
}: {
  data: GraphData | null
  height?: number
  caption?: string
  projectName?: string
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState<{ x: number; y: number } | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const layout = useMemo(() => {
    if (!data || data.nodes.length === 0) return null
    const visible = {
      nodes: data.nodes.filter((node) => !hidden.has(node.status)),
      links: data.links,
    }
    return layoutGraph(visible)
  }, [data, hidden])

  const statuses = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of data?.nodes ?? []) {
      counts.set(node.status, (counts.get(node.status) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  if (!data || data.nodes.length === 0) {
    return (
      <EmptyState title="No graph yet">
        Run an analysis and the design graph will be drawn here.
      </EmptyState>
    )
  }

  if (!layout || layout.nodes.length === 0) {
    return <EmptyState title="Everything is hidden">Turn a status back on to see the graph.</EmptyState>
  }

  /** Which nodes stay lit when one is selected. */
  const connected = new Set<string>()
  if (selected) {
    connected.add(selected)
    for (const edge of layout.edges) {
      if (edge.source.id === selected) connected.add(edge.target.id)
      if (edge.target.id === selected) connected.add(edge.source.id)
    }
  }

  function toggleStatus(status: string) {
    const next = new Set(hidden)
    if (next.has(status)) next.delete(status)
    else next.add(status)
    setHidden(next)
    setSelected(null)
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {statuses.map(([status, total]) => {
            const style = statusStyle(status)
            const off = hidden.has(status)
            return (
              <button
                key={status}
                onClick={() => toggleStatus(status)}
                aria-pressed={!off}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition ${
                  off ? 'border-hairline text-muted' : 'border-hairline text-ink-2 hover:text-ink'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full text-[9px] font-bold text-plane"
                  style={{ background: off ? '#6d6a64' : style.color }}
                >
                  {style.glyph}
                </span>
                {style.label}
                <span className="tabular-nums text-muted">{total}</span>
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}>
            −
          </Button>
          <span className="w-12 text-center text-xs tabular-nums text-muted">
            {Math.round(zoom * 100)}%
          </span>
          <Button variant="ghost" onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}>
            +
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setZoom(1)
              setPan({ x: 0, y: 0 })
              setSelected(null)
            }}
          >
            Reset
          </Button>
          <Button
            variant="ghost"
            onClick={() => downloadSvgElement(svgRef.current, `${projectName}-design-graph.svg`)}
          >
            Save as SVG
          </Button>
        </div>
      </div>

      <div
        className="overflow-hidden rounded-lg border border-hairline bg-surface"
        style={{ height }}
        onMouseDown={(event: MouseEvent<HTMLDivElement>) =>
          setDragging({ x: event.clientX - pan.x, y: event.clientY - pan.y })
        }
        onMouseMove={(event: MouseEvent<HTMLDivElement>) => {
          if (!dragging) return
          setPan({ x: event.clientX - dragging.x, y: event.clientY - dragging.y })
        }}
        onMouseUp={() => setDragging(null)}
        onMouseLeave={() => setDragging(null)}
        role="application"
        aria-label="Design graph. Drag to pan, use the buttons to zoom."
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className={`h-full w-full ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
                    markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94918a" />
            </marker>
            <marker id="arrow-lit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
                    markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#f7f7f5" />
            </marker>
          </defs>

          <g data-viewport transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {/* Layer bands, drawn first so nothing sits on top of a box. */}
            {layout.layerLabels.map((band) => (
              <text
                key={band.layer}
                x={6}
                y={band.y - 26}
                fontSize="10"
                fill="#6d6a64"
                letterSpacing="0.06em"
              >
                {band.label.toUpperCase()}
              </text>
            ))}

            {layout.edges.map((edge, index) => {
              const style = edgeStyle(edge.relation)
              const lit =
                !selected || edge.source.id === selected || edge.target.id === selected
              return (
                <path
                  key={`${edge.source.id}-${edge.target.id}-${index}`}
                  d={edge.path}
                  fill="none"
                  stroke={lit && selected ? '#f7f7f5' : '#94918a'}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash || undefined}
                  opacity={selected ? (lit ? 0.9 : 0.08) : style.opacity}
                  markerEnd={lit && selected ? 'url(#arrow-lit)' : 'url(#arrow)'}
                />
              )
            })}

            {layout.nodes.map((node) => {
              const style = statusStyle(node.status)
              const dimmed = selected !== null && !connected.has(node.id)
              const isSelected = selected === node.id
              return (
                <g
                  key={node.id}
                  opacity={dimmed ? 0.15 : 1}
                  onClick={(event: MouseEvent<SVGGElement>) => {
                    event.stopPropagation()
                    setSelected(isSelected ? null : node.id)
                  }}
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    event.stopPropagation()
                    setSelected(isSelected ? null : node.id)
                  }}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  aria-label={`${node.label} — ${style.label}. ${style.description}`}
                  className="cursor-pointer"
                >
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.width}
                    height={node.height}
                    rx={6}
                    fill="#262625"
                    stroke={style.color}
                    strokeWidth={isSelected ? 2.5 : 1.5}
                  />
                  <text
                    x={node.x + node.width / 2}
                    y={node.y + node.height / 2 + 4}
                    textAnchor="middle"
                    fontSize="12"
                    fill="#f7f7f5"
                  >
                    {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
                  </text>
                  {/* The glyph repeats the status without relying on colour. */}
                  <text
                    x={node.x + node.width - 7}
                    y={node.y + 12}
                    textAnchor="end"
                    fontSize="10"
                    fill={style.color}
                    aria-hidden="true"
                  >
                    {style.glyph}
                  </text>
                  <title>{`${node.label} — ${style.label}. ${style.description}`}</title>
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>
          {layout.nodes.length} classes · {layout.edges.length} relationships ·
          {' '}
          {selected ? 'showing what this connects to — click again to clear' : 'click a box to isolate it'}
        </span>
        <span className="flex flex-wrap gap-3">
          <span>── extends</span>
          <span>- - implements</span>
          <span>··· association</span>
        </span>
      </div>

      {caption && <p className="mt-2 text-xs text-muted">{caption}</p>}

      {selected && (
        <p className="mt-1 font-mono text-xs text-ink-2">
          {layout.nodes.find((node) => node.id === selected)?.source_file ?? ''}
        </p>
      )}
    </div>
  )
}
