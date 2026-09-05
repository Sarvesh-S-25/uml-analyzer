import type { Metrics, RunRow } from '../lib/types'
import { SERIES, formatDate, formatMs, formatNumber } from '../lib/theme'
import { Card, EmptyState, InfoHint, StatTile } from './ui'

/** What the gate actually saved on this project, and what it risked.
 *
 * The unit of saving here is **model invocations avoided** — the quantity the
 * study is about. Tokens are reported underneath as the mechanism, and the
 * dollar figures the API also returns are deliberately not shown: this is a
 * measurement of a change-detection strategy, not a procurement exercise, and
 * putting money at the top invites the reader to argue about pricing instead of
 * about the gate.
 */
export function MetricsPanel({ metrics, runs }: { metrics: Metrics; runs: RunRow[] }) {
  if (metrics.total_runs === 0) {
    return (
      <Card title="What the gate saved">
        <EmptyState title="No checks recorded yet" icon="◔">
          Every check appends a row here: which gate ran, what it decided, and what it cost.
        </EmptyState>
      </Card>
    )
  }

  const avoided = metrics.total_runs - metrics.llm_calls
  const avoidedShare = metrics.total_runs > 0 ? avoided / metrics.total_runs : 0
  const cachedShare = metrics.total_runs > 0 ? metrics.cached_runs / metrics.total_runs : 0

  return (
    <Card
      title="What the gate saved"
      subtitle="Measured from this project's own recorded checks. The baseline is what the same sequence would have cost with the gate switched off."
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Model calls avoided"
          value={`${avoided} of ${metrics.total_runs}`}
          detail={`${Math.round(avoidedShare * 100)}% of checks answered without the model`}
          tone="var(--good)"
          hint="The headline quantity: how often the gate concluded that re-checking could not change the answer. This is what the study measures."
        />
        <StatTile
          label="Answered from a stored version"
          value={`${Math.round(metrics.cache_hit_rate * 100)}%`}
          detail={`${metrics.cached_runs} of ${metrics.total_runs} checks`}
          hint="The gate decided nothing relevant had changed, so a previous version was reused instead of being recomputed."
        />
        <StatTile
          label="Re-checked"
          value={metrics.reanalyses}
          detail="Checks where the gate decided the answer could have moved"
        />
        <StatTile
          label="Time not spent"
          value={formatMs(metrics.latency_saved_ms)}
          detail={`${formatMs(metrics.mean_latency_ms_llm)} per re-check vs ${formatMs(
            metrics.mean_latency_ms_cached,
          )} reused`}
        />
      </div>

      {/* One part-to-whole comparison, both segments directly labelled. */}
      <div className="mt-5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span>What the gate decided, across every check</span>
          <span className="flex gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: SERIES.reanalysed }}
              />
              Re-checked {metrics.reanalyses}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: SERIES.cached }}
              />
              Reused {metrics.cached_runs}
            </span>
          </span>
        </div>
        <div
          className="flex h-3 w-full gap-px overflow-hidden rounded"
          role="img"
          aria-label={`${metrics.reanalyses} re-checked, ${metrics.cached_runs} reused`}
        >
          <div style={{ background: SERIES.reanalysed, width: `${(1 - cachedShare) * 100}%` }} />
          <div style={{ background: SERIES.cached, width: `${cachedShare * 100}%` }} />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile
          label="Tokens sent"
          value={formatNumber(metrics.total_tokens)}
          detail={`Against ${formatNumber(metrics.baseline_total_tokens)} with the gate off`}
          hint="The mechanism behind the saving, reported for completeness. The claim this project makes is about avoided invocations, not about spend."
        />
        <StatTile
          label="Tokens not sent"
          value={formatNumber(metrics.tokens_saved)}
          detail="The difference between those two figures"
        />
        <StatTile
          label="Score movement"
          value={metrics.score_variance === null ? 'not measured' : metrics.score_variance.toFixed(2)}
          detail={
            metrics.score_variance === null
              ? 'Needs at least two checks'
              : 'How much the code moved — not model randomness; see Repeatability for that'
          }
        />
      </div>

      {runs.length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
            Recent checks
            <InfoHint text="One row per recorded check. 'Allowed' is the gate's decision; 'Called' is whether the model was actually reached. They differ when no model is configured." />
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">Recorded checks, most recent first</caption>
              <thead className="text-muted">
                <tr className="border-b border-hairline">
                  <th className="py-1.5 pr-3 font-medium">When</th>
                  <th className="py-1.5 pr-3 font-medium">Ver.</th>
                  <th className="py-1.5 pr-3 font-medium">Gate</th>
                  <th className="py-1.5 pr-3 font-medium">Allowed</th>
                  <th className="py-1.5 pr-3 font-medium">Called</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Changed</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Tokens</th>
                  <th className="py-1.5 text-right font-medium">Took</th>
                </tr>
              </thead>
              <tbody className="text-ink-2">
                {[...runs].reverse().slice(0, 12).map((run, index) => (
                  <tr key={`${run.timestamp}-${index}`} className="border-b border-hairline/60">
                    <td className="whitespace-nowrap py-1.5 pr-3">{formatDate(run.timestamp)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{run.version}</td>
                    <td className="py-1.5 pr-3 font-mono text-[11px]">{run.gate_strategy}</td>
                    <td className="py-1.5 pr-3">
                      <span style={{ color: run.gate_allowed_llm ? SERIES.reanalysed : SERIES.cached }}>
                        <span aria-hidden="true">{run.gate_allowed_llm ? '↻ ' : '= '}</span>
                        {run.gate_allowed_llm ? 'yes' : 'no'}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3">{run.llm_invoked ? 'yes' : 'no'}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">{run.changed_nodes}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {formatNumber((run.prompt_tokens ?? 0) + (run.completion_tokens ?? 0))}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{formatMs(run.latency_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  )
}
