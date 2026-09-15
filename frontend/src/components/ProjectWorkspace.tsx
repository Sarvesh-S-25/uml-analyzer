import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../lib/api'
import type {
  AnalysisResult,
  Benchmark,
  GateStrategy,
  GraphData,
  Metrics,
  PublicConfig,
  RunRow,
  VersionRecord,
} from '../lib/types'
import type { ProjectSection } from './AppShell'
import { CodePanel } from './CodePanel'
import { ConformanceReport } from './ConformanceReport'
import { DesignMap } from './DesignMap'
import { MetricsPanel } from './MetricsPanel'
import { ResearchPanel } from './ResearchPanel'
import { UmlPanel } from './UmlPanel'
import { VersionTimeline } from './VersionTimeline'
import { useToast } from './Toast'
import { Banner, Button, Card, EmptyState, InfoHint } from './ui'

/** Plain-English names for the four gates.
 *
 * The interface used to show the raw strategy identifiers — "isomorphism" among
 * them — with no indication of what any of them would do. The identifier is
 * kept underneath because it is what the API and the paper both use. */
const GATE_LABELS: Record<GateStrategy, { label: string; help: string }> = {
  always: {
    label: 'Always re-check',
    help: 'Re-check on every run, no matter what changed. The most thorough and the most expensive — this is the baseline the others are measured against.',
  },
  content: {
    label: 'When any byte changes',
    help: 'Re-check whenever a file changed at all, including comments, whitespace and formatting.',
  },
  structural: {
    label: 'When the structure changes',
    help: 'Re-check only when the shape of the code changed — a class, method or field added, removed or altered. Reformatting is free.',
  },
  isomorphism: {
    label: 'Rename-aware',
    help: 'As above, but a pure rename is recognised as the same design under new names and the previous result is relabelled instead of re-checked.',
  },
}

export function ProjectWorkspace({
  projectName,
  config,
  section,
  onSection,
}: {
  projectName: string
  config: PublicConfig | null
  section: ProjectSection
  onSection: (section: ProjectSection) => void
}) {
  const toast = useToast()
  const [strategy, setStrategy] = useState<GateStrategy>(
    config?.default_gate_strategy ?? 'structural',
  )
  const [analysing, setAnalysing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [analysisError, setAnalysisError] = useState('')

  const [versions, setVersions] = useState<VersionRecord[]>([])
  const [maxVersions, setMaxVersions] = useState(3)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [runs, setRuns] = useState<RunRow[]>([])
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null)
  const [explanation, setExplanation] = useState<{ path: string; text: string } | null>(null)
  const [viewedGraph, setViewedGraph] = useState<{ version: number; data: GraphData } | null>(null)
  const [stale, setStale] = useState(false)

  const refreshHistory = useCallback(async () => {
    try {
      const [versionData, metricData] = await Promise.all([
        api.versions(projectName),
        api.metrics(projectName),
      ])
      setVersions(versionData.versions)
      setMaxVersions(versionData.max_versions)
      setMetrics(metricData.metrics)
      setRuns(metricData.runs)
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Could not load the check history.'), 'critical')
    }
  }, [projectName, toast])

  useEffect(() => {
    setResult(null)
    setBenchmark(null)
    setViewedGraph(null)
    setExplanation(null)
    setStale(false)
    void refreshHistory()
  }, [projectName, refreshHistory])

  async function check(force = false) {
    setAnalysing(true)
    setAnalysisError('')
    setViewedGraph(null)
    onSection('results')
    try {
      const analysis = await api.analyze(projectName, strategy, force)
      setResult(analysis)
      setStale(false)
      await refreshHistory()
      toast.notify(
        analysis.gate.should_invoke_llm
          ? `Re-checked — version ${analysis.version}.`
          : `Nothing relevant changed; reused version ${analysis.reused_from_version}.`,
        'good',
      )
    } catch (caught) {
      setAnalysisError(errorMessage(caught, 'The check failed.'))
    } finally {
      setAnalysing(false)
    }
  }

  async function explain(path: string) {
    setExplanation({ path, text: 'Loading…' })
    try {
      const response = await api.explain(projectName, path)
      setExplanation({ path, text: response.explanation })
    } catch (caught) {
      setExplanation({ path, text: errorMessage(caught, 'Could not explain this file.') })
    }
  }

  async function viewVersionGraph(version: number) {
    try {
      setViewedGraph({ version, data: await api.versionGraph(projectName, version) })
      onSection('map')
    } catch (caught) {
      toast.notify(errorMessage(caught, 'That version is no longer kept.'), 'critical')
    }
  }

  const shownGraph = viewedGraph?.data ?? result?.graph_data ?? null
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header data-print-hide className="fixed right-16 top-3 z-30 flex h-8 items-center gap-2">
          {stale && <span className="hidden text-[11px] text-series-1 lg:inline">Files changed</span>}
          <Button variant="primary" loading={analysing} onClick={() => check(false)}>
            {analysing ? 'Comparing…' : 'Run comparison'}
          </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {section === 'code' && (
          <div className="h-full">
            <CodePanel
              projectName={projectName}
              result={result}
              explanation={explanation}
              onChanged={() => setStale(true)}
              onExplain={explain}
            />
          </div>
        )}

        {section === 'diagram' && (
          <div className="mx-auto max-w-3xl space-y-3 p-4">
            <UmlPanel projectName={projectName} onChanged={() => setStale(true)} />
            <Card title="How a check works" subtitle="Three inputs. No git required.">
              <ol className="space-y-2.5 text-sm text-ink-2">
                <li className="flex gap-2.5">
                  <span className="shrink-0 font-semibold text-muted">1</span>
                  <span>
                    Put your code in the project — upload a folder, a .zip, individual files, or
                    write it in the Code screen.
                  </span>
                </li>
                <li className="flex gap-2.5">
                  <span className="shrink-0 font-semibold text-muted">2</span>
                  <span>Upload the StarUML .mdj file that describes the intended design.</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="shrink-0 font-semibold text-muted">3</span>
                  <span>
                    Press <span className="font-medium text-ink">Check now</span>. Later checks
                    reuse the previous answer unless the code's structure actually changed.
                  </span>
                </li>
              </ol>
            </Card>
          </div>
        )}

        {section === 'results' && (
          <div className="mx-auto max-w-[1500px] space-y-4 p-4 lg:p-5">
            <details className="group rounded-lg border border-hairline bg-surface shadow-[var(--shadow-card)]">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 text-sm font-medium text-ink">
                <span>Analysis settings</span>
                <span className="flex items-center gap-2 text-xs font-normal text-muted">
                  {GATE_LABELS[strategy]?.label}
                  <span aria-hidden="true" className="transition group-open:rotate-90">›</span>
                </span>
              </summary>
              <div className="border-t border-hairline px-4 py-4">
                <p className="mb-3 max-w-[72ch] text-xs leading-relaxed text-muted">
                  Choose when code changes should trigger a fresh model-assisted comparison.
                  Structural parser checks still run independently.
                </p>
              <div className="flex flex-wrap gap-1.5">
                {(config?.gate_strategies ?? ['structural']).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setStrategy(option)}
                    aria-pressed={strategy === option}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                      strategy === option
                        ? 'border-series-1 bg-series-1/12 text-ink'
                        : 'border-hairline text-muted hover:text-ink-2'
                    }`}
                  >
                    {GATE_LABELS[option]?.label ?? option}
                  </button>
                ))}
              </div>
              <p className="mt-2.5 max-w-[70ch] text-xs leading-relaxed text-muted">
                {GATE_LABELS[strategy]?.help}
                <span className="ml-1.5 font-mono text-[10px] opacity-70">({strategy})</span>
              </p>

              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="primary" loading={analysing} onClick={() => check(false)}>
                  Check now
                </Button>
                <Button onClick={() => check(true)} disabled={analysing}>
                  Force a full re-check
                </Button>
                <Button
                  variant="ghost"
                  disabled={analysing}
                  onClick={async () => {
                    try {
                      setBenchmark(await api.benchmark(projectName))
                    } catch (caught) {
                      toast.notify(errorMessage(caught, 'Could not measure.'), 'critical')
                    }
                  }}
                >
                  Measure what gets sent
                </Button>
              </div>

              {benchmark && (
                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-muted">Whole source</dt>
                    <dd className="tabular-nums text-ink-2">
                      {benchmark.raw_tokens.toLocaleString()}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Structure only</dt>
                    <dd className="tabular-nums text-ink-2">
                      {benchmark.optimized_tokens.toLocaleString()}
                    </dd>
                  </div>
                  <div>
                    <dt className="flex items-center gap-1 text-xs text-muted">
                      Reduction
                      <InfoHint text="Sending the extracted structure instead of the raw source is what makes a check affordable at all. It is a property of the pipeline, not of any one gate." />
                    </dt>
                    <dd className="tabular-nums text-good">
                      {benchmark.token_reduction_percentage}%
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Files</dt>
                    <dd className="tabular-nums text-ink-2">{benchmark.files_considered}</dd>
                  </div>
                  {!benchmark.exact_token_counts && (
                    <p className="col-span-full text-xs text-muted">
                      These counts are estimated: tiktoken is not installed on the server.
                    </p>
                  )}
                </dl>
              )}
              </div>
            </details>

            {analysisError && <Banner tone="critical">{analysisError}</Banner>}

            {!result && !analysisError && (
              <EmptyState title="Not checked yet" icon="◉">
                Press “Check now” and the comparison between your code and your diagram appears
                here.
              </EmptyState>
            )}

            {result && <ConformanceReport result={result} />}

          </div>
        )}

        {section === 'map' && (
          <div className="mx-auto max-w-[1500px] p-3">
            <Card
              title={viewedGraph ? `Code map — version ${viewedGraph.version}` : 'Code map'}
              subtitle="Every class recovered from the source, arranged in layers and coloured by its verification status."
              actions={
                viewedGraph ? (
                  <Button variant="ghost" onClick={() => setViewedGraph(null)}>
                    Back to the latest
                  </Button>
                ) : undefined
              }
            >
              <DesignMap data={shownGraph} projectName={projectName} />
            </Card>
          </div>
        )}

        {section === 'history' && (
          <div className="space-y-3 p-4">
            <VersionTimeline
              versions={versions}
              maxVersions={maxVersions}
              activeVersion={viewedGraph?.version ?? result?.version ?? null}
              onView={viewVersionGraph}
            />
            {metrics && <MetricsPanel metrics={metrics} runs={runs} />}
            <ResearchPanel projectName={projectName} config={config} />
          </div>
        )}
      </div>
    </div>
  )
}
