/** Deterministic layered layout for the design graph.
 *
 * The previous view ran a force simulation: nodes drifted, settled somewhere
 * different on every load, and the same project never produced the same picture
 * twice. That is fine for exploring and useless for a paper figure or for
 * telling at a glance what changed between two runs.
 *
 * This is a Sugiyama-style layered layout, run once, with no physics:
 *
 *   1. **Layer assignment.** Architectural naming (`*Controller`, `*Service`,
 *      `*Repository`) pins a node to a layer where the convention exists,
 *      because that is how the diagram was drawn and the reader already thinks
 *      in those terms. Everything else falls back to longest-path layering on
 *      the dependency edges, so a node always sits below what it depends on.
 *   2. **Ordering within a layer.** Barycentre sweeps -- repeatedly place each
 *      node at the average position of its neighbours in the adjacent layer --
 *      which reduces edge crossings. Ties break on node id, so the result is
 *      identical every run.
 *   3. **Coordinates.** Fixed grid. No randomness anywhere; `Math.random` is
 *      never called in this file.
 *
 * Same input, same picture. Every time.
 */
import type { GraphData, GraphLink, GraphNode } from './types'

export interface LaidOutNode extends GraphNode {
  x: number
  y: number
  width: number
  height: number
  layer: number
}

export interface LaidOutEdge {
  source: LaidOutNode
  target: LaidOutNode
  relation: string
  /** SVG path, routed so it leaves the bottom of one box and enters the top of
   *  the next -- or curves around when both boxes share a layer. */
  path: string
}

export interface Layout {
  nodes: LaidOutNode[]
  edges: LaidOutEdge[]
  width: number
  height: number
  layerLabels: Array<{ layer: number; label: string; y: number }>
}

/** Naming conventions that carry architectural intent, most specific first.
 *
 * Matching on the name is not a heuristic hack here: these suffixes are exactly
 * what the class diagram uses to express layering, so honouring them makes the
 * drawn picture match the drawn design.
 */
const LAYER_RULES: Array<{ layer: number; label: string; test: RegExp }> = [
  { layer: 0, label: 'Entry points', test: /(controller|handler|resource|endpoint|router|view|api)$/i },
  { layer: 1, label: 'Application logic', test: /(service|manager|usecase|use_case|facade|engine|processor)$/i },
  { layer: 2, label: 'Data access', test: /(repository|repo|dao|gateway|store|client|adapter)$/i },
  { layer: 3, label: 'Model', test: /(model|entity|dto|record|schema|domain|type)$/i },
]

const NODE_WIDTH = 148
const NODE_HEIGHT = 38
const H_GAP = 26
const V_GAP = 76
const PADDING = 28

export function layoutGraph(data: GraphData, options: { maxNodes?: number } = {}): Layout {
  const maxNodes = options.maxNodes ?? 120

  // Classes and interfaces carry the architecture; methods and fields would
  // swamp the picture. When a project is too large to draw legibly, keep the
  // best-connected nodes rather than an arbitrary prefix.
  const candidates = data.nodes.filter(
    (node) => node.kind === 'class' || node.kind === 'interface' || node.kind === 'module',
  )
  const pool = candidates.length > 0 ? candidates : data.nodes

  const degree = new Map<string, number>()
  for (const link of data.links) {
    degree.set(link.source, (degree.get(link.source) ?? 0) + 1)
    degree.set(link.target, (degree.get(link.target) ?? 0) + 1)
  }

  const kept =
    pool.length <= maxNodes
      ? [...pool]
      : [...pool]
          .sort(
            (a, b) =>
              (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.id.localeCompare(b.id),
          )
          .slice(0, maxNodes)

  const ids = new Set(kept.map((node) => node.id))
  const edges = data.links.filter(
    (link) => ids.has(link.source) && ids.has(link.target) && link.source !== link.target,
  )

  const layerOf = assignLayers(kept, edges)
  const ordered = orderWithinLayers(kept, edges, layerOf)

  // --- coordinates ---------------------------------------------------------
  const byLayer = new Map<number, GraphNode[]>()
  for (const node of ordered) {
    const layer = layerOf.get(node.id) ?? 0
    if (!byLayer.has(layer)) byLayer.set(layer, [])
    byLayer.get(layer)!.push(node)
  }

  const layers = [...byLayer.keys()].sort((a, b) => a - b)
  const widest = Math.max(1, ...layers.map((layer) => byLayer.get(layer)!.length))
  const contentWidth = widest * NODE_WIDTH + (widest - 1) * H_GAP

  const placed = new Map<string, LaidOutNode>()
  for (const [rank, layer] of layers.entries()) {
    const row = byLayer.get(layer)!
    const rowWidth = row.length * NODE_WIDTH + (row.length - 1) * H_GAP
    const startX = PADDING + (contentWidth - rowWidth) / 2

    row.forEach((node, index) => {
      placed.set(node.id, {
        ...node,
        x: startX + index * (NODE_WIDTH + H_GAP),
        y: PADDING + rank * (NODE_HEIGHT + V_GAP),
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        layer,
      })
    })
  }

  const laidOutEdges: LaidOutEdge[] = []
  for (const link of edges) {
    const source = placed.get(link.source)
    const target = placed.get(link.target)
    if (!source || !target) continue
    laidOutEdges.push({
      source,
      target,
      relation: link.relation,
      path: routeEdge(source, target),
    })
  }

  return {
    nodes: [...placed.values()],
    edges: laidOutEdges,
    width: contentWidth + PADDING * 2,
    height: PADDING * 2 + layers.length * (NODE_HEIGHT + V_GAP) - V_GAP,
    layerLabels: layers.map((layer, rank) => ({
      layer,
      label: labelForLayer(byLayer.get(layer)!, layer, rank),
      y: PADDING + rank * (NODE_HEIGHT + V_GAP) + NODE_HEIGHT / 2,
    })),
  }
}

/** Name a band only when it earns the name.
 *
 * Nodes whose names match no convention are placed by dependency depth, and can
 * land in a row that a rule also named. Calling that row "Data access" when half
 * of it is not data access is worse than calling it "Level 3", so the
 * architectural label is used only when most of the row actually matched.
 */
function labelForLayer(row: GraphNode[], layer: number, rank: number): string {
  const rule = LAYER_RULES.find((entry) => entry.layer === layer)
  if (!rule) return `Level ${rank + 1}`
  const matched = row.filter((node) => rule.test.test(node.label)).length
  return matched * 2 >= row.length ? rule.label : `Level ${rank + 1}`
}

/** Which row each node belongs in. */
function assignLayers(nodes: GraphNode[], edges: GraphLink[]): Map<string, number> {
  const layerOf = new Map<string, number>()
  const unpinned: GraphNode[] = []

  for (const node of nodes) {
    const rule = LAYER_RULES.find((entry) => entry.test.test(node.label))
    if (rule) layerOf.set(node.id, rule.layer)
    else unpinned.push(node)
  }

  // Everything the naming convention did not settle: longest path from a node
  // with no incoming dependency. Iterating to a fixed point rather than
  // recursing keeps a cyclic dependency graph -- which real code has -- from
  // blowing the stack.
  for (const node of unpinned) layerOf.set(node.id, 0)

  const unpinnedIds = new Set(unpinned.map((node) => node.id))
  for (let pass = 0; pass < Math.min(nodes.length, 24); pass += 1) {
    let moved = false
    for (const edge of edges) {
      if (!unpinnedIds.has(edge.target)) continue
      const from = layerOf.get(edge.source)
      const to = layerOf.get(edge.target)
      if (from === undefined || to === undefined) continue
      if (to <= from) {
        layerOf.set(edge.target, from + 1)
        moved = true
      }
    }
    if (!moved) break
  }

  // Close gaps, so a layer with nothing in it does not leave a blank band.
  const used = [...new Set([...layerOf.values()])].sort((a, b) => a - b)
  const compacted = new Map(used.map((layer, index) => [layer, index]));
  for (const [id, layer] of layerOf) layerOf.set(id, compacted.get(layer) ?? 0)
  return layerOf
}

/** Left-to-right order inside each row, chosen to reduce crossings. */
function orderWithinLayers(
  nodes: GraphNode[],
  edges: GraphLink[],
  layerOf: Map<string, number>,
): GraphNode[] {
  const byLayer = new Map<number, GraphNode[]>()
  for (const node of [...nodes].sort((a, b) => a.label.localeCompare(b.label))) {
    const layer = layerOf.get(node.id) ?? 0
    if (!byLayer.has(layer)) byLayer.set(layer, [])
    byLayer.get(layer)!.push(node)
  }

  const layers = [...byLayer.keys()].sort((a, b) => a - b)
  const position = new Map<string, number>()
  for (const layer of layers) {
    byLayer.get(layer)!.forEach((node, index) => position.set(node.id, index))
  }

  const neighbours = new Map<string, string[]>()
  for (const edge of edges) {
    if (!neighbours.has(edge.source)) neighbours.set(edge.source, [])
    if (!neighbours.has(edge.target)) neighbours.set(edge.target, [])
    neighbours.get(edge.source)!.push(edge.target)
    neighbours.get(edge.target)!.push(edge.source)
  }

  // Three sweeps down then three up. More converges no further on graphs this
  // size, and the count is fixed so the result cannot vary between runs.
  for (let sweep = 0; sweep < 6; sweep += 1) {
    const order = sweep % 2 === 0 ? layers : [...layers].reverse()
    for (const layer of order) {
      const row = byLayer.get(layer)!
      const barycentre = new Map<string, number>()
      for (const node of row) {
        const linked = (neighbours.get(node.id) ?? []).filter(
          (id) => (layerOf.get(id) ?? 0) !== layer,
        )
        const values = linked.map((id) => position.get(id) ?? 0)
        barycentre.set(
          node.id,
          values.length ? values.reduce((a, b) => a + b, 0) / values.length : position.get(node.id) ?? 0,
        )
      }
      // Tie-break on label, never on insertion order, so the layout is stable.
      row.sort(
        (a, b) =>
          (barycentre.get(a.id) ?? 0) - (barycentre.get(b.id) ?? 0) ||
          a.label.localeCompare(b.label),
      )
      row.forEach((node, index) => position.set(node.id, index))
    }
  }

  return layers.flatMap((layer) => byLayer.get(layer)!)
}

/** Route one edge as an SVG path. */
function routeEdge(source: LaidOutNode, target: LaidOutNode): string {
  const sx = source.x + source.width / 2
  const tx = target.x + target.width / 2

  if (source.layer === target.layer) {
    // Same row: arc above the boxes rather than drawing a line straight through
    // whatever sits between them.
    const y = source.y - 14
    const lift = Math.min(34, 14 + Math.abs(tx - sx) / 6)
    return `M ${sx} ${source.y} C ${sx} ${y - lift}, ${tx} ${y - lift}, ${tx} ${target.y}`
  }

  const downward = target.layer > source.layer
  const sy = downward ? source.y + source.height : source.y
  const ty = downward ? target.y : target.y + target.height
  const midpoint = (sy + ty) / 2
  return `M ${sx} ${sy} C ${sx} ${midpoint}, ${tx} ${midpoint}, ${tx} ${ty}`
}

/** Line style per relationship, following UML convention where one exists. */
export function edgeStyle(relation: string): { dash: string; width: number; opacity: number } {
  switch (relation) {
    case 'extends':
    case 'generalization':
      return { dash: '', width: 1.8, opacity: 0.95 }
    case 'implements':
    case 'realization':
      return { dash: '6 4', width: 1.8, opacity: 0.95 }
    case 'association':
      return { dash: '2 3', width: 1.2, opacity: 0.6 }
    default:
      return { dash: '', width: 1.1, opacity: 0.45 }
  }
}
