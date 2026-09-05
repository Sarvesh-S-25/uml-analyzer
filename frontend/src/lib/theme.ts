/** Conformance status encoding, and the light/dark theme controller.
 *
 * Every status colour here is a `var()` reference rather than a hex literal, so
 * one attribute on <html> re-themes the SVG figures along with the rest of the
 * app. The previous version hard-coded hex in three places -- here, in
 * `charts/primitives.tsx`, and inline in several components -- which is how the
 * "good" banner and the "Conforming" badge ended up being two different greens.
 * There is now exactly one definition, in `index.css`.
 *
 * The four status colours are validated for >=3:1 against their own theme's
 * surface. Red and green sit close together under deuteranopia, so every status
 * is *also* carried by a glyph and a written label -- in the legend, on the node
 * itself, and in the filter row. Colour never carries the meaning alone.
 */

export interface StatusStyle {
  /** A `var()` reference. Valid in CSS and in SVG presentation attributes. */
  color: string
  /** Tinted background for chips and highlighted rows. */
  wash: string
  glyph: string
  label: string
  description: string
}

export const STATUS_STYLES: Record<string, StatusStyle> = {
  conforming: {
    color: 'var(--good)',
    wash: 'var(--good-wash)',
    glyph: '✓',
    label: 'Matches',
    description: 'In the diagram and in the code, with the same members.',
  },
  partial: {
    color: 'var(--warning)',
    wash: 'var(--warning-wash)',
    glyph: '!',
    label: 'Partly matches',
    description: 'In both, but some members differ.',
  },
  undocumented: {
    color: 'var(--serious)',
    wash: 'var(--serious-wash)',
    glyph: '+',
    label: 'Not in the diagram',
    description: 'Written in the code but never drawn.',
  },
  missing: {
    color: 'var(--critical)',
    wash: 'var(--critical-wash)',
    glyph: '✗',
    label: 'Not built',
    description: 'Drawn in the diagram but not implemented.',
  },
  model_inferred: {
    color: 'var(--proposed)',
    wash: 'var(--proposed-wash)',
    glyph: '~',
    label: 'Model-proposed',
    description: 'Suggested by the language model; the code reader did not find it.',
  },
  not_applicable: {
    color: 'var(--neutral)',
    wash: 'var(--surface-2)',
    glyph: '·',
    label: 'Supporting code',
    description: 'Modules, functions and methods — not compared against the diagram.',
  },
}

export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLES[status] ?? STATUS_STYLES.not_applicable
}

/** Node radius by declaration kind — a second, colour-independent channel. */
export function nodeRadius(kind: string): number {
  switch (kind) {
    case 'module':
      return 7
    case 'class':
    case 'interface':
      return 5.5
    default:
      return 3.5
  }
}

/** Chart series slots. Also `var()` references, for the same reason. */
export const SERIES = {
  reanalysed: 'var(--series-1)',
  cached: 'var(--series-3)',
  slot1: 'var(--series-1)',
  slot2: 'var(--series-2)',
  slot3: 'var(--series-3)',
  slot4: 'var(--series-4)',
}

// --- theme control -----------------------------------------------------------

export type ThemeChoice = 'light' | 'dark' | 'system'

const THEME_KEY = 'compx.theme'

export function readThemeChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    // A browser with site data blocked still gets a working app, just not a
    // remembered preference.
  }
  return 'system'
}

export function applyThemeChoice(choice: ThemeChoice) {
  const root = document.documentElement
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
  try {
    localStorage.setItem(THEME_KEY, choice)
  } catch {
    // Not being able to remember it is not a reason to fail to apply it.
  }
}

/** What the user is actually looking at right now, with `system` resolved. */
export function resolvedTheme(choice: ThemeChoice): 'light' | 'dark' {
  if (choice !== 'system') return choice
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** Resolve a `var(--x)` reference to the hex the browser is currently painting.
 *
 * Needed only when a colour has to leave the page: an exported SVG carries no
 * stylesheet, so a `var()` reference in a `fill` attribute resolves to nothing
 * and the shape renders black-on-black. Everything on screen uses the reference
 * directly and themes for free.
 */
export function resolveColor(value: string, element?: Element): string {
  const match = /^var\((--[\w-]+)\)$/.exec(value.trim())
  if (!match) return value
  const scope = element ?? document.documentElement
  const resolved = getComputedStyle(scope).getPropertyValue(match[1]).trim()
  return resolved || value
}

// --- formatting --------------------------------------------------------------

export function formatMs(ms: number): string {
  if (!isFinite(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function formatNumber(value: number): string {
  return value.toLocaleString()
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** "3 minutes ago" — for a timestamp the reader only needs to place roughly. */
export function formatRelative(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  return formatDate(iso)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
