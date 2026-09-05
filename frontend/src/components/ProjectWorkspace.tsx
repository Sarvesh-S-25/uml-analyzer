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
import { ConformanceReport } from './ConformanceReport'
import { FileManager } from './FileManager'
import { GraphView } from './GraphView'
import { MetricsPanel } from './MetricsPanel'
import { ResearchPanel } from './ResearchPanel'
import { UmlPanel } from './UmlPanel'
import { VersionTimeline } from './VersionTimeline'
import { useToast } from './Toast'
import { Badge, Banner, Button, Card, Section } from './ui'

const STRATEGY_HELP: Record<GateStrategy, string> = {
  always: 'Re-analyse on every run. The baseline: no caching, highest cost.',
  content: 'Re-analyse whenever any file’s bytes changed — including comments and formatting.',
  structural: 'Re-analyse when the AST-derived fingerprint changed. Formatting edits are free.',
  isomorphism:
    'As structural, but also reuse when the new graph is isomorphic to the old one — pure renames are relabelled, not re-analysed.',
}

type Tab = 'setup' | 'results' | 'history'

const TABS: Array<{ id: Tab; label: string; hint: string }> = [
  { id: 'setup', label: 'Setup', hint: 'Your code and your diagram' },
  { id: 'results', label: 'Results', hint: 'What conforms and what does not' },
  { id: 'history', label: 'History', hint: 'Versions, cost, and stability' },
]

export function ProjectWorkspace({
  projectName,
  config,
  onBack,
}: {
  projectName: string
  config: PublicConfig | null
  onBack: () => void
}) {
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('setup')

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
      toast.notify(errorMessage(caught, 'Could not load run history.'), 'critical')
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

  async function runAnalysis(force = false) {
    setAnalysing(true)
    setAnalysisError('')
    setViewedGraph(null)
    setTab('results')
    try {
      const analysis = await api.analyze(projectName, strategy, force)
      setResult(analysis)
      setStale(false)
      await refreshHistory()
      toast.notify(
        analysis.gate.should_invoke_llm
          ? `Re-analysed — version ${analysis.version}.`
          : `No relevant change; reused version ${analysis.reused_from_version}.`,
        'good',
      )
    } catch (caught) {
      setAnalysisError(errorMessage(caught, 'Analysis failed.'))
    } finally {
      setAnalysing(false)
    }
  }

  async function loadBenchmark() {
    try {
      setBenchmark(await api.benchmark(projectName))
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Benchmark failed.'), 'critical')
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
      setTab('results')
    } catch (caught) {
      toast.notify(errorMessage(caught, 'That version is no longer retained.'), 'critical')
    }
  }

  const shownGraph = viewedGraph?.data ?? result?.graph_data ?? null

  return (
    <div className="mx-auto max-w-7xl p-6">
      <button onClick={onBack} className="mb-5 text-sm text-muted transition hover:text-ink">
        ← All projects
      </button>

      <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-4">
        <div>
          <h1 className="text-lg font-semibold text-ink">{projectName}</h1>
          <p className="mt-0.5 text-xs text-muted">
            {versions.length} version{versions.length === 1 ? '' : 's'} retained
            {config && !config.llm_enabled && ' · deterministic mode'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {config && !config.llm_enabled && (
            <Badge glyph="!" color="#fab219">
              No model configured
            </Badge>
          )}
          <Button variant="primary" loading={analysing} onClick={() => runAnalysis(false)}>
            {analysing ? 'Analysing…' : 'Run analysis'}
          </Button>
        </div>
      </header>

      <nav className="mb-6 flex gap-6 border-b border-hairline" aria-label="Project sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            onClick={() => setTab(entry.id)}
            aria-current={tab === entry.id ? 'page' : undefined}
            className={`-mb-px border-b-2 px-1 pb-3 text-left transition ${
              tab === entry.id
                ? 'border-series-1 text-ink'
                : 'border-transparent text-muted hover:text-ink-2'
            }`}
          >
            <span className="block text-sm font-medium">{entry.label}</span>
            <span className="mt-0.5 block text-xs text-muted">{entry.hint}</span>
          </button>
        ))}
      </nav>

      {stale && tab === 'results' && (
        <div className="mb-4">
          <Banner tone="info" title="Files changed since this analysis" onDismiss={() => setStale(false)}>
            Run the analysis again to pick up your edits.
          </Banner>
        </div>
      )}

      {tab === 'setup' && (
        <div className="space-y-5">
          <FileManager
            projectName={projectName}
            onChanged={() => setStale(true)}
            onExplain={explain}
          />

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <UmlPanel projectName={projectName} onChanged={() => setStale(true)} />

            {explanation ? (
              <Card title={explanation.path} subtitle="Plain-English summary of this file.">
                <p className="text-sm leading-relaxed text-ink-2">{explanation.text}</p>
              </Card>
            ) : (
              <Card
                title="How this works"
                subtitle="Three inputs, no git needed."
              >
                <ol className="space-y-2 text-sm text-ink-2">
                  <li>
                    <span className="text-muted">1.</span> Put your code in the project — upload a
                    folder, a .zip, individual files, or write it here.
                  </li>
                  <li>
                    <span className="text-muted">2.</span> Upload the StarUML .mdj diagram that
                    describes the intended design.
                  </li>
                  <li>
                    <span className="text-muted">3.</span> Run the analysis. Repeat runs reuse the
                    previous result unless the structure actually changed.
                  </li>
                </ol>
                <p className="mt-3 text-xs text-muted">
                  Connecting GitHub is one way to fill step 1. It is never required.
                </p>
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === 'results' && (
        <div className="space-y-5">
          <Card
            title="Change-detection gate"
            subtitle="Which signal decides whether this run needs the language model at all."
          >
            <Section title="">
              <div className="flex flex-wrap gap-1 rounded-lg border border-hairline p-1">
                {(config?.gate_strategies ?? ['structural']).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setStrategy(option)}
                    className={`flex-1 rounded-md px-3 py-1.5 text-xs capitalize transition ${
                      strategy === option ? 'bg-surface-2 text-ink' : 'text-muted hover:text-ink-2'
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">{STRATEGY_HELP[strategy]}</p>
            </Section>

            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="primary" loading={analysing} onClick={() => runAnalysis(false)}>
                Run analysis
              </Button>
              <Button onClick={() => runAnalysis(true)} disabled={analysing}>
                Force full re-analysis
              </Button>
              <Button variant="ghost" onClick={loadBenchmark} disabled={analysing}>
                Token benchmark
              </Button>
            </div>

            {benchmark && (
              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-muted">Raw source tokens</dt>
                  <dd className="tabular-nums text-ink-2">
                    {benchmark.raw_tokens.toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Extracted structure</dt>
                  <dd className="tabular-nums text-ink-2">
                    {benchmark.optimized_tokens.toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Reduction</dt>
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
                    Token counts are estimated: tiktoken is not installed on the server.
                  </p>
                )}
              </dl>
            )}
          </Card>

          {analysisError && <Banner tone="critical">{analysisError}</Banner>}

          {result && <ConformanceReport result={result} />}

          <Card
            title={viewedGraph ? `Semantic graph — version ${viewedGraph.version}` : 'Semantic graph'}
            subtitle="Parsed structure, annotated with conformance status and any nodes the model proposed."
            actions={
              viewedGraph ? (
                <Button variant="ghost" onClick={() => setViewedGraph(null)}>
                  Back to latest
                </Button>
              ) : undefined
            }
          >
            <GraphView data={shownGraph} projectName={projectName} />
          </Card>
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-5">
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
  )
}
