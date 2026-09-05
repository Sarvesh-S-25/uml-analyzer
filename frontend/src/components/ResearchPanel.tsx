import { useState } from 'react'
import { api, errorMessage } from '../lib/api'
import type { ModelComparison, PublicConfig, Spread } from '../lib/types'
import { formatMs } from '../lib/theme'
import { useToast } from './Toast'
import { Banner, Button, Card, Section, StatTile } from './ui'

interface Repeatability {
  runs: number
  llm_enabled: boolean
  similarity_score: Spread
  gap_count: Spread
  graph_node_count: Spread
  note: string
}

/** Measurements that belong to the study rather than to day-to-day use.
 *
 * Both answer questions a reader will ask about any LLM-produced number: how
 * stable is it across identical runs, and how much of it is about this
 * particular model?
 */
export function ResearchPanel({
  projectName,
  config,
}: {
  projectName: string
  config: PublicConfig | null
}) {
  const toast = useToast()
  const [runs, setRuns] = useState(3)
  const [repeat, setRepeat] = useState<Repeatability | null>(null)
  const [repeatBusy, setRepeatBusy] = useState(false)

  const [selected, setSelected] = useState<string[]>([])
  const [comparison, setComparison] = useState<ModelComparison | null>(null)
  const [compareBusy, setCompareBusy] = useState(false)

  const models = config?.available_models ?? []

  async function runRepeatability() {
    setRepeatBusy(true)
    try {
      setRepeat(await api.repeatability(projectName, runs))
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Repeatability run failed.'), 'critical')
    } finally {
      setRepeatBusy(false)
    }
  }

  async function runComparison() {
    setCompareBusy(true)
    try {
      setComparison(await api.modelComparison(projectName, selected))
    } catch (caught) {
      toast.notify(errorMessage(caught, 'Model comparison failed.'), 'critical')
    } finally {
      setCompareBusy(false)
    }
  }

  function toggle(spec: string) {
    setSelected((current) =>
      current.includes(spec) ? current.filter((item) => item !== spec) : [...current, spec],
    )
  }

  return (
    <Card
      title="Measurement"
      subtitle="Run-to-run stability, and how much a finding depends on which model produced it."
    >
      <div className="space-y-6">
        <Section title="Repeatability">
          <p className="mb-3 text-xs text-muted">
            Re-runs the full analysis on identical input. A single score from a non-deterministic
            model is not a measurement; this is the spread that has to accompany it.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-muted">
              Runs
              <select
                value={runs}
                onChange={(event) => setRuns(Number(event.target.value))}
                className="ml-2 rounded-md border border-hairline bg-plane px-2 py-1 text-xs text-ink"
              >
                {[2, 3, 5, 10].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <Button onClick={runRepeatability} loading={repeatBusy}>
              Run
            </Button>
          </div>

          {repeat && (
            <div className="mt-3">
              {!repeat.llm_enabled && (
                <div className="mb-3">
                  <Banner tone="info">{repeat.note}</Banner>
                </div>
              )}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatTile
                  label="Match score"
                  value={`${repeat.similarity_score.mean}`}
                  detail={`± ${repeat.similarity_score.stdev} (range ${repeat.similarity_score.range})`}
                />
                <StatTile
                  label="Gaps reported"
                  value={`${repeat.gap_count.mean}`}
                  detail={`± ${repeat.gap_count.stdev}`}
                />
                <StatTile
                  label="Graph nodes"
                  value={`${repeat.graph_node_count.mean}`}
                  detail={`± ${repeat.graph_node_count.stdev}`}
                />
              </div>
            </div>
          )}
        </Section>

        <Section title="Cross-model agreement">
          <p className="mb-3 text-xs text-muted">
            The same analysis under several models. Structural findings are identical by
            construction, so any disagreement is confined to the model-authored score, gaps, and
            graph. Nothing here is saved to the version history.
          </p>

          {models.length <= 1 ? (
            <Banner tone="info" title="Only one model is configured">
              Set <code className="text-ink-2">LLM_COMPARISON_MODELS</code> in the backend
              <code className="text-ink-2"> .env</code> to something like{' '}
              <code className="text-ink-2">anthropic:claude-sonnet-4-5,openai:gpt-4o-mini</code> to
              compare. The deterministic offline path is always available as a control.
            </Banner>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap gap-2">
                {models.map((model) => (
                  <button
                    key={model.spec}
                    onClick={() => toggle(model.spec)}
                    disabled={!model.available}
                    className={`rounded-full border px-3 py-1 text-xs transition disabled:opacity-40 ${
                      selected.includes(model.spec)
                        ? 'border-series-1 text-ink'
                        : 'border-hairline text-muted hover:text-ink-2'
                    }`}
                    title={model.available ? model.spec : `${model.provider} is not configured`}
                  >
                    {model.model}
                  </button>
                ))}
              </div>
              <Button onClick={runComparison} loading={compareBusy}>
                {selected.length > 0 ? `Compare ${selected.length} models` : 'Compare all available'}
              </Button>
            </>
          )}

          {comparison && (
            <div className="mt-4 space-y-3">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted">
                    <tr className="border-b border-hairline">
                      <th className="py-2 pr-3 font-medium">Model</th>
                      <th className="py-2 pr-3 font-medium text-right">Score</th>
                      <th className="py-2 pr-3 font-medium text-right">Gaps</th>
                      <th className="py-2 pr-3 font-medium text-right">Grounded</th>
                      <th className="py-2 pr-3 font-medium text-right">Tokens</th>
                      <th className="py-2 font-medium text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="text-ink-2">
                    {comparison.models.map((entry) => (
                      <tr key={entry.spec} className="border-b border-hairline/50">
                        <td className="py-2 pr-3">{entry.model ?? entry.spec}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {entry.error ? '—' : `${entry.similarity_score}%`}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {entry.error ? '—' : entry.gap_count}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {entry.grounded_node_ratio == null
                            ? '—'
                            : `${Math.round(entry.grounded_node_ratio * 100)}%`}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {(entry.prompt_tokens ?? 0) + (entry.completion_tokens ?? 0)}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {entry.error ? entry.error : formatMs(entry.latency_ms ?? 0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {comparison.agreement.length > 0 && (
                <div>
                  <h4 className="mb-1 text-xs font-medium text-ink">Pairwise agreement</h4>
                  <ul className="space-y-1 text-xs text-ink-2">
                    {comparison.agreement.map((pair, index) => (
                      <li key={index}>
                        {pair.pair[0]} ↔ {pair.pair[1]}: score differs by{' '}
                        <span className="tabular-nums">{pair.score_difference}</span>, gap overlap{' '}
                        <span className="tabular-nums">
                          {pair.gap_jaccard == null ? 'n/a' : `${Math.round(pair.gap_jaccard * 100)}%`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-muted">{comparison.note}</p>
            </div>
          )}
        </Section>
      </div>
    </Card>
  )
}
