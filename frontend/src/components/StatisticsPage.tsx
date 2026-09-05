import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, errorMessage } from '../lib/api'
import { downloadBlob, downloadCsv } from '../lib/csv'
import type {
  DeviationTable,
  GateTable,
  RecoveryHorizon,
  ProjectRow,
  ProjectTable,
  StatisticsReport,
  StudyTable,
} from '../lib/statsTypes'
import type { ProjectSummary } from '../lib/types'
import { BarChart } from './charts/BarChart'
import { ParetoChart } from './charts/ParetoChart'
import { DriftChart } from './charts/DriftChart'
import { Figure, STATUS, downloadSvgElement, formatNumber, formatPercent } from './charts/primitives'
import { useToast } from './Toast'
import { Badge, Banner, Button, Card, EmptyState, Spinner } from './ui'

/** Four tables, one test, two charts — each with a sentence saying what it means.
 *
 * The organising rule: **no number is shown without a sentence explaining it.**
 * Those sentences come from the backend, generated from the same numbers the
 * table displays, so they cannot drift out of step with the data or claim
 * something the data does not support.
 *
 * An earlier version of this page had eight tables, six figures and a dozen
 * statistical tests. It was correct and unreadable. This one is deliberately
 * small.
 */
export function StatisticsPage() {
  const toast = useToast()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [report, setReport] = useState<StatisticsReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState('')
  const [showGlossary, setShowGlossary] = useState(false)

  const load = useCallback(async (names: string[]) => {
    setLoading(true)
    setError('')
    try {
      setReport(await api.statistics(names))
    } catch (caught) {
      setError(errorMessage(caught, 'Could not compute statistics.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    api.projects().then(setProjects).catch(() => setProjects([]))
    void load([])
  }, [load])

  function toggleProject(name: string) {
    const next = selected.includes(name)
      ? selected.filter((entry) => entry !== name)
      : [...selected, name]
    setSelected(next)
    void load(next)
  }

  async function exportAs(format: 'zip' | 'csv' | 'latex') {
    setExporting(format)
    try {
      const blob = await api.downloadStatistics(selected, format)
      const extension = format === 'latex' ? 'tex' : format === 'csv' ? 'csv' : 'zip'
      downloadBlob(`conformance-statistics.${extension}`, blob)
      toast.notify(`Exported as ${extension.toUpperCase()}.`, 'good')
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Export failed.'), 'critical')
    } finally {
      setExporting('')
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <header className="mb-6 border-b border-hairline pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-ink">Statistics</h1>
            <p className="mt-1 text-sm text-muted">
              Four tables and three charts — everything the paper needs, and nothing else. Each
              one is followed by a sentence saying what it means.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => load(selected)} loading={loading}>
              Recompute
            </Button>
            <Button onClick={() => exportAs('zip')} loading={exporting === 'zip'}>
              All as CSV
            </Button>
            <Button variant="primary" onClick={() => exportAs('latex')} loading={exporting === 'latex'}>
              LaTeX for the paper
            </Button>
          </div>
        </div>

        {projects.length > 1 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">Showing:</span>
            <button
              onClick={() => {
                setSelected([])
                void load([])
              }}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                selected.length === 0
                  ? 'border-series-1 text-ink'
                  : 'border-hairline text-muted hover:text-ink-2'
              }`}
            >
              All projects
            </button>
            {projects.map((project) => (
              <button
                key={project.name}
                onClick={() => toggleProject(project.name)}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  selected.includes(project.name)
                    ? 'border-series-1 text-ink'
                    : 'border-hairline text-muted hover:text-ink-2'
                }`}
              >
                {project.name}
              </button>
            ))}
          </div>
        )}
      </header>

      {error && (
        <div className="mb-5">
          <Banner tone="critical">{error}</Banner>
        </div>
      )}

      {loading && !report && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Computing…
        </p>
      )}

      {report && !report.usable && (
        <div className="space-y-8">
          <EmptyState title="Nothing to show yet">{report.reason}</EmptyState>
          {/* Table 4 needs no analysis run at all -- `evaluate_deviations.py`
              is a self-contained controlled test -- so it has no reason to
              wait behind "no runs recorded yet" the way the corpus-derived
              tables above genuinely do. */}
          <DeviationSection deviations={report.deviations} />
        </div>
      )}

      {report?.usable && (
        <div className="space-y-8">
          {/* The one paragraph to read if you read nothing else. */}
          <div className="rounded-lg border border-series-1/40 bg-surface p-5">
            <h2 className="text-xs font-medium uppercase tracking-wide text-muted">
              The short version
            </h2>
            <p className="mt-2 text-base leading-relaxed text-ink">{report.headline}</p>
          </div>

          <GateExplainer />
          <StudySection study={report.study} />
          <GateSection gates={report.gates} charts={report.charts} />
          <ProjectSection projects={report.projects} />
          <DeviationSection deviations={report.deviations} />
          <ComparisonSection comparison={report.comparison} />
          <ParetoSection charts={report.charts} />
          <DriftSection charts={report.charts} />
          {report.configuration && (
            <ConfigurationSection configuration={report.configuration} />
          )}

          <Card
            title="What the words mean"
            subtitle="Six terms. Everything on this page is built from them."
            actions={
              <Button variant="ghost" onClick={() => setShowGlossary(!showGlossary)}>
                {showGlossary ? 'Hide' : 'Show'}
              </Button>
            }
          >
            {showGlossary && (
              <dl className="space-y-3">
                {report.how_to_read.map((item) => (
                  <div key={item.term}>
                    <dt className="text-sm font-medium text-ink">{item.term}</dt>
                    <dd className="mt-0.5 text-sm leading-relaxed text-ink-2">{item.meaning}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

/** What a gate is, in words, before any number is shown.
 *
 * Every table on this page is about gates. A reader who does not know what one
 * is cannot read any of it, and "gate" is not a term the field uses — it is
 * ours, so nobody arrives already knowing it.
 */
function GateExplainer() {
  const [open, setOpen] = useState(false)

  const gates = [
    {
      name: 'always',
      plain: 'Re-check on every single commit.',
      skips: 'Nothing.',
      why: 'The yardstick. Every other gate is measured as invocations avoided against this.',
    },
    {
      name: 'content',
      plain: 'Re-check whenever any file\u2019s bytes changed.',
      skips: 'Commits that touched no file at all.',
      why: 'Obvious and safe, but it still pays to re-check after you fix a typo in a comment.',
    },
    {
      name: 'structural',
      plain: 'Re-check only when the code\u2019s shape changed \u2014 classes, methods, inheritance, what calls what.',
      skips: 'Comments, formatting, renamed local variables, reordered statements.',
      why: 'None of those can change whether your code matches a class diagram, so re-checking after them is a wasted invocation.',
    },
    {
      name: 'isomorphism',
      plain: 'Also skip when the shape changed but the new shape is the same picture as the old one \u2014 for example a class renamed everywhere.',
      skips: 'Everything above, plus project-wide renames and reshuffles.',
      why: 'The cheapest. But if your diagram names that class, the rename did break conformance and this gate misses it. That is the trade the study measures.',
    },
  ]

  return (
    <Card
      title="First: what is a gate?"
      subtitle="Every table below is about gates. Two minutes here makes the rest of the page readable."
      actions={
        <Button variant="ghost" onClick={() => setOpen(!open)}>
          {open ? 'Hide' : 'Explain'}
        </Button>
      }
    >
      <p className="text-sm leading-relaxed text-ink-2">
        Checking whether your code still matches your UML diagram means calling a language
        model, and it has to be redone every time the code changes. A{' '}
        <span className="font-medium text-ink">gate</span> is the decision made{' '}
        <span className="italic">before</span> that call: <span className="text-ink">has anything
        changed that could possibly affect the answer?</span> If not, reuse the previous result and
        the model is never invoked.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-ink-2">
        Four gates are implemented, from most cautious to most economical. The whole study is one
        question: how many model invocations does each one avoid, and what does avoiding them
        cost in missed problems?
      </p>

      {open && (
        <div className="mt-4 space-y-3">
          {gates.map((gate) => (
            <div key={gate.name} className="rounded-lg border border-hairline bg-surface-2 p-3">
              <div className="font-mono text-sm text-ink">{gate.name}</div>
              <p className="mt-1 text-sm text-ink-2">{gate.plain}</p>
              <dl className="mt-2 space-y-1 text-xs text-muted">
                <div>
                  <dt className="inline font-medium">Skips: </dt>
                  <dd className="inline">{gate.skips}</dd>
                </div>
                <div>
                  <dt className="inline font-medium">Why it matters: </dt>
                  <dd className="inline">{gate.why}</dd>
                </div>
              </dl>
            </div>
          ))}
          <p className="text-sm leading-relaxed text-ink-2">
            <span className="font-medium text-ink">The one rule for reading this page:</span>{' '}
            a gate that skips more avoids more invocations but risks missing more. Never look at how
            much a gate skipped without looking at what it missed in the same glance.
          </p>
        </div>
      )}
    </Card>
  )
}


/** How long a missed change stayed missed.
 *
 * "--" means not measured -- either no oracle, or no miss to measure. It never
 * means zero, and a median that the survival curve never reaches is reported as
 * "more than N" rather than invented. */
function RecoveryCell({ recovery }: { recovery: RecoveryHorizon | undefined }) {
  if (!recovery || !recovery.measured) {
    return <span className="text-xs text-muted">not measured</span>
  }
  if (recovery.misses_tracked === 0) {
    return <span className="text-good">nothing missed</span>
  }
  if (recovery.median_commits !== null) {
    return (
      <>
        {recovery.median_commits.toFixed(0)}
        <div className="text-xs text-muted">
          commits · {recovery.resolved_count}/{recovery.misses_tracked} corrected
        </div>
      </>
    )
  }
  return (
    <>
      <span className="text-warning">&gt;{recovery.censored_beyond ?? 0}</span>
      <div className="text-xs text-muted">{recovery.censored_count} still outstanding</div>
    </>
  )
}


/** The sentence under every table. Styled once, so it reads as one voice. */
function Reading({ children }: { children: ReactNode }) {
  return (
    <p className="mt-4 border-l-2 border-series-1/50 pl-3 text-sm leading-relaxed text-ink-2">
      {children}
    </p>
  )
}

function Th({ children, numeric }: { children: ReactNode; numeric?: boolean }) {
  return (
    <th className={`py-2 pr-4 font-medium ${numeric ? 'text-right' : 'text-left'}`}>{children}</th>
  )
}

function Td({ children, numeric }: { children: ReactNode; numeric?: boolean }) {
  return (
    <td className={`py-2.5 pr-4 ${numeric ? 'text-right tabular-nums' : ''}`}>{children}</td>
  )
}

// --- Table 1 -----------------------------------------------------------------

function StudySection({ study }: { study: StudyTable }) {
  return (
    <Card
      title={`Table ${study.number} — ${study.title}`}
      actions={
        <Button
          variant="ghost"
          onClick={() =>
            downloadCsv(
              'table1-what-was-studied.csv',
              study.rows.map((row) => ({ item: row.label, value: row.value, detail: row.detail })),
            )
          }
        >
          CSV
        </Button>
      }
    >
      <dl className="grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
        {study.rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-4 border-b border-hairline/60 pb-2">
            <dt className="text-sm text-muted">{row.label}</dt>
            <dd className="text-right">
              <span className="text-lg font-semibold tabular-nums text-ink">{row.value}</span>
              {row.detail && <div className="text-xs text-muted">{row.detail}</div>}
            </dd>
          </div>
        ))}
      </dl>
      <Reading>{study.reading}</Reading>
    </Card>
  )
}

// --- Table 2: the headline ---------------------------------------------------

function GateSection({
  gates,
  charts,
}: {
  gates: GateTable
  charts: StatisticsReport['charts']
}) {
  const [openGate, setOpenGate] = useState<string | null>(null)
  const figureRef = useRef<SVGSVGElement>(null)

  return (
    <Card
      title={`Table ${gates.number} — ${gates.title}`}
      subtitle="This is the result the paper is about."
      actions={
        <Button variant="ghost" onClick={() => downloadCsv('table2-gates.csv', gates.rows)}>
          CSV
        </Button>
      }
    >
      {gates.recommended.gate && (
        <div className="mb-4">
          <Banner tone={gates.recommended.safe ? 'good' : 'warning'} title="Use this one">
            {gates.recommended.reason}
          </Banner>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-hairline text-xs text-muted">
            <tr>
              <Th>Gate</Th>
              <Th numeric>Runs</Th>
              <Th numeric>Skipped</Th>
              <Th numeric>Skip rate</Th>
              <Th numeric>
                Missed
                <div className="font-normal normal-case">all runs</div>
              </Th>
              <Th numeric>
                Caught
                <div className="font-normal normal-case">of real changes</div>
              </Th>
              <Th numeric>
                Correctly skipped
                <div className="font-normal normal-case">of quiet commits</div>
              </Th>
              <Th numeric>Recovery</Th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {gates.rows.map((row) => (
              <tr
                key={row.gate}
                onClick={() => setOpenGate(openGate === row.gate ? null : row.gate)}
                className="cursor-pointer border-b border-hairline/50 transition hover:bg-surface-2"
              >
                <Td>
                  <span className="font-mono text-ink">{row.gate}</span>
                  {row.is_baseline && <span className="ml-2 text-xs text-muted">baseline</span>}
                  {!row.enough_runs && (
                    <span className="ml-2 text-xs text-warning" title="Too few runs to trust the rate">
                      few runs
                    </span>
                  )}
                </Td>
                <Td numeric>{row.runs}</Td>
                <Td numeric>{row.skipped}</Td>
                <Td numeric>
                  {formatPercent(row.skip_rate)}
                  {row.skip_low !== null && (
                    <div className="text-xs text-muted">
                      {formatPercent(row.skip_low, 0)}–{formatPercent(row.skip_high, 0)}
                    </div>
                  )}
                </Td>
                <Td numeric>
                  {row.missed === null ? (
                    <span className="text-xs text-muted">not measured</span>
                  ) : row.missed === 0 ? (
                    <span className="text-good">0</span>
                  ) : (
                    <span className="text-warning">{row.missed}</span>
                  )}
                </Td>
                {/* Recall: of the commits where conformance really changed,
                    how many did this gate re-analyse? The column beside it
                    divides by every run instead, and most commits change
                    nothing, so the two disagree and both are shown. */}
                <Td numeric>
                  {row.recall === null ? (
                    <span className="text-xs text-muted">not measured</span>
                  ) : (
                    <>
                      <span className={row.recall === 1 ? 'text-good' : 'text-warning'}>
                        {formatPercent(row.recall)}
                      </span>
                      <div className="text-xs text-muted">
                        {row.recall_low !== null
                          ? `${formatPercent(row.recall_low, 0)}–${formatPercent(row.recall_high, 0)}`
                          : ''}
                        {row.changed_checked ? ` · n=${row.changed_checked}` : ''}
                      </div>
                    </>
                  )}
                </Td>
                <Td numeric>
                  {row.specificity === null ? (
                    <span className="text-xs text-muted">not measured</span>
                  ) : (
                    <>
                      {formatPercent(row.specificity)}
                      <div className="text-xs text-muted">
                        {row.unchanged_checked ? `n=${row.unchanged_checked}` : ''}
                      </div>
                    </>
                  )}
                </Td>
                <Td numeric>
                  <RecoveryCell recovery={row.recovery} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openGate && (
        <div className="mt-3 rounded border border-hairline bg-surface-2 p-3">
          {(() => {
            const row = gates.rows.find((entry) => entry.gate === openGate)
            if (!row) return null
            return (
              <>
                <p className="text-sm text-ink-2">{row.reading}</p>
                <p className="mt-2 text-xs text-muted">{row.description}</p>
              </>
            )
          })()}
        </div>
      )}

      <Reading>{gates.reading}</Reading>

      <div className="mt-6">
        <Figure
          title={charts.skip_by_gate.title}
          caption={charts.skip_by_gate.caption}
          actions={
            <Button
              variant="ghost"
              onClick={() => downloadSvgElement(figureRef.current, 'figure1-skip-by-gate.svg', '#ffffff', true)}
            >
              Save as SVG
            </Button>
          }
        >
          <BarChart data={charts.skip_by_gate.data} svgRef={figureRef} />
        </Figure>
      </div>
    </Card>
  )
}

// --- Table 3 -----------------------------------------------------------------

function ProjectSection({ projects }: { projects: ProjectTable }) {
  const [open, setOpen] = useState<string | null>(null)

  return (
    <Card
      title={`Table ${projects.number} — ${projects.title}`}
      subtitle={
        projects.gate
          ? `Numbers below are for the ${projects.gate} gate.`
          : 'No gate recommended yet.'
      }
      actions={
        <Button variant="ghost" onClick={() => downloadCsv('table3-projects.csv', projects.rows)}>
          CSV
        </Button>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-hairline text-xs text-muted">
            <tr>
              <Th>Project</Th>
              <Th numeric>Commits</Th>
              <Th numeric>Skip rate</Th>
              <Th numeric>Missed</Th>
              <Th numeric>Tokens saved</Th>
              <Th numeric>Drift/commit</Th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            {projects.rows.map((row) => (
              <Fragment key={row.project}>
              <tr
                onClick={() => setOpen(open === row.project ? null : row.project)}
                className="cursor-pointer border-b border-hairline/50 transition hover:bg-surface-2"
              >
                <Td>
                  <span className="mr-1.5 text-muted">{open === row.project ? '▾' : '▸'}</span>
                  <span className="text-ink">{row.project}</span>
                  {!row.enough_runs && (
                    <span className="ml-2 text-xs text-warning">few runs</span>
                  )}
                </Td>
                <Td numeric>{row.commits}</Td>
                <Td numeric>{formatPercent(row.skip_rate)}</Td>
                <Td numeric>
                  {row.missed === null ? (
                    <span className="text-xs text-muted">—</span>
                  ) : row.missed === 0 ? (
                    <span className="text-good">0</span>
                  ) : (
                    <span className="text-warning">{row.missed}</span>
                  )}
                </Td>
                <Td numeric>
                  {row.tokens_saved === null ? '—' : formatNumber(row.tokens_saved)}
                </Td>
                <Td numeric>{formatNumber(row.drift_per_commit, 2)}</Td>
              </tr>
              {open === row.project && (
                <tr className="border-b border-hairline/50">
                  <td colSpan={6} className="bg-surface-2 px-3 py-3">
                    <ProjectGateBreakdown row={row} />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3">
        {projects.consistent_ranking ? (
          <Badge color={STATUS.good} glyph="✓">
            Same ranking in every project
          </Badge>
        ) : (
          <Badge color={STATUS.warning} glyph="!">
            Ranking differs between projects
          </Badge>
        )}
      </div>

      <Reading>{projects.reading}</Reading>
    </Card>
  )
}

/** Every gate's numbers for one project.
 *
 * The pooled table answers "how did each gate do overall" and the project table
 * answers "did the recommended gate work here". Neither answers "what happened
 * in this project", which is the question someone looking at their own
 * repository is actually asking. This does.
 */
function ProjectGateBreakdown({ row }: { row: ProjectRow }) {
  return (
    <div>
      <p className="mb-2 text-xs text-muted">
        Every gate, for <span className="text-ink-2">{row.project}</span> alone — the same four
        rows as the headline table, but for this repository only.
      </p>
      <table className="w-full text-sm">
        <thead className="border-b border-hairline text-xs text-muted">
          <tr>
            <Th>Gate</Th>
            <Th numeric>Runs</Th>
            <Th numeric>Skipped</Th>
            <Th numeric>Skip rate</Th>
            <Th numeric>Missed</Th>
            <Th numeric>Tokens</Th>
            <Th numeric>Saved</Th>
          </tr>
        </thead>
        <tbody className="text-ink-2">
          {row.per_gate.map((gate) => (
            <tr key={gate.gate} className="border-b border-hairline/40">
              <Td>
                <span className="font-mono text-ink">{gate.gate}</span>
                {!gate.enough_runs && gate.runs > 0 && (
                  <span className="ml-2 text-xs text-warning">few runs</span>
                )}
              </Td>
              <Td numeric>{gate.runs || '—'}</Td>
              <Td numeric>{gate.runs ? gate.skipped : '—'}</Td>
              <Td numeric>{formatPercent(gate.skip_rate)}</Td>
              <Td numeric>
                {gate.missed === null ? (
                  <span className="text-xs text-muted">—</span>
                ) : gate.missed === 0 ? (
                  <span className="text-good">0</span>
                ) : (
                  <span className="text-warning">{gate.missed}</span>
                )}
              </Td>
              <Td numeric>{gate.tokens ? formatNumber(gate.tokens) : '—'}</Td>
              <Td numeric>
                {gate.tokens_saved === null ? '—' : formatNumber(gate.tokens_saved)}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        Drift here was {formatNumber(row.drift_per_commit, 2)} new violations per commit, and the
        median similarity score was {formatNumber(row.median_similarity, 3)}.
      </p>
    </div>
  )
}

// --- Table 4 -----------------------------------------------------------------

function DeviationSection({ deviations }: { deviations: DeviationTable }) {
  return (
    <Card
      title={`Table ${deviations.number} — ${deviations.title}`}
      subtitle="16 deliberate design changes with known right answers. The only table here with unambiguous ground truth."
      actions={
        deviations.available ? (
          <Button variant="ghost" onClick={() => downloadCsv('table4-controlled-test.csv', deviations.rows)}>
            CSV
          </Button>
        ) : undefined
      }
    >
      {!deviations.available ? (
        <EmptyState title="Not run yet">{deviations.reading}</EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-hairline text-xs text-muted">
                <tr>
                  <Th>Gate</Th>
                  <Th numeric>Caught</Th>
                  <Th numeric>Missed</Th>
                  <Th numeric>False alarms</Th>
                  <Th numeric>Correctly ignored</Th>
                </tr>
              </thead>
              <tbody className="text-ink-2">
                {deviations.rows.map((row) => (
                  <tr key={row.gate} className="border-b border-hairline/50">
                    <Td>
                      <span className="font-mono text-ink">{row.gate}</span>
                    </Td>
                    <Td numeric>
                      <span className="text-good">{row.caught}</span>
                    </Td>
                    <Td numeric>
                      {row.missed === 0 ? (
                        <span className="text-good">0</span>
                      ) : (
                        <span className="text-warning">{row.missed}</span>
                      )}
                    </Td>
                    <Td numeric>{row.false_alarms}</Td>
                    <Td numeric>{row.correctly_ignored}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Reading>{deviations.reading}</Reading>
        </>
      )}
    </Card>
  )
}

// --- the one significance test ------------------------------------------------

function ComparisonSection({ comparison }: { comparison: StatisticsReport['comparison'] }) {
  if (!comparison.left || !comparison.right) return null

  return (
    <Card
      title="Is the difference between the two gates real?"
      subtitle="McNemar's exact test — the one significance test on this page."
    >
      {comparison.usable ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Figureless label="Commits both saw" value={comparison.paired_observations ?? 0} />
          <Figureless label="They disagreed on" value={comparison.discordant ?? 0} />
          <Figureless
            label={`Only ${comparison.left} re-analysed`}
            value={comparison.left_only ?? 0}
          />
          <Figureless
            label="p-value"
            value={comparison.p_text ?? '—'}
            tone={comparison.p_value !== null && comparison.p_value < 0.05 ? STATUS.good : undefined}
          />
        </div>
      ) : (
        <EmptyState title="Cannot test this yet">{comparison.reason}</EmptyState>
      )}
      <Reading>{comparison.reading}</Reading>
    </Card>
  )
}

function Figureless({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="rounded border border-hairline bg-surface-2 px-3 py-2.5">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
    </div>
  )
}

// --- Figure 2 -----------------------------------------------------------------

function ParetoSection({ charts }: { charts: StatisticsReport['charts'] }) {
  const figureRef = useRef<SVGSVGElement>(null)
  const pareto = charts.pareto

  return (
    <Card title="Which gate is actually worth choosing?">
      <Figure
        title={pareto.title}
        caption={pareto.caption}
        actions={
          pareto.available ? (
            <>
              <Button
                variant="ghost"
                onClick={() => downloadCsv('figure3-pareto.csv', pareto.data)}
              >
                CSV
              </Button>
              <Button
                variant="ghost"
                onClick={() => downloadSvgElement(figureRef.current, 'figure3-pareto.svg', '#ffffff', true)}
              >
                Save as SVG
              </Button>
            </>
          ) : undefined
        }
      >
        {pareto.available ? (
          <ParetoChart data={pareto.data} svgRef={figureRef} />
        ) : (
          <EmptyState title="Not measured yet">{pareto.reason}</EmptyState>
        )}
      </Figure>
    </Card>
  )
}

function DriftSection({ charts }: { charts: StatisticsReport['charts'] }) {
  const figureRef = useRef<SVGSVGElement>(null)
  const hasData = charts.drift.data.length > 0

  return (
    <Card title="Are the code and the diagram drifting apart?">
      <Figure
        title={charts.drift.title}
        caption={charts.drift.caption}
        actions={
          hasData ? (
            <>
              <Button
                variant="ghost"
                onClick={() =>
                  downloadCsv(
                    'figure2-drift.csv',
                    charts.drift.data.flatMap((series) =>
                      series.points.map((point) => ({ project: series.project, ...point })),
                    ),
                  )
                }
              >
                CSV
              </Button>
              <Button
                variant="ghost"
                onClick={() => downloadSvgElement(figureRef.current, 'figure2-drift.svg', '#ffffff', true)}
              >
                Save as SVG
              </Button>
            </>
          ) : undefined
        }
      >
        <DriftChart series={charts.drift.data} svgRef={figureRef} />
      </Figure>
    </Card>
  )
}

/** What settings produced these runs.
 *
 * Reviewers of any study involving a language model expect the model,
 * temperature and seed to be stated; their absence is a routine review comment.
 * Shown here rather than buried in a config file so it can be copied straight
 * into the methodology section.
 */
function ConfigurationSection({
  configuration,
}: {
  configuration: NonNullable<StatisticsReport['configuration']>
}) {
  if (!configuration.rows.length) return null

  return (
    <Card
      title={configuration.title}
      subtitle="Copy this into the paper's methodology section."
      actions={
        <Button
          variant="ghost"
          onClick={() =>
            downloadCsv(
              'study-configuration.csv',
              configuration.rows.map((row) => ({
                setting: row.label,
                value: row.value,
                note: row.note,
              })),
            )
          }
        >
          CSV
        </Button>
      }
    >
      <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
        {configuration.rows.map((row) => (
          <div
            key={row.label}
            className="flex items-baseline justify-between gap-4 border-b border-hairline/60 pb-2"
          >
            <dt className="text-sm text-muted">{row.label}</dt>
            <dd className="text-right">
              <span
                className={`text-sm font-medium ${row.consistent ? 'text-ink' : 'text-warning'}`}
              >
                {String(row.value)}
              </span>
              {row.note && <div className="max-w-[34ch] text-xs text-muted">{row.note}</div>}
            </dd>
          </div>
        ))}
      </dl>

      {!configuration.consistent && (
        <div className="mt-4">
          <Banner tone="warning" title="Runs were not all produced the same way">
            Settings differ between runs. Re-run the corpus under one configuration, or report the
            split — a reviewer who finds two models in one corpus will discount the comparison.
          </Banner>
        </div>
      )}

      <Reading>{configuration.reading}</Reading>
    </Card>
  )
}
