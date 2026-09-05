import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  allFolderPaths,
  ancestorsOf,
  buildTree,
  countFiles,
  defaultOpenFolders,
  filterTree,
  languageOf,
} from '../lib/tree'
import type { TreeEntry } from '../lib/tree'
import { formatBytes, statusStyle } from '../lib/theme'
import type { TreeNode } from '../lib/types'
import { IconButton, Input } from './ui'

/** The project's files, as an actual tree.
 *
 * Every folder opens and closes, the depth is drawn with guide lines rather
 * than implied by padding, and the whole thing is one roving-tabindex listbox
 * so it can be driven from the keyboard: up and down move, right opens a
 * folder or steps into it, left closes it or steps out, Enter opens a file.
 */

const LANGUAGE_TINT: Record<string, string> = {
  java: 'var(--series-2)',
  python: 'var(--series-1)',
  typescript: 'var(--series-1)',
  javascript: 'var(--warning)',
  csharp: 'var(--proposed)',
  go: 'var(--series-1)',
  ruby: 'var(--critical)',
  php: 'var(--proposed)',
  kotlin: 'var(--serious)',
  diagram: 'var(--good)',
}

function FileGlyph({ path }: { path: string }) {
  const language = languageOf(path)
  const tint = LANGUAGE_TINT[language] ?? 'var(--muted)'
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border text-[8px] font-bold uppercase"
      style={{ borderColor: tint, color: tint }}
    >
      {language === 'diagram' ? '◈' : language.slice(0, 1)}
    </span>
  )
}

interface RowProps {
  entry: TreeEntry
  open: Set<string>
  selectedPath: string | null
  focusedPath: string | null
  statusByFile: Record<string, string>
  onToggle: (path: string) => void
  onSelect: (entry: TreeEntry) => void
  onRename: (entry: TreeEntry) => void
  onDelete: (entry: TreeEntry) => void
  onExplain: (path: string) => void
  registerRow: (path: string, element: HTMLDivElement | null) => void
}

function Row(props: RowProps) {
  const {
    entry,
    open,
    selectedPath,
    focusedPath,
    statusByFile,
    onToggle,
    onSelect,
    onRename,
    onDelete,
    onExplain,
    registerRow,
  } = props

  const isFolder = entry.type === 'tree'
  const isOpen = open.has(entry.path)
  const isSelected = selectedPath === entry.path
  const status = statusByFile[entry.path]
  const style = status ? statusStyle(status) : null

  return (
    <>
      <div
        ref={(element) => registerRow(entry.path, element)}
        role="treeitem"
        aria-expanded={isFolder ? isOpen : undefined}
        aria-selected={isSelected}
        aria-level={entry.depth + 1}
        tabIndex={focusedPath === entry.path ? 0 : -1}
        onClick={() => (isFolder ? onToggle(entry.path) : onSelect(entry))}
        className={`group relative flex cursor-pointer items-center gap-1.5 rounded py-[3px] pr-1.5 text-xs transition ${
          isSelected
            ? 'bg-series-1/12 font-medium text-ink'
            : 'text-ink-2 hover:bg-surface-2'
        }`}
        style={{ paddingLeft: `${6 + entry.depth * 14}px` }}
      >
        {/* Indent guides: one hairline per ancestor level, so depth is visible
            instead of merely implied by how far the text starts. */}
        {Array.from({ length: entry.depth }, (_, level) => (
          <span
            key={level}
            aria-hidden="true"
            className="pointer-events-none absolute top-0 bottom-0 w-px bg-hairline"
            style={{ left: `${12 + level * 14}px` }}
          />
        ))}

        {isFolder ? (
          <span
            aria-hidden="true"
            className={`inline-block w-3 shrink-0 text-[9px] text-muted transition-transform duration-150 ${
              isOpen ? 'rotate-90' : ''
            }`}
          >
            ▶
          </span>
        ) : (
          <span aria-hidden="true" className="inline-block w-3 shrink-0" />
        )}

        {isFolder ? (
          <span aria-hidden="true" className="shrink-0 text-[11px] text-muted">
            {isOpen ? '▽' : '▷'}
          </span>
        ) : (
          <FileGlyph path={entry.path} />
        )}

        <span className="min-w-0 flex-1 truncate" title={entry.path}>
          {entry.name}
          {isFolder && <span className="text-muted">/</span>}
        </span>

        {/* Conformance status of the classes declared in this file. Colour, a
            glyph and a tooltip carrying the word -- never colour alone. */}
        {style && (
          <span
            aria-label={style.label}
            title={`${style.label} — ${style.description}`}
            className="shrink-0 text-[9px] font-bold"
            style={{ color: style.color }}
          >
            {style.glyph}
          </span>
        )}

        {isFolder ? (
          <span className="shrink-0 pr-0.5 text-[10px] tabular-nums text-muted opacity-70 group-hover:hidden">
            {entry.fileCount}
          </span>
        ) : (
          <span className="hidden shrink-0 text-[10px] tabular-nums text-muted group-hover:hidden sm:inline">
            {entry.size !== null ? formatBytes(entry.size) : ''}
          </span>
        )}

        <span
          className="hidden shrink-0 items-center gap-0.5 group-hover:flex"
          onClick={(event) => event.stopPropagation()}
        >
          {!isFolder && (
            <IconButton label={`Explain ${entry.name}`} onClick={() => onExplain(entry.path)}>
              <span className="text-[10px]">?</span>
            </IconButton>
          )}
          <IconButton label={`Rename ${entry.name}`} onClick={() => onRename(entry)}>
            <span className="text-[10px]">✎</span>
          </IconButton>
          <IconButton
            label={`Delete ${entry.name}`}
            onClick={() => onDelete(entry)}
            className="hover:text-critical"
          >
            <span className="text-[10px]">✕</span>
          </IconButton>
        </span>
      </div>

      {isFolder && isOpen && entry.children.map((child) => (
        <Row key={child.path} {...props} entry={child} />
      ))}
    </>
  )
}

export function FileTree({
  nodes,
  selectedPath,
  statusByFile = {},
  onOpenFile,
  onRename,
  onDelete,
  onExplain,
}: {
  nodes: TreeNode[]
  selectedPath: string | null
  statusByFile?: Record<string, string>
  onOpenFile: (path: string, editable: boolean) => void
  onRename: (entry: TreeEntry) => void
  onDelete: (entry: TreeEntry) => void
  onExplain: (path: string) => void
}) {
  const [filter, setFilter] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [focusedPath, setFocusedPath] = useState<string | null>(null)
  const [initialised, setInitialised] = useState(false)
  const rowRefs = useRef(new Map<string, HTMLDivElement>())

  const full = useMemo(() => buildTree(nodes), [nodes])
  const totalFiles = useMemo(() => countFiles(full), [full])

  // Open a sensible set the first time a project's files arrive, but never
  // again -- re-applying it would slam shut folders the user opened by hand
  // every time the tree refreshed after a save.
  useEffect(() => {
    if (initialised || full.length === 0) return
    setOpen(new Set(defaultOpenFolders(full)))
    setInitialised(true)
  }, [full, initialised])

  const { entries: visible, expand } = useMemo(() => filterTree(full, filter), [full, filter])

  // While a filter is active every folder on the way to a match is forced open,
  // without disturbing what the user had open before they started typing.
  const effectiveOpen = useMemo(() => {
    if (!filter.trim()) return open
    return new Set([...open, ...expand])
  }, [open, expand, filter])

  // Reveal the selected file when it is opened from somewhere else, such as a
  // click on the design map.
  useEffect(() => {
    if (!selectedPath) return
    setOpen((current) => {
      const next = new Set(current)
      let changed = false
      for (const ancestor of ancestorsOf(selectedPath)) {
        if (!next.has(ancestor)) {
          next.add(ancestor)
          changed = true
        }
      }
      return changed ? next : current
    })
    setFocusedPath(selectedPath)
  }, [selectedPath])

  const toggle = useCallback((path: string) => {
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
    setFocusedPath(path)
  }, [])

  const registerRow = useCallback((path: string, element: HTMLDivElement | null) => {
    if (element) rowRefs.current.set(path, element)
    else rowRefs.current.delete(path)
  }, [])

  /** The rows actually on screen, in visual order — what the arrow keys walk. */
  const flattened = useMemo(() => {
    const rows: TreeEntry[] = []
    const walk = (list: TreeEntry[]) => {
      for (const entry of list) {
        rows.push(entry)
        if (entry.type === 'tree' && effectiveOpen.has(entry.path)) walk(entry.children)
      }
    }
    walk(visible)
    return rows
  }, [visible, effectiveOpen])

  function move(delta: number) {
    if (flattened.length === 0) return
    const index = flattened.findIndex((entry) => entry.path === focusedPath)
    const next = flattened[Math.max(0, Math.min(flattened.length - 1, index + delta))]
    if (!next) return
    setFocusedPath(next.path)
    rowRefs.current.get(next.path)?.scrollIntoView({ block: 'nearest' })
    rowRefs.current.get(next.path)?.focus()
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const current = flattened.find((entry) => entry.path === focusedPath)
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        move(1)
        break
      case 'ArrowUp':
        event.preventDefault()
        move(-1)
        break
      case 'ArrowRight':
        event.preventDefault()
        if (!current) return
        if (current.type === 'tree' && !effectiveOpen.has(current.path)) toggle(current.path)
        else move(1)
        break
      case 'ArrowLeft': {
        event.preventDefault()
        if (!current) return
        if (current.type === 'tree' && effectiveOpen.has(current.path)) {
          toggle(current.path)
          return
        }
        const parent = ancestorsOf(current.path).slice(-1)[0]
        if (parent) {
          setFocusedPath(parent)
          rowRefs.current.get(parent)?.focus()
        }
        break
      }
      case 'Enter':
      case ' ':
        event.preventDefault()
        if (!current) return
        if (current.type === 'tree') toggle(current.path)
        else onOpenFile(current.path, current.editable)
        break
      default:
        break
    }
  }

  const matched = countFiles(visible)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline p-2">
        <Input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Find a file…"
          aria-label="Filter files by name"
          className="py-1 text-xs"
        />
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted">
          <span className="tabular-nums">
            {filter.trim() ? `${matched} of ${totalFiles} files` : `${totalFiles} files`}
          </span>
          <span className="flex gap-1">
            <button
              type="button"
              onClick={() => setOpen(new Set(allFolderPaths(full)))}
              className="rounded px-1.5 py-0.5 transition hover:bg-surface-2 hover:text-ink"
            >
              Expand all
            </button>
            <button
              type="button"
              onClick={() => setOpen(new Set())}
              className="rounded px-1.5 py-0.5 transition hover:bg-surface-2 hover:text-ink"
            >
              Collapse all
            </button>
          </span>
        </div>
      </div>

      <div
        role="tree"
        aria-label="Project files"
        onKeyDown={onKeyDown}
        className="min-h-0 flex-1 overflow-y-auto p-1"
      >
        {visible.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-muted">
            {totalFiles === 0 ? 'No files yet.' : 'Nothing matches that filter.'}
          </p>
        ) : (
          visible.map((entry) => (
            <Row
              key={entry.path}
              entry={entry}
              open={effectiveOpen}
              selectedPath={selectedPath}
              focusedPath={focusedPath ?? flattened[0]?.path ?? null}
              statusByFile={statusByFile}
              onToggle={toggle}
              onSelect={(target) => {
                setFocusedPath(target.path)
                onOpenFile(target.path, target.editable)
              }}
              onRename={onRename}
              onDelete={onDelete}
              onExplain={onExplain}
              registerRow={registerRow}
            />
          ))
        )}
      </div>
    </div>
  )
}
