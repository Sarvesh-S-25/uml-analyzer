import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../lib/api'
import { formatRelative } from '../lib/theme'
import type { ProjectSummary, PublicConfig, Repo } from '../lib/types'
import { useToast } from './Toast'
import {
  Banner,
  Button,
  Card,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  Input,
  ScoreBar,
  SegmentedControl,
  Select,
  StatTile,
} from './ui'

type Source = 'empty' | 'zip' | 'github'

/** The home screen: one card per codebase, each saying at a glance whether it
 *  still matches its diagram and when that was last checked. */
export function ProjectsPage({
  config,
  projects,
  githubConnected,
  repos,
  onRefresh,
  onOpen,
}: {
  config: PublicConfig | null
  projects: ProjectSummary[]
  githubConnected: boolean
  repos: Repo[]
  onRefresh: () => Promise<void>
  onOpen: (name: string) => void
}) {
  const toast = useToast()
  const [source, setSource] = useState<Source>('empty')
  const [name, setName] = useState('')
  const [repo, setRepo] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const summary = useMemo(() => {
    const withDiagram = projects.filter((project) => project.has_uml).length
    const checked = projects.filter((project) => project.last_analysed)
    const latest = checked
      .map((project) => project.last_analysed as string)
      .sort()
      .slice(-1)[0]
    return { withDiagram, latest, checked: checked.length }
  }, [projects])

  function connectGithub() {
    if (!config?.github_client_id) return
    const redirect = encodeURIComponent(window.location.origin + window.location.pathname)
    window.location.href =
      `https://github.com/login/oauth/authorize?client_id=${config.github_client_id}` +
      `&redirect_uri=${redirect}&scope=repo`
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
      const created = await api.createProject(targetName, source === 'github' ? repo : null)
      // The server may normalise the name, so use what it actually created.
      const actualName = created.project_name
      if (source === 'zip' && file) await api.uploadSource(actualName, file)

      setName('')
      setRepo('')
      setFile(null)
      setCreating(false)
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
    try {
      await api.deleteProject(projectName)
      await onRefresh()
      toast.notify(`Deleted “${projectName}”.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught), 'critical')
    } finally {
      setConfirmDelete(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-4 lg:p-6">
      <header className="relative mb-6 overflow-hidden rounded-2xl border border-hairline bg-surface/62 px-6 py-10 text-center shadow-[var(--shadow-card)] backdrop-blur-md lg:py-14">
        <div className="pointer-events-none absolute left-6 top-6 h-8 w-8 opacity-35 [background-image:radial-gradient(circle,var(--ink)_1px,transparent_1.2px)] [background-size:7px_7px]" />
        <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-muted">
          Structural conformance workspace
        </p>
        <h1 className="mx-auto mt-3 max-w-4xl text-[clamp(2.35rem,5.6vw,5.5rem)] font-semibold uppercase leading-[0.92] tracking-[-0.065em] text-ink">
          Code meets design
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-muted">
          Compare a codebase with its StarUML model, inspect structural drift, and keep every
          result grounded in parser evidence.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {githubConnected ? (
            <Button
              variant="ghost"
              onClick={async () => {
                try {
                  await api.githubDisconnect()
                  await onRefresh()
                  toast.notify('GitHub disconnected.', 'good')
                } catch (caught) {
                  toast.notify(errorMessage(caught), 'critical')
                }
              }}
            >
              ✓ GitHub connected
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
          <Button variant="primary" onClick={() => setCreating((value) => !value)}>
            New project
          </Button>
        </div>
      </header>

      {projects.length > 0 && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <StatTile
            label="Projects"
            value={projects.length}
            detail={`${summary.checked} checked at least once`}
          />
          <StatTile
            label="With a diagram"
            value={`${summary.withDiagram} of ${projects.length}`}
            detail="A project with no diagram can only be parsed, not compared"
          />
          <StatTile
            label="Last checked"
            value={summary.latest ? formatRelative(summary.latest) : 'never'}
            detail="Across all projects"
          />
        </div>
      )}

      {creating && (
        <Card title="New project" className="mb-4">
          <div className="mb-4">
            <SegmentedControl
              options={[
                { value: 'empty', label: 'Start empty' },
                { value: 'zip', label: 'From a .zip' },
                { value: 'github', label: 'From GitHub', disabled: !githubConnected },
              ]}
              value={source}
              onChange={(value) => {
                setSource(value)
                setError('')
              }}
            />
          </div>

          {error && (
            <div className="mb-4">
              <Banner tone="critical">{error}</Banner>
            </div>
          )}

          <form onSubmit={createProject} className="space-y-4">
            {source === 'empty' && (
              <Field label="Project name" hint="Letters, digits, spaces, hyphens and underscores.">
                <Input
                  autoFocus
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Order Service"
                />
              </Field>
            )}

            {source === 'github' && (
              <Field label="Repository" hint="The default branch is imported.">
                <Select value={repo} onChange={(event) => setRepo(event.target.value)}>
                  <option value="">Select a repository…</option>
                  {repos.map((option) => (
                    <option key={option.full_name} value={option.full_name}>
                      {option.full_name}
                      {option.private ? ' (private)' : ''}
                    </option>
                  ))}
                </Select>
              </Field>
            )}

            {source === 'zip' && (
              <Field label="Archive" hint="The folder structure inside the archive is preserved.">
                <input
                  type="file"
                  accept=".zip"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:text-ink"
                />
              </Field>
            )}

            <div className="flex gap-2">
              <Button type="submit" variant="primary" loading={busy}>
                Create project
              </Button>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {!config?.github_configured && !creating && projects.length === 0 && (
        <div className="mb-6">
          <Banner tone="info" title="GitHub import is not configured — everything else works">
            Create a project and upload a folder, a .zip, or individual files; you can also write
            code directly in the app. Repository import needs{' '}
            <code className="text-ink">GITHUB_CLIENT_ID</code> and{' '}
            <code className="text-ink">GITHUB_CLIENT_SECRET</code> in the backend{' '}
            <code className="text-ink">.env</code>.
          </Banner>
        </div>
      )}

      {projects.length === 0 ? (
        <EmptyState
          title="No projects yet"
          icon="▤"
          action={
            <Button variant="primary" onClick={() => setCreating(true)}>
              Create your first project
            </Button>
          }
        >
          A project holds your code and the diagram it should match. Start empty and upload a
          folder, or import a repository.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {projects.map((project) => (
            <div
              key={project.name}
              className="group rounded-md border border-hairline bg-surface p-3 shadow-[var(--shadow-card)] transition hover:border-series-1/60"
            >
              <div className="flex items-start justify-between gap-3">
                <button onClick={() => onOpen(project.name)} className="min-w-0 flex-1 text-left">
                  <div className="truncate text-sm font-semibold text-ink">{project.name}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {project.file_count} file{project.file_count === 1 ? '' : 's'} ·{' '}
                    {project.latest_version
                      ? `version ${project.latest_version}`
                      : 'never checked'}
                    {project.last_analysed ? ` · ${formatRelative(project.last_analysed)}` : ''}
                  </div>
                </button>
                <IconButton
                  label={`Delete ${project.name}`}
                  onClick={() => setConfirmDelete(project.name)}
                  className="opacity-0 transition group-hover:opacity-100 hover:text-critical"
                >
                  ✕
                </IconButton>
              </div>

              <div className="mt-3">
                {!project.has_uml ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium"
                      style={{
                        borderColor: 'var(--warning)',
                        background: 'var(--warning-wash)',
                        color: 'var(--warning)',
                      }}
                    >
                      <span aria-hidden="true" className="font-bold">
                        !
                      </span>
                      Needs a diagram
                    </span>
                    <button
                      onClick={() => onOpen(project.name)}
                      className="text-xs text-series-1 underline-offset-2 hover:underline"
                    >
                      Upload one
                    </button>
                  </div>
                ) : project.latest_score === null ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted">Diagram ready — not checked yet.</span>
                    <button
                      onClick={() => onOpen(project.name)}
                      className="text-xs text-series-1 underline-offset-2 hover:underline"
                    >
                      Check now
                    </button>
                  </div>
                ) : (
                  <ScoreBar value={project.latest_score} />
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog
        open={confirmDelete !== null}
        title={`Delete “${confirmDelete}”?`}
        description="This removes the project, its files, its diagram and every recorded check. It cannot be undone."
        confirmLabel="Delete project"
        danger
        onConfirm={() => confirmDelete && deleteProject(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  )
}
