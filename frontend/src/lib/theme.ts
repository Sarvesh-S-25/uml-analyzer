/** Conformance status encoding.
 *
 * The four status colours are reserved and validated for >=3:1 contrast on the
 * dark chart surface. Red/green sit close together under deuteranopia, so every
 * status is *also* carried by a glyph and a written label -- in the legend, on
 * the node itself, and in the filter row. Colour never carries the meaning
 * alone.
 */
export interface StatusStyle {
  color: string
  glyph: string
  label: string
  description: string
}

export const STATUS_STYLES: Record<string, StatusStyle> = {
  conforming: {
    color: '#2fb344',
    glyph: '✓',
    label: 'Conforming',
    description: 'Present in both the diagram and the code, with matching members.',
  },
  partial: {
    color: '#fab219',
    glyph: '!',
    label: 'Partial',
    description: 'Present in both, but members differ.',
  },
  undocumented: {
    color: '#ec835a',
    glyph: '+',
    label: 'Undocumented',
    description: 'In the code but absent from the diagram.',
  },
  missing: {
    color: '#e05252',
    glyph: '✗',
    label: 'Missing',
    description: 'In the diagram but not implemented.',
  },
  model_inferred: {
    color: '#9085e9',
    glyph: '~',
    label: 'Model-inferred',
    description: 'Proposed by the language model; not found by the parser.',
  },
  not_applicable: {
    color: '#94918a',
    glyph: '·',
    label: 'Structural',
    description: 'Modules, functions and methods -- not directly compared to the diagram.',
  },
}

export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLES[status] ?? STATUS_STYLES.not_applicable
}

/** Node radius by declaration kind -- a second, colour-independent channel. */
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

export const SERIES = {
  reanalysed: '#3987e5',
  cached: '#199e70',
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function formatNumber(value: number): string {
  return value.toLocaleString()
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
