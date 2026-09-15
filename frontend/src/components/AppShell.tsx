import type { ReactNode } from 'react'
import type { ThemeChoice } from '../lib/theme'
import type { ProjectSummary } from '../lib/types'
import { ThemeToggle } from './ui'

export type Destination = 'projects' | 'statistics'
export type ProjectSection = 'results' | 'code' | 'map' | 'diagram' | 'history'

const PROJECT_SECTIONS: Array<{
  id: ProjectSection
  label: string
  hint: string
}> = [
  { id: 'results', label: 'Overview', hint: 'Structural score and differences' },
  { id: 'code', label: 'Code', hint: 'Browse and edit source files' },
  { id: 'map', label: 'Code map', hint: 'Explore the recovered architecture' },
  { id: 'diagram', label: 'Diagram', hint: 'Manage the StarUML model' },
  { id: 'history', label: 'Runs', hint: 'History, metrics, and research tools' },
]

function ProjectIcon() {
  return (
    <span aria-hidden="true" className="grid h-5 w-5 place-items-center rounded text-[11px] text-muted">
      ▧
    </span>
  )
}

export function AppShell({
  destination,
  onNavigate,
  projects,
  onOpenProject,
  openProject,
  projectSection,
  onProjectSection,
  onCloseProject,
  theme,
  onTheme,
  onSignOut,
  modelLabel,
  children,
}: {
  destination: Destination
  onNavigate: (destination: Destination) => void
  projects: ProjectSummary[]
  onOpenProject: (name: string) => void
  openProject: string | null
  projectSection: ProjectSection
  onProjectSection: (section: ProjectSection) => void
  onCloseProject: () => void
  theme: ThemeChoice
  onTheme: (choice: ThemeChoice) => void
  onSignOut: () => void
  modelLabel: string
  children: ReactNode
}) {
  const totalRuns = projects.reduce((sum, project) => sum + project.versions, 0)
  const totalFiles = projects.reduce((sum, project) => sum + project.file_count, 0)

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <header
        data-print-hide
        className="flex h-14 shrink-0 items-center gap-4 border-b border-hairline bg-surface/85 px-5 backdrop-blur-xl"
      >
        <button
          type="button"
          onClick={() => onNavigate('projects')}
          className="shrink-0 text-lg font-bold tracking-[-0.04em] text-ink"
          title="All projects"
        >
          CompX
        </button>

        <span className="h-5 w-px shrink-0 bg-hairline" aria-hidden="true" />

        <select
          aria-label="Current project"
          value={openProject ?? ''}
          onChange={(event) => {
            if (event.target.value) onOpenProject(event.target.value)
            else onCloseProject()
          }}
          className="w-40 shrink-0 rounded-full border border-hairline bg-surface/80 px-3 py-1.5 text-[11px] font-medium text-ink shadow-[var(--shadow-card)] focus:border-ink focus:outline-none"
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.name} value={project.name}>
              {project.name}
            </option>
          ))}
        </select>

        {openProject && destination === 'projects' ? (
          <nav className="flex min-w-0 flex-1 items-center justify-center gap-1 overflow-x-auto" aria-label="Project">
            {PROJECT_SECTIONS.map((section) => (
              <button
                key={section.id}
                type="button"
                onClick={() => onProjectSection(section.id)}
                aria-current={projectSection === section.id ? 'page' : undefined}
                title={section.hint}
                className={`shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-medium transition-all duration-200 ${
                  projectSection === section.id
                    ? 'border-ink bg-surface text-ink shadow-[var(--shadow-card)]'
                    : 'border-transparent text-muted hover:border-hairline hover:bg-surface/70 hover:text-ink-2'
                }`}
              >
                {section.label}
              </button>
            ))}
          </nav>
        ) : (
          <div className="flex-1" />
        )}

        {!openProject && (
          <button
            type="button"
            onClick={() => onNavigate('statistics')}
            className={`hidden rounded-md px-2.5 py-1.5 text-xs font-medium transition sm:block ${
              destination === 'statistics'
                ? 'bg-surface-2 text-ink'
                : 'text-muted hover:bg-surface-2 hover:text-ink'
            }`}
          >
            Statistics
          </button>
        )}

        <details className="group relative shrink-0">
          <summary
            className="grid h-7 w-7 cursor-pointer list-none place-items-center rounded text-muted transition hover:bg-surface-2 hover:text-ink"
            aria-label="Application settings"
            title="Application settings"
          >
            ⚙
          </summary>
          <div className="absolute right-0 top-10 z-40 w-64 rounded-lg border border-hairline bg-surface p-3 shadow-[var(--shadow-float)]">
            <p className="mb-2 text-[11px] leading-relaxed text-muted">{modelLabel}</p>
            <div className="flex items-center justify-between gap-3 border-t border-hairline pt-3">
              <ThemeToggle choice={theme} onChange={onTheme} />
              <button
                type="button"
                onClick={onSignOut}
                className="rounded-md px-2 py-1 text-xs text-muted transition hover:bg-surface-2 hover:text-critical"
              >
                Sign out
              </button>
            </div>
          </div>
        </details>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          data-print-hide
          className="hidden w-48 shrink-0 flex-col border-r border-hairline bg-surface/82 backdrop-blur-xl md:flex"
        >
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
            <div className="mb-2 flex items-center justify-between px-1">
              <h2 className="text-[11px] font-semibold uppercase tracking-wide text-muted">Projects</h2>
              <button
                type="button"
                onClick={() => onNavigate('projects')}
                className="rounded px-1.5 text-base leading-5 text-muted transition hover:bg-surface-2 hover:text-ink"
                aria-label="New project"
                title="New project"
              >
                +
              </button>
            </div>

            <nav className="space-y-0.5" aria-label="Projects">
              {projects.map((project) => {
                const active = openProject === project.name && destination === 'projects'
                return (
                  <button
                    key={project.name}
                    type="button"
                    onClick={() => onOpenProject(project.name)}
                    aria-current={active ? 'page' : undefined}
                    title={project.name}
                    className={`relative flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition ${
                      active
                        ? 'bg-series-1/10 font-medium text-ink'
                        : 'text-ink-2 hover:bg-surface-2 hover:text-ink'
                    }`}
                  >
                    {active && <span className="absolute inset-y-1 left-0 w-0.5 rounded bg-series-1" />}
                    <ProjectIcon />
                    <span className="min-w-0 flex-1 truncate">{project.name}</span>
                    {!project.has_uml && (
                      <span className="text-[10px] text-warning" title="Needs a diagram">!</span>
                    )}
                  </button>
                )
              })}
              {projects.length === 0 && (
                <p className="px-2 py-3 text-xs leading-relaxed text-muted">No projects yet.</p>
              )}
            </nav>

            <button
              type="button"
              onClick={() => onNavigate('projects')}
              className="mt-2 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted transition hover:bg-surface-2 hover:text-ink"
            >
              <span aria-hidden="true" className="grid h-5 w-5 place-items-center">+</span>
              New project
            </button>

            <div className="my-4 border-t border-hairline" />

            <button
              type="button"
              onClick={() => onNavigate('statistics')}
              className="mb-2 flex w-full items-center justify-between px-1 text-left"
            >
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Statistics</span>
              <span className="text-xs text-muted">›</span>
            </button>
            <dl className="space-y-2 px-1 text-xs">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">Comparison runs</dt>
                <dd className="font-medium tabular-nums text-ink-2">{totalRuns}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">Projects</dt>
                <dd className="font-medium tabular-nums text-ink-2">{projects.length}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">Source files</dt>
                <dd className="font-medium tabular-nums text-ink-2">{totalFiles.toLocaleString()}</dd>
              </div>
            </dl>
          </div>

          <div className="space-y-2.5 border-t border-hairline p-3">
            <p className="truncate text-[11px] leading-tight text-muted" title={modelLabel}>
              {modelLabel}
            </p>
            <div className="flex items-center justify-between gap-2">
              <ThemeToggle choice={theme} onChange={onTheme} />
              <button
                type="button"
                onClick={onSignOut}
                className="rounded-md px-2 py-1 text-xs text-muted transition hover:bg-surface-2 hover:text-critical"
              >
                Sign out
              </button>
            </div>
          </div>
        </aside>

        <main className="relative min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
