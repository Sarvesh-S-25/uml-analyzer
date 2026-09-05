import type { ReactNode } from 'react'

/** Shared chart chrome.
 *
 * Every colour here is a `var()` reference into the tokens defined once in
 * `index.css`, so a chart re-colours with the light/dark toggle and cannot
 * drift away from the rest of the app. The previous version duplicated the
 * status hex values in this file with a comment promising to keep them in step;
 * they had already fallen out of step.
 *
 * The colour policy itself is unchanged and was decided by running a separation
 * validator rather than by eye: the first three categorical slots clear the
 * colour-blindness and normal-vision floors pairwise, a fourth does not in any
 * ordering, so a chart distinguishing four things carries identity in **direct
 * labels**, not in a fourth hue.
 */

export const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)'] as const

export const STATUS = {
  good: 'var(--good)',
  warning: 'var(--warning)',
  serious: 'var(--serious)',
  critical: 'var(--critical)',
} as const

export const INK = {
  primary: 'var(--ink)',
  secondary: 'var(--ink-2)',
  muted: 'var(--muted)',
  grid: 'var(--grid)',
  axis: 'var(--axis)',
  surface: 'var(--surface)',
} as const

export function seriesColor(index: number): string {
  return SERIES[index] ?? INK.muted
}

/** A chart frame with a title, a caption, and a table-view slot.
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
        <div className="min-w-0">
          <h4 className="text-sm font-semibold text-ink">{title}</h4>
          {caption && (
            <figcaption className="mt-0.5 max-w-[74ch] text-xs leading-relaxed text-muted">
              {caption}
            </figcaption>
          )}
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

/** Attributes that can carry a colour, and therefore a `var()` reference. */
const COLOUR_ATTRIBUTES = ['fill', 'stroke', 'stop-color', 'flood-color'] as const

/** Replace every `var(--x)` in a detached SVG with the value being painted now.
 *
 * An exported file carries no stylesheet, so a `var()` reference in a `fill`
 * resolves to nothing and the shape renders black — on a black background, in
 * the dark theme. Resolving against the live element before serialising is what
 * makes a figure exported from either theme open correctly anywhere.
 */
function inlineComputedColors(clone: SVGSVGElement, live: SVGSVGElement) {
  const cloned = [clone, ...Array.from(clone.querySelectorAll('*'))]
  const original = [live, ...Array.from(live.querySelectorAll('*'))]

  cloned.forEach((element, index) => {
    const source = original[index]
    if (!source) return
    const computed = getComputedStyle(source)
    for (const attribute of COLOUR_ATTRIBUTES) {
      const value = element.getAttribute(attribute)
      if (!value || !value.includes('var(')) continue
      const resolved = computed.getPropertyValue(attribute).trim()
      if (resolved && resolved !== 'none') element.setAttribute(attribute, resolved)
    }
  })
}

/** Save an on-screen SVG chart as a vector file.
 *
 * A screenshot of a figure is a raster image that goes soft the moment the
 * publisher scales it; a vector file prints correctly at any size. Both the
 * paper figures and the design map route through this one function so they
 * behave identically and there is only one place for the background rule to be
 * wrong.
 */
export function downloadSvgElement(
  element: SVGSVGElement | null,
  filename: string,
  background = '#ffffff',
  resolveVariables = false,
) {
  if (!element) return
  const clone = element.cloneNode(true) as SVGSVGElement

  if (resolveVariables) inlineComputedColors(clone, element)

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
