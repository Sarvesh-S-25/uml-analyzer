/** Client-side CSV generation and download.
 *
 * Every table on the statistics page carries its own download button, so a
 * reader can take exactly the table they are looking at without fetching the
 * whole bundle. The server also serves a complete zip; this is the convenience
 * path, not a replacement for it.
 */

function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  // Quote when the value contains a delimiter, a quote, or a newline; double
  // any embedded quotes. This is RFC 4180, and it is what stops a note
  // containing a comma from silently shifting every later column.
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

/** Accepts typed interfaces as well as plain records.
 *
 * `Record<string, unknown>` would reject every declared interface here, because
 * an interface has no index signature. Widening to `object` and reading through
 * one cast keeps the call sites clean without forcing `as any` at each one.
 */
export function toCsv(rows: readonly object[], columns?: string[]): string {
  if (rows.length === 0) return ''
  const records = rows as ReadonlyArray<Record<string, unknown>>
  const fields = columns ?? Array.from(new Set(records.flatMap((row) => Object.keys(row))))
  const lines = [fields.map(escapeCell).join(',')]
  for (const row of records) {
    lines.push(fields.map((field) => escapeCell(row[field])).join(','))
  }
  return lines.join('\n')
}

export function downloadText(filename: string, content: string, mime = 'text/csv;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  downloadBlob(filename, blob)
}

export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  // Revoke on the next tick: revoking synchronously can cancel the download in
  // some browsers before it has started.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadCsv(filename: string, rows: readonly object[], columns?: string[]) {
  downloadText(filename, toCsv(rows, columns))
}
