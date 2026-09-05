import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import type { ProjectSummary, PublicConfig, Repo } from '../lib/types'
import { formatDate } from '../lib/theme'
import { useToast } from './Toast'
import { Banner, Button, Card, EmptyState, Field, Input } from './ui'

type Source = 'name' | 'github' | 'zip'

export function Dashboard({
  config,
  projects,
  githubConnected,
  repos,
  onRefresh,
  onOpen,
  onSignOut,
  onOpenStatistics,
}: {
  config: PublicConfig | null
  projects: ProjectSummary[]
  githubConnected: boolean
  repos: Repo[]
  onRefresh: () => Promise<void>
  onOpen: (name: string) => void
  onSignOut: () => void
  onOpenStatistics: () => void
}) {
  const toast = useToast()
  const [source, setSource] = useState<Source>('name')
  const [name, setName] = useState('')
  const [repo, setRepo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function connectGithub() {
    if (!config?.github_client_id) return
    const redirect = encodeURIComponent(window.location.origin + window.location.pathname)
    window.location.href =
      `https://github.com/login/oauth/authorize?client_id=${config.github_client_id}` +
      `&redirect_uri=${redirect}&scope=repo`
  }

  async function disconnectGithub() {
    try {
      await api.githubDisconnect()
      await onRefresh()
      toast.notify('GitHub disconnected.', 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  function derivedName(): string {
    if (source === 'zip' && file) {
      return file.name.replace(/\.[^/.]+$/, '').replace(/[^a-zA-Z0-9 _-]/g, '_')
    }
    if (source === 'github' && repo) {
      return (repo.split('/').pop() ?? '').replace(/[^a-zA-Z0-9 _-]/g, '_')
    }
    return name.trim()
  }

  async function createProject(event: FormEvent) {
    event.preventDefault()
    setError('')
    const targetName = derivedName()
    if (!targetName) {
      setError('Give the project a name, pick a repository, or choose a .zip archive.')
      return
    }

    setBusy(true)
    try {
      const created = await api.createProject(
        targetName,
        source === 'github' ? repo : null,
      )
      // The server may normalise the name, so use what it actually created.
      const actualName = created.project_name

      if (source === 'zip' && file) {
        await api.uploadSource(actualName, file)
      }

      setName('')
      setRepo('')
      setFile(null)
      await onRefresh()
      toast.notify(`Created “${actualName}”.`, 'good')
      onOpen(actualName)
    } catch (caught) {
      setError(errorMessage(caught, 'Could not create the project.'))
    } finally {
      setBusy(false)
    }
  }

  async function deleteProject(projectName: string) {
    if (!window.confirm(`Delete “${projectName}” and all of its analysis history?`)) return
    try {
      await api.deleteProject(projectName)
      await onRefresh()
      toast.notify(`Deleted “${projectName}”.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <h1 className="text-xl font-semibold text-ink">Polyglot Conformance Platform</h1>
          <p className="mt-1 text-sm text-muted">
            {config?.llm_enabled
              ? `Incremental analysis · ${config.llm_model}`
              : 'Incremental analysis · deterministic mode (no model configured)'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onOpenStatistics}>Statistics</Button>
          {githubConnected ? (
            <Button variant="ghost" onClick={disconnectGithub}>
              ✓ GitHub connected — disconnect
            </Button>
          ) : (
            <Button
              onClick={connectGithub}
              disabled={!config?.github_configured}
              title={
                config?.github_configured
                  ? undefined
                  : 'Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in the backend .env to enable this.'
              }
            >
              Connect GitHub
            </Button>
          )}
          <Button variant="danger" onClick={onSignOut}>
            Sign out
          </Button>
        </div>
      </header>

      {!config?.github_configured && (
        <div className="mb-6">
          <Banner tone="info" title="GitHub import is not configured — everything else works">
            The server has no GitHub OAuth credentials, so repository import is unavailable. Create
            a project below and upload a folder, a .zip, or individual files; you can also write
            code directly in the project. To enable repository import, set{' '}
            <code className="text-ink-2">GITHUB_CLIENT_ID</code> and{' '}
            <code className="text-ink-2">GITHUB_CLIENT_SECRET</code> in the backend{' '}
            <code className="text-ink-2">.env</code>.
          </Banner>
        </div>
      )}

      <Card
        title="New project"
        subtitle="Start empty and add files by hand, upload an archive, or import a repository. Only the last one needs GitHub."
        className="mb-8"
      >
        <div className="mb-4 flex flex-wrap gap-1 rounded-lg border border-hairline p-1">
          {([
            ['name', 'Empty project'],
            ['zip', 'From .zip archive'],
            ['github', 'From GitHub'],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setSource(value)
                setError('')
              }}
              disabled={value === 'github' && !githubConnected}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm transition disabled:opacity-40 ${
                source === value ? 'bg-surface-2 text-ink' : 'text-muted hover:text-ink-2'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {error && (
          <div className="mb-4">
            <Banner tone="critical">{error}</Banner>
          </div>
        )}

        <form onSubmit={createProject} className="space-y-4">
          {source === 'name' && (
            <Field label="Project name" hint="Letters, digits, spaces, hyphens and underscores.">
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Order Service"
              />
            </Field>
          )}

          {source === 'github' && (
            <Field label="Repository" hint="The default branch is imported.">
              <select
                value={repo}
                onChange={(event) => setRepo(event.target.value)}
                className="w-full rounded-lg border border-hairline bg-plane px-3 py-2 text-sm text-ink focus:border-series-1 focus:outline-none"
              >
                <option value="">Select a repository…</option>
                {repos.map((option) => (
                  <option key={option.full_name} value={option.full_name}>
                    {option.full_name}
                    {option.private ? ' (private)' : ''}
                  </option>
                ))}
              </select>
            </Field>
          )}

          {source === 'zip' && (
            <Field label="Archive" hint="The folder structure inside the archive is preserved.">
              <input
                type="file"
                accept=".zip"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:text-sm file:text-ink"
              />
            </Field>
          )}

          <Button type="submit" variant="primary" loading={busy}>
            Create project
          </Button>
        </form>
      </Card>

      <h2 className="mb-3 text-sm font-semibold text-ink">Projects</h2>
      {projects.length === 0 ? (
        <EmptyState title="No projects yet">
          Create one above to upload a StarUML diagram and its source code.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {projects.map((project) => (
            <div
              key={project.name}
              className="group rounded-xl border border-hairline bg-surface p-4 transition hover:border-series-1/50"
            >
              <div className="flex items-start justify-between gap-3">
                <button
                  onClick={() => onOpen(project.name)}
                  className="min-w-0 flex-1 text-left"
                >
                  <div className="truncate text-sm font-medium text-ink">{project.name}</div>
                  <div className="mt-1 text-xs text-muted">
                    {project.file_count} file{project.file_count === 1 ? '' : 's'}
                    {project.has_uml ? ' · diagram uploaded' : ' · no diagram'}
                  </div>
                  <div className="text-xs text-muted">
                    {project.latest_version
                      ? `v${project.latest_version} · ${project.versions} retained`
                      : 'Never analysed'}
                  </div>
                  {project.last_analysed && (
                    <div className="text-xs text-muted">{formatDate(project.last_analysed)}</div>
                  )}
                </button>
                <div className="flex shrink-0 items-center gap-2">
                  {project.latest_score !== null && (
                    <span className="text-sm tabular-nums text-ink-2">
                      {project.latest_score}%
                    </span>
                  )}
                  <button
                    onClick={() => deleteProject(project.name)}
                    aria-label={`Delete ${project.name}`}
                    className="text-muted opacity-0 transition group-hover:opacity-100 hover:text-critical"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
