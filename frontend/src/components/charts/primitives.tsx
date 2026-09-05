import type { ReactNode } from 'react'

/** Shared chart chrome.
 *
 * Colour policy, decided by running the palette validator rather than by eye:
 * the first three categorical slots clear the all-pairs colour-blindness and
 * normal-vision separation floors on this dark surface; a fourth does not, in
 * any ordering. So charts that distinguish four gates carry identity in
 * **direct labels**, not in a fourth hue, and colour is used only where two or
 * three series are genuinely being compared.
 */
export const SERIES = ['#3987e5', '#d95926', '#199e70'] as const

/** Mirrors the status tokens in index.css. SVG cannot read a CSS custom
 *  property through an attribute, so these are duplicated here and must be kept
 *  in step -- there is no third place either can drift to. */
export const STATUS = {
  good: '#2fb344',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#e05252',
} as const

export const INK = {
  primary: '#f7f7f5',
  secondary: '#d3d2ca',
  muted: '#94918a',
  grid: '#302f2d',
  axis: '#3a3a38',
  surface: '#1c1c1b',
} as const

export function seriesColor(index: number): string {
  return SERIES[index] ?? INK.muted
}

/** A chart frame with a title, an optional caption, and a table-view slot.
 *
 * The table alternative is not decoration: it is the accessibility fallback for
 * every figure here, and it is also what a reader copies numbers out of.
 */
export function Figure({
  title,
  caption,
  children,
  actions,
  tableView,
}: {
  title: string
  caption?: ReactNode
  children: ReactNode
  actions?: ReactNode
  tableView?: ReactNode
}) {
  return (
    <figure className="m-0">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-sm font-medium text-ink">{title}</h4>
          {caption && <figcaption className="mt-0.5 text-xs text-muted">{caption}</figcaption>}
        </div>
        {actions}
      </div>
      <div className="rounded-lg border border-hairline bg-surface p-3">{children}</div>
      {tableView && <div className="mt-2">{tableView}</div>}
    </figure>
  )
}

export function Legend({
  items,
}: {
  items: Array<{ label: string; color: string; glyph?: string }>
}) {
  if (items.length < 2) return null
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5 text-xs text-ink-2">
          <span
            aria-hidden="true"
            className="inline-flex h-2.5 w-2.5 items-center justify-center rounded-sm"
            style={{ background: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

export function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex h-40 items-center justify-center rounded border border-dashed border-hairline px-4 text-center text-xs text-muted">
      {message}
    </div>
  )
}

/** Nice axis ticks: 1, 2, 2.5 or 5 times a power of ten. */
export function niceTicks(max: number, count = 5): number[] {
  if (!isFinite(max) || max <= 0) return [0, 1]
  const rough = max / count
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)))
  const normalised = rough / magnitude
  const step =
    (normalised >= 5 ? 5 : normalised >= 2.5 ? 2.5 : normalised >= 2 ? 2 : 1) * magnitude
  const ticks: number[] = []
  for (let value = 0; value <= max + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(10)))
  }
  return ticks
}

export function formatNumber(value: number | null | undefined, places = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (Math.abs(value) >= 1000) return Math.round(value).toLocaleString()
  return Number(value.toFixed(places)).toString()
}

export function formatPercent(value: number | null | undefined, places = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(places)}%`
}

/** Save an on-screen SVG chart as a vector file.
 *
 * A screenshot of a figure is a raster image that goes soft the moment the
 * publisher scales it; a vector file prints correctly at any size. Both paper
 * figures and the design graph route through this one function so they behave
 * identically and there is only one place for the background-colour rule to be
 * wrong.
 */
export function downloadSvgElement(element: SVGSVGElement | null, filename: string, background = INK.surface) {
  if (!element) return
  const clone = element.cloneNode(true) as SVGSVGElement

  // Whatever pan/zoom the viewer applied belongs to the screen, not the file.
  const viewport = clone.querySelector('[data-viewport]')
  viewport?.setAttribute('transform', '')

  const box = element.viewBox.baseVal
  if (box && box.width) {
    clone.setAttribute('width', String(box.width))
    clone.setAttribute('height', String(box.height))
  }
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

  // Without an explicit background the file renders black in some viewers and
  // white in others, and the text disappears in one of them.
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  rect.setAttribute('width', '100%')
  rect.setAttribute('height', '100%')
  rect.setAttribute('fill', background)
  clone.insertBefore(rect, clone.firstChild)

  const blob = new Blob([new XMLSerializer().serializeToString(clone)], {
    type: 'image/svg+xml;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename.endsWith('.svg') ? filename : `${filename}.svg`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
