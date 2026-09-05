import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import type { FileContent, TreeNode, WorkspaceStats } from '../lib/types'
import { useToast } from './Toast'
import { Banner, Button, Card, EmptyState, Input, Spinner } from './ui'

/** The virtual directory.
 *
 * This is the whole non-git workflow in one panel: upload a folder or an
 * archive, create and edit files in the browser, rename, delete, and export.
 * Nothing here touches GitHub, and the analysis pipeline reads the same
 * directory either way, so a project filled by hand behaves identically to one
 * imported from a repository.
 */
export function FileManager({
  projectName,
  onChanged,
  onExplain,
}: {
  projectName: string
  onChanged: () => void
  onExplain: (path: string) => void
}) {
  const toast = useToast()
  const [tree, setTree] = useState<TreeNode[]>([])
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')

  const [open, setOpen] = useState<FileContent | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const [newPath, setNewPath] = useState('')
  const [creating, setCreating] = useState<'file' | 'folder' | null>(null)

  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const archiveInput = useRef<HTMLInputElement>(null)

  const dirty = open !== null && draft !== open.content

  async function refresh() {
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
  }

  useEffect(() => {
    setOpen(null)
    setDraft('')
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectName])

  const visible = useMemo(() => {
    if (!filter.trim()) return tree
    const needle = filter.trim().toLowerCase()
    return tree.filter((node) => node.path.toLowerCase().includes(needle))
  }, [tree, filter])

  function confirmDiscard(): boolean {
    if (!dirty) return true
    return window.confirm('You have unsaved changes. Discard them?')
  }

  async function openFile(node: TreeNode) {
    if (!node.editable) {
      toast.notify(`${node.path} is binary or too large to edit here.`, 'warning')
      return
    }
    if (!confirmDiscard()) return
    try {
      const content = await api.readFile(projectName, node.path)
      setOpen(content)
      setDraft(content.content)
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

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

  async function create() {
    const path = newPath.trim()
    if (!path || !creating) return
    setBusy('create')
    try {
      if (creating === 'folder') {
        await api.createFolder(projectName, path)
      } else {
        await api.createFile(projectName, path, '')
        const content = await api.readFile(projectName, path)
        setOpen(content)
        setDraft(content.content)
      }
      setNewPath('')
      setCreating(null)
      await refresh()
      onChanged()
      toast.notify(`Created ${path}.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    } finally {
      setBusy('')
    }
  }

  async function remove(node: TreeNode) {
    const label = node.type === 'tree' ? 'folder and everything in it' : 'file'
    if (!window.confirm(`Delete the ${label} “${node.path}”?`)) return
    try {
      await api.deleteFile(projectName, node.path)
      if (open?.path === node.path) {
        setOpen(null)
        setDraft('')
      }
      await refresh()
      onChanged()
      toast.notify(`Deleted ${node.path}.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  async function rename(node: TreeNode) {
    const destination = window.prompt(`Move or rename “${node.path}” to:`, node.path)
    if (!destination || destination === node.path) return
    try {
      await api.moveFile(projectName, node.path, destination)
      if (open?.path === node.path) {
        setOpen(null)
        setDraft('')
      }
      await refresh()
      onChanged()
      toast.notify(`Moved to ${destination}.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  async function uploadFiles(event: ChangeEvent<HTMLInputElement>, mode: 'files' | 'folder') {
    const selected = Array.from(event.target.files ?? [])
    if (selected.length === 0) return

    setBusy(mode)
    try {
      // `webkitRelativePath` carries each file's position inside the chosen
      // folder; without it a folder upload would flatten to a pile of names.
      const paths = selected.map((file) => {
        const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath
        if (mode === 'folder' && relative) {
          const parts = relative.split('/')
          return parts.length > 1 ? parts.slice(1).join('/') : relative
        }
        return file.name
      })

      const result = await api.uploadBatch(projectName, selected, paths)
      await refresh()
      onChanged()

      if (result.rejected.length > 0) {
        toast.notify(
          `Uploaded ${result.written.length}; skipped ${result.rejected.length} (${result.rejected[0].reason}).`,
          'warning',
        )
      } else {
        toast.notify(`Uploaded ${result.written.length} file(s).`, 'good')
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
      const result = await api.uploadSource(projectName, file)
      await refresh()
      onChanged()
      const rejected = result?.extracted?.rejected ?? []
      if (rejected.length > 0) {
        toast.notify(
          `Extracted the archive; ${rejected.length} unsafe entry/entries were skipped.`,
          'warning',
        )
      } else {
        toast.notify(`Extracted ${file.name}.`, 'good')
      }
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

  async function clearAll() {
    if (!window.confirm('Remove every file from this project? Analysis history is kept.')) return
    try {
      await api.clearSource(projectName)
      setOpen(null)
      setDraft('')
      await refresh()
      onChanged()
      toast.notify('Project files cleared.', 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  return (
    <Card
      title="Project files"
      subtitle="Upload a folder, an archive, or write code directly here. No git required."
      actions={
        <>
          <Button variant="ghost" onClick={download} disabled={!stats?.files}>
            Export .zip
          </Button>
          <Button variant="ghost" onClick={refresh}>
            Refresh
          </Button>
        </>
      }
    >
      {error && (
        <div className="mb-3">
          <Banner tone="critical">{error}</Banner>
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <Button onClick={() => folderInput.current?.click()} loading={busy === 'folder'}>
          Upload folder
        </Button>
        <Button onClick={() => fileInput.current?.click()} loading={busy === 'files'}>
          Upload files
        </Button>
        <Button onClick={() => archiveInput.current?.click()} loading={busy === 'archive'}>
          Upload .zip
        </Button>
        <Button variant="ghost" onClick={() => setCreating('file')}>
          New file
        </Button>
        <Button variant="ghost" onClick={() => setCreating('folder')}>
          New folder
        </Button>
        {!!stats?.files && (
          <Button variant="danger" onClick={clearAll}>
            Clear all
          </Button>
        )}
      </div>

      {/* `webkitdirectory` is how a browser offers a whole-folder picker. */}
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
      <input
        ref={fileInput}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => uploadFiles(event, 'files')}
      />
      <input
        ref={archiveInput}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={uploadArchive}
      />

      {creating && (
        <div className="mb-4 rounded-lg border border-hairline bg-surface-2 p-3">
          <p className="mb-2 text-xs text-muted">
            {creating === 'file'
              ? 'Path for the new file, e.g. app/services/order_service.py'
              : 'Path for the new folder, e.g. app/services'}
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              autoFocus
              value={newPath}
              onChange={(event) => setNewPath(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && create()}
              placeholder={creating === 'file' ? 'app/service.py' : 'app/services'}
              className="flex-1 min-w-48"
            />
            <Button variant="primary" onClick={create} loading={busy === 'create'}>
              Create
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setCreating(null)
                setNewPath('')
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter files…"
            className="mb-2"
          />
          <div className="max-h-96 overflow-y-auto rounded-lg border border-hairline">
            {loading ? (
              <p className="flex items-center gap-2 p-4 text-xs text-muted">
                <Spinner /> Loading…
              </p>
            ) : visible.length === 0 ? (
              <div className="p-4">
                <EmptyState title={tree.length === 0 ? 'No files yet' : 'Nothing matches'}>
                  {tree.length === 0
                    ? 'Upload a folder or create a file to get started.'
                    : 'Try a different filter.'}
                </EmptyState>
              </div>
            ) : (
              <ul className="divide-y divide-hairline/60">
                {visible.map((node) => (
                  <li
                    key={node.path}
                    className={`group flex items-center gap-2 px-3 py-1.5 text-xs ${
                      open?.path === node.path ? 'bg-surface-2' : ''
                    }`}
                    style={{ paddingLeft: `${12 + node.path.split('/').length * 8}px` }}
                  >
                    <span aria-hidden="true" className="text-muted">
                      {node.type === 'tree' ? '▸' : '·'}
                    </span>
                    <button
                      onClick={() => node.type === 'blob' && openFile(node)}
                      disabled={node.type === 'tree'}
                      className={`min-w-0 flex-1 truncate text-left ${
                        node.type === 'tree'
                          ? 'text-muted'
                          : 'text-ink-2 hover:text-series-1 cursor-pointer'
                      }`}
                      title={node.path}
                    >
                      {node.path.split('/').slice(-1)[0]}
                      {node.type === 'tree' ? '/' : ''}
                    </button>
                    <span className="shrink-0 tabular-nums text-muted opacity-0 transition group-hover:opacity-100">
                      {node.size !== null ? `${Math.max(1, Math.round(node.size / 100) / 10)}k` : ''}
                    </span>
                    {node.type === 'blob' && (
                      <button
                        onClick={() => onExplain(node.path)}
                        title="Explain this file"
                        className="shrink-0 text-muted opacity-0 transition hover:text-series-1 group-hover:opacity-100"
                      >
                        ?
                      </button>
                    )}
                    <button
                      onClick={() => rename(node)}
                      title="Move or rename"
                      className="shrink-0 text-muted opacity-0 transition hover:text-ink group-hover:opacity-100"
                    >
                      ↔
                    </button>
                    <button
                      onClick={() => remove(node)}
                      title="Delete"
                      className="shrink-0 text-muted opacity-0 transition hover:text-critical group-hover:opacity-100"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {stats && (
            <p className="mt-2 text-xs text-muted">
              {stats.files} file{stats.files === 1 ? '' : 's'} · {stats.directories} folder
              {stats.directories === 1 ? '' : 's'} · {Math.round(stats.bytes / 1024)} KB
            </p>
          )}
        </div>

        <div>
          {open ? (
            <div className="flex h-full flex-col">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="min-w-0 flex-1 truncate text-xs text-ink-2" title={open.path}>
                  {open.path}
                  {dirty && <span className="ml-2 text-warning">● unsaved</span>}
                </span>
                <div className="flex gap-2">
                  <Button variant="primary" onClick={save} loading={saving} disabled={!dirty}>
                    Save
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      if (confirmDiscard()) {
                        setOpen(null)
                        setDraft('')
                      }
                    }}
                  >
                    Close
                  </Button>
                </div>
              </div>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                spellCheck={false}
                className="h-96 w-full resize-none rounded-lg border border-hairline bg-plane p-3 font-mono text-xs text-ink-2 focus:border-series-1 focus:outline-none"
              />
              <p className="mt-1 text-xs text-muted">
                Saving rewrites the file in place. The next analysis will see the change.
              </p>
            </div>
          ) : (
            <div className="flex h-full items-center">
              <EmptyState title="No file open">
                Select a text file on the left to view and edit it here.
              </EmptyState>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
