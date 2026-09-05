import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import type { AnalysisResult, FileContent, TreeNode, WorkspaceStats } from '../lib/types'
import type { TreeEntry } from '../lib/tree'
import { formatBytes, statusStyle } from '../lib/theme'
import { CodeViewer } from './CodeViewer'
import { FileTree } from './FileTree'
import { useToast } from './Toast'
import { Banner, Button, Dialog, EmptyState, IconButton, Spinner, StatusChip } from './ui'

/** Browse and edit the project's code, beside what the diagram says about it.
 *
 * Three panes. The tree on the left is a real tree. The middle is the file,
 * with line numbers and colour. The right says what the diagram expected of the
 * class you are looking at and what the code actually has — which is the whole
 * point of the tool, and previously lived on a different screen entirely.
 */

type PendingAction =
  | { kind: 'delete'; entry: TreeEntry }
  | { kind: 'rename'; entry: TreeEntry; value: string }
  | { kind: 'create'; type: 'file' | 'folder'; value: string }
  | { kind: 'clear' }
  | { kind: 'discard'; next: () => void }

export function CodePanel({
  projectName,
  result,
  onChanged,
  onExplain,
  explanation,
}: {
  projectName: string
  result: AnalysisResult | null
  onChanged: () => void
  onExplain: (path: string) => void
  explanation: { path: string; text: string } | null
}) {
  const toast = useToast()
  const [tree, setTree] = useState<TreeNode[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const [open, setOpen] = useState<FileContent | null>(null)
  const [draft, setDraft] = useState('')
  const [editable, setEditable] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pending, setPending] = useState<PendingAction | null>(null)

  const [treeWidth, setTreeWidth] = useState(252)
  const [detailWidth, setDetailWidth] = useState(288)
  // Three panes need room. Below this the code pane is squeezed to a
  // column too narrow to read a line of Java in, so the detail pane starts
  // closed and stays one click away.
  const [detailOpen, setDetailOpen] = useState(() => window.innerWidth >= 1280)
  const dragging = useRef<'tree' | 'detail' | null>(null)

  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const archiveInput = useRef<HTMLInputElement>(null)

  const dirty = open !== null && draft !== open.content

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.tree(projectName)
      setTree(response.tree)
      setStats(response.stats)
      setError('')
    } catch (caught) {
      setError(errorMessage(caught, 'Could not list the project files.'))
    } finally {
      setLoading(false)
    }
  }, [projectName])

  useEffect(() => {
    setOpen(null)
    setDraft('')
    void refresh()
  }, [projectName, refresh])

  // --- what the diagram says about each file ---------------------------------

  /** Worst status wins, so a file containing one unimplemented class is not
   *  reported as matching because its other three classes do. */
  const statusByFile = useMemo(() => {
    const rank: Record<string, number> = {
      missing: 5,
      partial: 4,
      undocumented: 3,
      model_inferred: 2,
      conforming: 1,
    }
    const worst: Record<string, string> = {}
    for (const node of result?.graph_data.nodes ?? []) {
      const file = node.source_file
      if (!file || node.status === 'not_applicable') continue
      const current = worst[file]
      if (!current || (rank[node.status] ?? 0) > (rank[current] ?? 0)) worst[file] = node.status
    }
    return worst
  }, [result])

  const classesInFile = useMemo(() => {
    if (!open || !result) return []
    return result.graph_data.nodes.filter(
      (node) =>
        node.source_file === open.path &&
        (node.kind === 'class' || node.kind === 'interface'),
    )
  }, [open, result])

  /** Member-level differences for the classes in the open file. */
  const differencesInFile = useMemo(() => {
    if (!result) return []
    const names = new Set(classesInFile.map((node) => node.label))
    return result.difference.element_differences.filter((entry) => names.has(entry.element_name))
  }, [result, classesInFile])

  // --- opening and saving ----------------------------------------------------

  const openFile = useCallback(
    async (path: string, canEdit: boolean) => {
      const load = async () => {
        try {
          const content = await api.readFile(projectName, path)
          setOpen(content)
          setDraft(content.content)
          setEditable(canEdit)
        } catch (caught) {
          toast.notify(errorMessage(caught), 'critical')
        }
      }
      if (!canEdit) {
        toast.notify(`${path} is binary or too large to open here.`, 'warning')
        return
      }
      if (dirty) {
        setPending({ kind: 'discard', next: () => void load() })
        return
      }
      await load()
    },
    [projectName, dirty, toast],
  )

  async function save() {
    if (!open) return
    setSaving(true)
    try {
      await api.saveFile(projectName, open.path, draft)
      setOpen({ ...open, content: draft })
      toast.notify(`Saved ${open.path}.`, 'good')
      await refresh()
      onChanged()
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Could not save.'), 'critical')
    } finally {
      setSaving(false)
    }
  }

  // --- destructive actions, all through one dialog ---------------------------

  async function runPending() {
    if (!pending) return
    try {
      if (pending.kind === 'discard') {
        const next = pending.next
        setPending(null)
        next()
        return
      }
      if (pending.kind === 'delete') {
        await api.deleteFile(projectName, pending.entry.path)
        if (open?.path === pending.entry.path) {
          setOpen(null)
          setDraft('')
        }
        toast.notify(`Deleted ${pending.entry.path}.`, 'good')
      }
      if (pending.kind === 'rename') {
        const destination = pending.value.trim()
        if (!destination || destination === pending.entry.path) {
          setPending(null)
          return
        }
        await api.moveFile(projectName, pending.entry.path, destination)
        if (open?.path === pending.entry.path) {
          setOpen(null)
          setDraft('')
        }
        toast.notify(`Moved to ${destination}.`, 'good')
      }
      if (pending.kind === 'create') {
        const path = pending.value.trim()
        if (!path) {
          setPending(null)
          return
        }
        if (pending.type === 'folder') {
          await api.createFolder(projectName, path)
        } else {
          await api.createFile(projectName, path, '')
          const content = await api.readFile(projectName, path)
          setOpen(content)
          setDraft(content.content)
          setEditable(true)
        }
        toast.notify(`Created ${path}.`, 'good')
      }
      if (pending.kind === 'clear') {
        await api.clearSource(projectName)
        setOpen(null)
        setDraft('')
        toast.notify('Project files cleared.', 'good')
      }
      setPending(null)
      await refresh()
      onChanged()
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
      setPending(null)
    }
  }

  // --- uploads ---------------------------------------------------------------

  async function uploadFiles(event: ChangeEvent<HTMLInputElement>, mode: 'files' | 'folder') {
    const selected = Array.from(event.target.files ?? [])
    if (selected.length === 0) return
    setBusy(mode)
    try {
      // `webkitRelativePath` carries each file's position inside the chosen
      // folder; without it a folder upload flattens to a pile of names.
      const paths = selected.map((file) => {
        const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath
        if (mode === 'folder' && relative) {
          const parts = relative.split('/')
          return parts.length > 1 ? parts.slice(1).join('/') : relative
        }
        return file.name
      })
      const uploaded = await api.uploadBatch(projectName, selected, paths)
      await refresh()
      onChanged()
      if (uploaded.rejected.length > 0) {
        toast.notify(
          `Uploaded ${uploaded.written.length}; skipped ${uploaded.rejected.length} (${uploaded.rejected[0].reason}).`,
          'warning',
        )
      } else {
        toast.notify(`Uploaded ${uploaded.written.length} file(s).`, 'good')
      }
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Upload failed.'), 'critical')
    } finally {
      setBusy('')
      event.target.value = ''
    }
  }

  async function uploadArchive(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy('archive')
    try {
      const uploaded = await api.uploadSource(projectName, file)
      await refresh()
      onChanged()
      const rejected = uploaded?.extracted?.rejected ?? []
      toast.notify(
        rejected.length > 0
          ? `Extracted the archive; ${rejected.length} unsafe entry/entries were skipped.`
          : `Extracted ${file.name}.`,
        rejected.length > 0 ? 'warning' : 'good',
      )
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Upload failed.'), 'critical')
    } finally {
      setBusy('')
      event.target.value = ''
    }
  }

  async function download() {
    try {
      const blob = await api.downloadExport(projectName)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${projectName.replace(/\s+/g, '_')}-source.zip`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Export failed.'), 'critical')
    }
  }

  // --- pane resizing ---------------------------------------------------------

  useEffect(() => {
    function onMove(event: MouseEvent) {
      if (!dragging.current) return
      event.preventDefault()
      if (dragging.current === 'tree') {
        setTreeWidth(Math.max(180, Math.min(520, event.clientX - 240)))
      } else {
        setDetailWidth(Math.max(220, Math.min(560, window.innerWidth - event.clientX)))
      }
    }
    function onUp() {
      dragging.current = null
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  function startDrag(which: 'tree' | 'detail') {
    dragging.current = which
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const dialogCopy = describe(pending)

  return (
    <div className="flex h-full min-h-0 flex-col">
      {error && (
        <div className="p-3">
          <Banner tone="critical" onDismiss={() => setError('')}>
            {error}
          </Banner>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* --- pane 1: the tree --- */}
        <div
          className="flex shrink-0 flex-col border-r border-hairline bg-surface"
          style={{ width: treeWidth }}
        >
          {loading ? (
            <p className="flex items-center gap-2 p-4 text-xs text-muted">
              <Spinner /> Loading files…
            </p>
          ) : (
            <FileTree
              // Remount per project so the tree re-applies its default open
              // folders instead of carrying the previous project's state over.
              key={projectName}
              nodes={tree}
              selectedPath={open?.path ?? null}
              statusByFile={statusByFile}
              onOpenFile={openFile}
              onRename={(entry) => setPending({ kind: 'rename', entry, value: entry.path })}
              onDelete={(entry) => setPending({ kind: 'delete', entry })}
              onExplain={onExplain}
            />
          )}

          <div className="shrink-0 border-t border-hairline p-2">
            <div className="mb-1.5 flex flex-wrap gap-1">
              <Button size="sm" variant="subtle" onClick={() => setPending({ kind: 'create', type: 'file', value: '' })}>
                New file
              </Button>
              <Button size="sm" variant="subtle" onClick={() => setPending({ kind: 'create', type: 'folder', value: '' })}>
                New folder
              </Button>
            </div>
            <div className="mb-1.5 flex flex-wrap gap-1">
              <Button size="sm" variant="subtle" loading={busy === 'folder'} onClick={() => folderInput.current?.click()}>
                Upload folder
              </Button>
              <Button size="sm" variant="subtle" loading={busy === 'files'} onClick={() => fileInput.current?.click()}>
                Files
              </Button>
              <Button size="sm" variant="subtle" loading={busy === 'archive'} onClick={() => archiveInput.current?.click()}>
                .zip
              </Button>
            </div>
            {stats && (
              <p className="flex items-center justify-between text-[11px] text-muted">
                <span className="tabular-nums">
                  {stats.files} files · {stats.directories} folders · {formatBytes(stats.bytes)}
                </span>
                <span className="flex gap-1">
                  <IconButton label="Export as .zip" onClick={download}>
                    <span className="text-[10px]">⭳</span>
                  </IconButton>
                  {stats.files > 0 && (
                    <IconButton
                      label="Remove every file"
                      onClick={() => setPending({ kind: 'clear' })}
                      className="hover:text-critical"
                    >
                      <span className="text-[10px]">✕</span>
                    </IconButton>
                  )}
                </span>
              </p>
            )}
          </div>
        </div>

        <Divider onMouseDown={() => startDrag('tree')} label="Resize the file tree" />

        {/* --- pane 2: the file --- */}
        <div className="flex min-w-0 flex-1 flex-col">
          <CodeViewer
            path={open?.path ?? null}
            content={draft}
            editable={editable}
            dirty={dirty}
            saving={saving}
            onChange={setDraft}
            onSave={save}
            onClose={() =>
              dirty
                ? setPending({
                    kind: 'discard',
                    next: () => {
                      setOpen(null)
                      setDraft('')
                    },
                  })
                : (setOpen(null), setDraft(''))
            }
          />
        </div>

        {/* --- pane 3: what the diagram says --- */}
        {detailOpen ? (
          <>
            <Divider onMouseDown={() => startDrag('detail')} label="Resize the detail panel" />
            <aside
              className="flex shrink-0 flex-col overflow-y-auto border-l border-hairline bg-surface"
              style={{ width: detailWidth }}
            >
              <header className="flex shrink-0 items-center justify-between gap-2 border-b border-hairline px-3 py-2">
                <h3 className="text-xs font-semibold text-ink">Against the diagram</h3>
                <IconButton label="Hide this panel" onClick={() => setDetailOpen(false)}>
                  <span className="text-[10px]">→</span>
                </IconButton>
              </header>

              <div className="min-h-0 flex-1 space-y-3 p-3">
                {!result ? (
                  <EmptyState title="Not checked yet">
                    Run a check and this panel will show, for the open file, what your diagram
                    expects and what the code actually has.
                  </EmptyState>
                ) : !open ? (
                  <p className="text-xs text-muted">Open a file to see how it compares.</p>
                ) : classesInFile.length === 0 ? (
                  <p className="text-xs text-muted">
                    No classes from this file appear in the comparison. It may be supporting code,
                    or it may not have parsed — check the Results screen.
                  </p>
                ) : (
                  classesInFile.map((node) => {
                    const style = statusStyle(node.status)
                    const difference = differencesInFile.find(
                      (entry) => entry.element_name === node.label,
                    )
                    return (
                      <div key={node.id} className="rounded-lg border border-hairline p-2.5">
                        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-1.5">
                          <span className="truncate font-mono text-xs font-medium text-ink">
                            {node.label}
                          </span>
                          <StatusChip status={node.status} size="sm" />
                        </div>
                        <p className="text-[11px] leading-snug text-muted">{style.description}</p>

                        {difference && (
                          <dl className="mt-2 space-y-1.5 text-[11px]">
                            <MemberList
                              label="In the diagram, not in the code"
                              items={[
                                ...difference.missing_methods.map((name) => `${name}()`),
                                ...difference.missing_attributes,
                              ]}
                              tone="var(--critical)"
                            />
                            <MemberList
                              label="In the code, not in the diagram"
                              items={[
                                ...difference.extra_methods.map((name) => `${name}()`),
                                ...difference.extra_attributes,
                              ]}
                              tone="var(--serious)"
                            />
                          </dl>
                        )}
                      </div>
                    )
                  })
                )}

                {open && (
                  <div>
                    <Button size="sm" variant="subtle" onClick={() => onExplain(open.path)}>
                      Explain this file
                    </Button>
                    {explanation?.path === open.path && (
                      <p className="mt-2 rounded-lg border border-hairline bg-surface-2 p-2.5 text-[11px] leading-relaxed text-ink-2">
                        {explanation.text}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </aside>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setDetailOpen(true)}
            className="shrink-0 border-l border-hairline bg-surface px-1.5 text-[10px] text-muted transition hover:bg-surface-2 hover:text-ink"
            title="Show what the diagram says"
          >
            ←
          </button>
        )}
      </div>

      {/* Hidden pickers. `webkitdirectory` is how a browser offers a folder. */}
      <input
        ref={folderInput}
        type="file"
        multiple
        // @ts-expect-error non-standard but universally supported directory picker
        webkitdirectory=""
        directory=""
        className="hidden"
        onChange={(event) => uploadFiles(event, 'folder')}
      />
      <input ref={fileInput} type="file" multiple className="hidden" onChange={(event) => uploadFiles(event, 'files')} />
      <input ref={archiveInput} type="file" accept=".zip" className="hidden" onChange={uploadArchive} />

      <Dialog
        open={pending !== null}
        title={dialogCopy.title}
        description={dialogCopy.description}
        confirmLabel={dialogCopy.confirm}
        danger={dialogCopy.danger}
        input={
          pending && (pending.kind === 'rename' || pending.kind === 'create')
            ? {
                label: dialogCopy.inputLabel ?? 'Path',
                value: pending.value,
                placeholder: pending.kind === 'create' && pending.type === 'folder'
                  ? 'src/main/java/com/example/services'
                  : 'src/main/java/com/example/OrderService.java',
                onChange: (value) => setPending({ ...pending, value }),
              }
            : undefined
        }
        onConfirm={runPending}
        onCancel={() => setPending(null)}
      />
    </div>
  )
}

function MemberList({ label, items, tone }: { label: string; items: string[]; tone: string }) {
  if (items.length === 0) return null
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 flex flex-wrap gap-1">
        {items.map((item) => (
          <span
            key={item}
            className="rounded border px-1 py-px font-mono text-[10px]"
            style={{ borderColor: tone, color: tone }}
          >
            {item}
          </span>
        ))}
      </dd>
    </div>
  )
}

function Divider({ onMouseDown, label }: { onMouseDown: () => void; label: string }) {
  return (
    <div
      role="separator"
      aria-label={label}
      title={label}
      onMouseDown={onMouseDown}
      className="w-1 shrink-0 cursor-col-resize bg-transparent transition hover:bg-series-1/40"
    />
  )
}

function describe(pending: PendingAction | null): {
  title: string
  description: string
  confirm: string
  danger: boolean
  inputLabel?: string
} {
  if (!pending) return { title: '', description: '', confirm: 'Confirm', danger: false }
  switch (pending.kind) {
    case 'delete':
      return {
        title: `Delete ${pending.entry.name}?`,
        description:
          pending.entry.type === 'tree'
            ? `This removes the folder “${pending.entry.path}” and all ${pending.entry.fileCount} file(s) inside it. Analysis history is kept.`
            : `This removes “${pending.entry.path}”. Analysis history is kept.`,
        confirm: 'Delete',
        danger: true,
      }
    case 'rename':
      return {
        title: `Move or rename ${pending.entry.name}`,
        description: 'Give the full path from the project root. Folders in it are created as needed.',
        confirm: 'Move',
        danger: false,
        inputLabel: 'New path',
      }
    case 'create':
      return {
        title: pending.type === 'file' ? 'New file' : 'New folder',
        description:
          pending.type === 'file'
            ? 'The file is created empty and opened for editing.'
            : 'Folders in the path are created as needed.',
        confirm: 'Create',
        danger: false,
        inputLabel: 'Path',
      }
    case 'clear':
      return {
        title: 'Remove every file?',
        description:
          'This empties the project of source code. Your diagram and the analysis history are kept.',
        confirm: 'Remove all files',
        danger: true,
      }
    case 'discard':
      return {
        title: 'Discard unsaved changes?',
        description: 'You have edits in the open file that have not been saved.',
        confirm: 'Discard',
        danger: true,
      }
  }
}
