import type { ReactNode } from 'react'
import type { ThemeChoice } from '../lib/theme'
import { ThemeToggle } from './ui'

/** The frame every screen sits in.
 *
 * The previous version had three unlabelled tabs inside a project and reached
 * the statistics through a button in the corner of an unrelated screen, so
 * there was no way to see how the parts related. This puts the whole app in one
 * always-visible list: where you are, what else there is, and — when a project
 * is open — what that project contains.
 */

export type Destination = 'projects' | 'statistics'
export type ProjectSection = 'code' | 'diagram' | 'results' | 'history'

const DESTINATIONS: Array<{ id: Destination; label: string; hint: string; glyph: string }> = [
  { id: 'projects', label: 'Projects', glyph: '▤', hint: 'Your codebases and their diagrams' },
  { id: 'statistics', label: 'Statistics', glyph: '▦', hint: 'The numbers for the paper' },
]

export const PROJECT_SECTIONS: Array<{
  id: ProjectSection
  label: string
  hint: string
  glyph: string
}> = [
  { id: 'code', label: 'Code', glyph: '◧', hint: 'Browse and edit the source files' },
  { id: 'diagram', label: 'Diagram', glyph: '◈', hint: 'The StarUML file it is checked against' },
  { id: 'results', label: 'Results', glyph: '◉', hint: 'What matches and what does not' },
  { id: 'history', label: 'History', glyph: '◔', hint: 'Previous checks and what they cost' },
]

function NavButton({
  active,
  glyph,
  label,
  hint,
  onClick,
  indented = false,
  badge,
}: {
  active: boolean
  glyph: string
  label: string
  hint?: string
  onClick: () => void
  indented?: boolean
  badge?: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      title={hint}
      className={`relative flex w-full items-center gap-2.5 rounded-lg py-1.5 pr-2 text-left transition ${
        indented ? 'pl-6' : 'pl-2.5'
      } ${active ? 'bg-series-1/12 text-ink' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'}`}
    >
      {active && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-series-1"
        />
      )}
      <span aria-hidden="true" className="shrink-0 text-sm text-muted">
        {glyph}
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-sm ${active ? 'font-medium' : ''}`}>{label}</span>
        {hint && !indented && (
          <span className="block truncate text-[11px] leading-tight text-muted">{hint}</span>
        )}
      </span>
      {badge}
    </button>
  )
}

export function AppShell({
  destination,
  onNavigate,
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
  return (
    <div className="flex h-full">
      <aside
        data-print-hide
        className="flex w-60 shrink-0 flex-col border-r border-hairline bg-surface"
      >
        <div className="border-b border-hairline px-4 py-3.5">
          <div className="text-lg font-semibold tracking-tight text-ink">CompX</div>
          <p className="mt-0.5 text-[11px] leading-tight text-muted">
            Does your code still match your diagram?
          </p>
        </div>

        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2" aria-label="Main">
          {DESTINATIONS.map((entry) => (
            <NavButton
              key={entry.id}
              active={destination === entry.id && !(entry.id === 'projects' && openProject)}
              glyph={entry.glyph}
              label={entry.label}
              hint={entry.hint}
              onClick={() => onNavigate(entry.id)}
            />
          ))}

          {openProject && (
            <div className="pt-3">
              <div className="flex items-center justify-between gap-1 px-2.5 pb-1">
                <span
                  className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-wide text-muted"
                  title={openProject}
                >
                  {openProject}
                </span>
                <button
                  type="button"
                  onClick={onCloseProject}
                  aria-label="Close this project"
                  title="Close this project"
                  className="shrink-0 rounded px-1 text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  ✕
                </button>
              </div>
              {PROJECT_SECTIONS.map((section) => (
                <NavButton
                  key={section.id}
                  indented
                  active={destination === 'projects' && projectSection === section.id}
                  glyph={section.glyph}
                  label={section.label}
                  hint={section.hint}
                  onClick={() => onProjectSection(section.id)}
                />
              ))}
            </div>
          )}
        </nav>

        <div className="space-y-2 border-t border-hairline p-3">
          <ThemeToggle choice={theme} onChange={onTheme} />
          <p className="text-[11px] leading-tight text-muted">{modelLabel}</p>
          <button
            type="button"
            onClick={onSignOut}
            className="w-full rounded-lg px-2 py-1 text-left text-xs text-muted transition hover:bg-surface-2 hover:text-critical"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
