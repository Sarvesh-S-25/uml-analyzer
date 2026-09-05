import { useEffect, useMemo, useRef, useState } from 'react'
import { TOKEN_COLORS, tokenizeLines } from '../lib/highlight'
import { languageOf } from '../lib/tree'
import { statusStyle } from '../lib/theme'
import { Button, EmptyState } from './ui'

/** A file, readable.
 *
 * Replaces a bare `<textarea>` that had no line numbers, no colour, and no way
 * to relate what you were reading back to the diagram.
 *
 * Editing keeps the highlighting: a transparent `<textarea>` sits exactly on
 * top of the coloured text and the two scroll together, so the caret and the
 * selection are the browser's real ones while the colour underneath is ours.
 * The two layers must agree on font, size, line height and padding to the pixel
 * or the caret drifts away from the glyphs, which is why those values are set
 * once in `LAYER` below and shared rather than written twice.
 */

const LAYER = 'font-mono text-xs leading-[1.55] tracking-normal'
const PAD_Y = 10
const LINE_HEIGHT = 1.55

export interface LineMark {
  line: number
  status: string
  note: string
}

export function CodeViewer({
  path,
  content,
  editable,
  dirty,
  saving,
  marks = [],
  onChange,
  onSave,
  onClose,
}: {
  path: string | null
  content: string
  editable: boolean
  dirty: boolean
  saving: boolean
  /** Lines the comparison had something to say about. */
  marks?: LineMark[]
  onChange: (value: string) => void
  onSave: () => void
  onClose: () => void
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [caret, setCaret] = useState({ line: 1, column: 1 })

  const language = path ? languageOf(path) : 'text'
  const lines = useMemo(() => tokenizeLines(content, language), [content, language])
  const markByLine = useMemo(() => {
    const map = new Map<number, LineMark>()
    for (const mark of marks) map.set(mark.line, mark)
    return map
  }, [marks])

  // Ctrl/Cmd+S saves, because in an editor that is what it does and the button
  // being the only way is a papercut on every single edit.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        if (!editable || !dirty) return
        event.preventDefault()
        onSave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editable, dirty, onSave])

  function updateCaret() {
    const element = textareaRef.current
    if (!element) return
    const upto = element.value.slice(0, element.selectionStart)
    const rows = upto.split('\n')
    setCaret({ line: rows.length, column: rows[rows.length - 1].length + 1 })
  }

  if (!path) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <EmptyState title="No file open" icon="◧">
          Pick a file in the tree on the left. Its classes are matched against your diagram, and
          anything the comparison flagged is marked in the margin.
        </EmptyState>
      </div>
    )
  }

  const gutterWidth = `${Math.max(2, String(lines.length).length)}ch`

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-hairline px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs text-ink-2" title={path}>
            {path}
          </span>
          {dirty && (
            <span className="shrink-0 text-[11px] font-medium text-warning">● unsaved</span>
          )}
          {!editable && (
            <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted">
              read-only
            </span>
          )}
        </div>
        <div className="flex shrink-0 gap-1.5">
          {editable && (
            <Button size="sm" variant="primary" onClick={onSave} loading={saving} disabled={!dirty}>
              Save
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </header>

      <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-auto bg-plane">
        <div className="relative flex min-h-full w-max min-w-full">
          {/* Gutter: line numbers, plus a status bar for any line the
              comparison flagged. Sticky so it survives horizontal scrolling. */}
          <div
            aria-hidden="true"
            className={`sticky left-0 z-10 shrink-0 select-none border-r border-hairline bg-surface-2 pr-2 pl-3 text-right text-muted ${LAYER}`}
            style={{ paddingTop: PAD_Y, paddingBottom: PAD_Y }}
          >
            {lines.map((_, index) => {
              const mark = markByLine.get(index + 1)
              const style = mark ? statusStyle(mark.status) : null
              return (
                <div key={index} className="relative" style={{ width: gutterWidth }}>
                  {style && (
                    <span
                      className="absolute -left-3 top-0 bottom-0 w-[3px] rounded-full"
                      style={{ background: style.color }}
                      title={`${style.label} — ${mark!.note}`}
                    />
                  )}
                  {index + 1}
                </div>
              )
            })}
          </div>

          <div className="relative min-w-0 flex-1">
            {/* Coloured text. aria-hidden because the textarea above carries
                the real, selectable content for assistive tech. */}
            <pre
              aria-hidden={editable}
              className={`m-0 whitespace-pre px-3 ${LAYER}`}
              style={{ paddingTop: PAD_Y, paddingBottom: PAD_Y }}
            >
              {lines.map((tokens, index) => {
                const mark = markByLine.get(index + 1)
                return (
                  <div
                    key={index}
                    style={
                      mark
                        ? { background: statusStyle(mark.status).wash }
                        : undefined
                    }
                  >
                    {tokens.length === 0 ? (
                      '\n'
                    ) : (
                      tokens.map((token, position) => (
                        <span key={position} style={{ color: TOKEN_COLORS[token.kind] }}>
                          {token.text}
                        </span>
                      ))
                    )}
                  </div>
                )
              })}
            </pre>

            {editable && (
              <textarea
                ref={textareaRef}
                value={content}
                spellCheck={false}
                onChange={(event) => onChange(event.target.value)}
                onKeyUp={updateCaret}
                onClick={updateCaret}
                onKeyDown={(event) => {
                  // Tab indents instead of leaving the editor, which is what
                  // anyone editing code expects.
                  if (event.key !== 'Tab') return
                  event.preventDefault()
                  const element = event.currentTarget
                  const { selectionStart, selectionEnd, value } = element
                  const next = `${value.slice(0, selectionStart)}    ${value.slice(selectionEnd)}`
                  onChange(next)
                  requestAnimationFrame(() => {
                    element.selectionStart = element.selectionEnd = selectionStart + 4
                  })
                }}
                aria-label={`Contents of ${path}`}
                className={`absolute inset-0 h-full w-full resize-none overflow-hidden whitespace-pre border-0 bg-transparent px-3 text-transparent caret-ink outline-none ${LAYER}`}
                style={{
                  paddingTop: PAD_Y,
                  paddingBottom: PAD_Y,
                  lineHeight: LINE_HEIGHT,
                }}
              />
            )}
          </div>
        </div>
      </div>

      <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-hairline px-3 py-1 text-[11px] text-muted">
        <span className="flex gap-3">
          <span className="tabular-nums">
            Ln {caret.line}, Col {caret.column}
          </span>
          <span className="tabular-nums">{lines.length} lines</span>
          <span className="capitalize">{language}</span>
        </span>
        {marks.length > 0 && (
          <span className="flex flex-wrap items-center gap-2.5">
            <span>Margin marks:</span>
            {[...new Set(marks.map((mark) => mark.status))].map((status) => {
              const style = statusStyle(status)
              return (
                <span key={status} className="inline-flex items-center gap-1">
                  <span
                    aria-hidden="true"
                    className="inline-block h-2.5 w-[3px] rounded-full"
                    style={{ background: style.color }}
                  />
                  <span style={{ color: style.color }}>{style.label}</span>
                </span>
              )
            })}
          </span>
        )}
      </footer>
    </div>
  )
}
