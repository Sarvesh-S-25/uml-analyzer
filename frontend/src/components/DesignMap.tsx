import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent, WheelEvent } from 'react'
import { edgeStyle, layoutGraph } from '../lib/layout'
import type { GraphData } from '../lib/types'
import { resolveColor, statusStyle } from '../lib/theme'
import { downloadSvgElement } from './charts/primitives'
import { Button, EmptyState, IconButton, Input, StatusChip } from './ui'

/** The design, drawn once and then still.
 *
 * No physics, no drift, no dragging of nodes. The layout comes from
 * `lib/layout.ts` and depends only on the graph, so the same project always
 * produces the same picture — which is what makes it usable as a paper figure
 * and what lets you see at a glance that something moved between two runs.
 *
 * Status is carried three ways at once — border colour, a glyph in the corner
 * of the box, and the written word in the legend — because the reserved palette
 * puts green and red close together under deuteranopia and a printed figure may
 * be greyscale.
 */
export function DesignMap({
  data,
  height = 480,
  caption,
  projectName = 'design-map',
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
  const [search, setSearch] = useState('')

  const layout = useMemo(() => {
    if (!data || data.nodes.length === 0) return null
    return layoutGraph({
      nodes: data.nodes.filter((node) => !hidden.has(node.status)),
      links: data.links,
    })
  }, [data, hidden])

  const statuses = useMemo(() => {
    const counts = new Map<string, number>()
    for (const node of data?.nodes ?? []) {
      counts.set(node.status, (counts.get(node.status) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  const matches = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle || !layout) return new Set<string>()
    return new Set(
      layout.nodes.filter((node) => node.label.toLowerCase().includes(needle)).map((n) => n.id),
    )
  }, [search, layout])

  // Escape clears the selection, which is otherwise a dead end on a big graph.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!data || data.nodes.length === 0) {
    return (
      <EmptyState title="No map yet" icon="◈">
        Run a check and every class the code reader found is drawn here, arranged in layers.
      </EmptyState>
    )
  }
  if (!layout || layout.nodes.length === 0) {
    return (
      <EmptyState title="Everything is hidden">
        Turn a status back on using the buttons above to see the map again.
      </EmptyState>
    )
  }

  const connected = new Set<string>()
  if (selected) {
    connected.add(selected)
    for (const edge of layout.edges) {
      if (edge.source.id === selected) connected.add(edge.target.id)
      if (edge.target.id === selected) connected.add(edge.source.id)
    }
  }

  const selectedNode = layout.nodes.find((node) => node.id === selected)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {statuses.map(([status, total]) => {
            const off = hidden.has(status)
            return (
              <button
                key={status}
                onClick={() => {
                  setHidden((current) => {
                    const next = new Set(current)
                    if (next.has(status)) next.delete(status)
                    else next.add(status)
                    return next
                  })
                  setSelected(null)
                }}
                aria-pressed={!off}
                title={off ? 'Hidden — click to show' : 'Shown — click to hide'}
                className={`transition ${off ? 'opacity-35 grayscale' : ''}`}
              >
                <StatusChip status={status} count={total} size="sm" />
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-1">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a class…"
            aria-label="Find a class in the map"
            className="w-36 py-1 text-xs"
          />
          <IconButton label="Zoom out" onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}>
            −
          </IconButton>
          <span className="w-10 text-center text-xs tabular-nums text-muted">
            {Math.round(zoom * 100)}%
          </span>
          <IconButton label="Zoom in" onClick={() => setZoom((z) => Math.min(3, z + 0.2))}>
            +
          </IconButton>
          <Button
            size="sm"
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
            size="sm"
            variant="ghost"
            onClick={() => {
              // A `var()` reference means nothing outside this page, so the
              // clone is walked and every colour replaced with the value the
              // browser is currently painting. Without this an exported figure
              // is black shapes on a black ground.
              downloadSvgElement(
                svgRef.current,
                `${projectName}-design-map.svg`,
                resolveColor('var(--surface)'),
                true,
              )
            }}
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
        onWheel={(event: WheelEvent<HTMLDivElement>) => {
          if (!event.ctrlKey && !event.metaKey) return
          event.preventDefault()
          setZoom((z) => Math.max(0.4, Math.min(3, z - event.deltaY / 500)))
        }}
        role="application"
        aria-label="Design map. Drag to pan; hold Ctrl and scroll to zoom."
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className={`h-full w-full ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <marker id="dm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
                    markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted)" />
            </marker>
            <marker id="dm-arrow-lit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6"
                    markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink)" />
            </marker>
          </defs>

          <g data-viewport transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {/* Layer bands first, so nothing sits on top of a box. */}
            {layout.layerLabels.map((band) => (
              <text
                key={band.layer}
                x={6}
                y={band.y - 26}
                fontSize="10"
                fill="var(--muted)"
                letterSpacing="0.06em"
              >
                {band.label.toUpperCase()}
              </text>
            ))}

            {layout.edges.map((edge, index) => {
              const style = edgeStyle(edge.relation)
              const lit = !selected || edge.source.id === selected || edge.target.id === selected
              return (
                <path
                  key={`${edge.source.id}-${edge.target.id}-${index}`}
                  d={edge.path}
                  fill="none"
                  stroke={lit && selected ? 'var(--ink)' : 'var(--muted)'}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash || undefined}
                  opacity={selected ? (lit ? 0.9 : 0.07) : style.opacity}
                  markerEnd={lit && selected ? 'url(#dm-arrow-lit)' : 'url(#dm-arrow)'}
                />
              )
            })}

            {layout.nodes.map((node) => {
              const style = statusStyle(node.status)
              const dimmed = selected !== null && !connected.has(node.id)
              const isSelected = selected === node.id
              const isMatch = matches.has(node.id)
              return (
                <g
                  key={node.id}
                  opacity={dimmed ? 0.14 : 1}
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
                    fill={isMatch ? style.wash : 'var(--surface-2)'}
                    stroke={style.color}
                    strokeWidth={isSelected || isMatch ? 2.5 : 1.4}
                  />
                  <text
                    x={node.x + node.width / 2}
                    y={node.y + node.height / 2 + 4}
                    textAnchor="middle"
                    fontSize="12"
                    fill="var(--ink)"
                  >
                    {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
                  </text>
                  {/* The glyph repeats the status without relying on colour. */}
                  <text
                    x={node.x + node.width - 7}
                    y={node.y + 12}
                    textAnchor="end"
                    fontSize="10"
                    fontWeight="bold"
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
          {layout.nodes.length} classes · {layout.edges.length} relationships ·{' '}
          {selected ? 'showing only what this connects to — Esc to clear' : 'click a box to isolate it'}
        </span>
        <span className="flex flex-wrap gap-3">
          <span>—— extends</span>
          <span>- - - implements</span>
          <span>····· uses</span>
        </span>
      </div>

      {selectedNode && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-hairline bg-surface-2 px-3 py-2">
          <span className="font-mono text-xs font-medium text-ink">{selectedNode.label}</span>
          <StatusChip status={selectedNode.status} size="sm" />
          <span className="text-xs text-muted">{statusStyle(selectedNode.status).description}</span>
          {selectedNode.source_file && (
            <span className="ml-auto truncate font-mono text-[11px] text-muted">
              {selectedNode.source_file}
            </span>
          )}
        </div>
      )}

      {caption && <p className="mt-2 text-xs text-muted">{caption}</p>}
    </div>
  )
}
