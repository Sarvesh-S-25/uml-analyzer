import type { Metrics, RunRow } from '../lib/types'
import { SERIES, formatDate, formatMs, formatNumber } from '../lib/theme'
import { Card, EmptyState, StatTile } from './ui'

/** Cost and cache behaviour, measured from the run ledger.
 *
 * These are the numbers the incremental design is supposed to move. They come
 * from real runs recorded on disk, not from a simulation, so they can be
 * reported directly.
 */
export function MetricsPanel({ metrics, runs }: { metrics: Metrics; runs: RunRow[] }) {
  if (metrics.total_runs === 0) {
    return (
      <Card title="Run metrics">
        <EmptyState title="No runs recorded yet">
          Every analysis appends a row here: gate decision, tokens, and latency.
        </EmptyState>
      </Card>
    )
  }

  const cachedShare = metrics.total_runs > 0 ? metrics.cached_runs / metrics.total_runs : 0

  return (
    <Card
      title="Run metrics"
      subtitle="Measured from this project's own run history. The baseline is what the same sequence of runs would have cost with the gate disabled."
    >
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="Analyses run"
          value={formatNumber(metrics.total_runs)}
          detail={`${metrics.reanalyses} re-analysed · ${metrics.cached_runs} reused`}
        />
        <StatTile
          label="Cache hit rate"
          value={`${Math.round(metrics.cache_hit_rate * 100)}%`}
          detail="Runs the gate answered from a stored version"
          tone={SERIES.cached}
        />
        <StatTile
          label="Tokens used"
          value={formatNumber(metrics.total_tokens)}
          detail={`vs ${formatNumber(metrics.baseline_total_tokens)} without the gate`}
        />
        <StatTile
          label="Estimated cost"
          value={`$${metrics.actual_cost_usd.toFixed(4)}`}
          detail={`Saved $${metrics.cost_saved_usd.toFixed(4)}`}
        />
      </div>

      {/* One part-to-whole comparison, with both segments directly labelled. */}
      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between text-xs text-muted">
          <span>Gate decisions</span>
          <span className="flex gap-4">
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ background: SERIES.reanalysed }}
              />
              Re-analysed {metrics.reanalyses}
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
        <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded">
          <div
            className="rounded-l"
            style={{ background: SERIES.reanalysed, width: `${(1 - cachedShare) * 100}%` }}
          />
          <div
            className="rounded-r"
            style={{ background: SERIES.cached, width: `${cachedShare * 100}%` }}
          />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile
          label="Mean latency, re-analysis"
          value={formatMs(metrics.mean_latency_ms_llm)}
        />
        <StatTile label="Mean latency, reused" value={formatMs(metrics.mean_latency_ms_cached)} />
        <StatTile
          label="Similarity score variance across commits"
          value={metrics.score_variance === null ? '—' : metrics.score_variance.toFixed(2)}
          detail={
            metrics.score_variance === null
              ? 'Needs at least two runs'
              : 'How much the code moved, not model non-determinism — see Repeatability for that'
          }
        />
      </div>

      {runs.length > 0 && (
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">Recorded analysis runs</caption>
            <thead className="text-muted">
              <tr className="border-b border-hairline">
                <th className="py-2 pr-3 font-medium">When</th>
                <th className="py-2 pr-3 font-medium">Ver.</th>
                <th className="py-2 pr-3 font-medium">Gate</th>
                <th className="py-2 pr-3 font-medium">Decision</th>
                <th className="py-2 pr-3 font-medium text-right">Changed</th>
                <th className="py-2 pr-3 font-medium text-right">Tokens</th>
                <th className="py-2 font-medium text-right">Latency</th>
              </tr>
            </thead>
            <tbody className="text-ink-2">
              {[...runs].reverse().slice(0, 12).map((run, index) => (
                <tr key={`${run.timestamp}-${index}`} className="border-b border-hairline/50">
                  <td className="py-2 pr-3 whitespace-nowrap">{formatDate(run.timestamp)}</td>
                  <td className="py-2 pr-3 tabular-nums">{run.version}</td>
                  <td className="py-2 pr-3">{run.gate_strategy}</td>
                  <td className="py-2 pr-3">
                    <span
                      className="inline-flex items-center gap-1.5"
                      style={{
                        color: run.gate_allowed_llm ? SERIES.reanalysed : SERIES.cached,
                      }}
                    >
                      <span aria-hidden="true">{run.gate_allowed_llm ? '↻' : '='}</span>
                      {run.gate_allowed_llm ? 'Re-analysed' : 'Reused'}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{run.changed_nodes}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {formatNumber((run.prompt_tokens ?? 0) + (run.completion_tokens ?? 0))}
                  </td>
                  <td className="py-2 text-right tabular-nums">{formatMs(run.latency_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
