import type { VersionRecord } from '../lib/types'
import { SERIES, formatDate } from '../lib/theme'
import { Button, Card, EmptyState } from './ui'

/** Version history.
 *
 * The store keeps a bounded ring of the most recent snapshots, so this list is
 * also a statement of what can still be compared or rolled back to.
 */
export function VersionTimeline({
  versions,
  maxVersions,
  activeVersion,
  onView,
}: {
  versions: VersionRecord[]
  maxVersions: number
  activeVersion: number | null
  onView: (version: number) => void
}) {
  return (
    <Card
      title="Version history"
      subtitle={`The last ${maxVersions} snapshots are retained; older ones are discarded automatically.`}
    >
      {versions.length === 0 ? (
        <EmptyState title="No versions yet">
          The first analysis creates version 1.
        </EmptyState>
      ) : (
        <ol className="space-y-2">
          {versions.map((version) => {
            const reused = version.gate?.should_invoke_llm === false
            const isActive = version.version === activeVersion
            return (
              <li
                key={version.version}
                className={`rounded-lg border px-3.5 py-3 ${
                  isActive ? 'border-series-1/60 bg-surface-2' : 'border-hairline'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span
                      aria-hidden="true"
                      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold text-plane"
                      style={{ background: reused ? SERIES.cached : SERIES.reanalysed }}
                    >
                      {version.version}
                    </span>
                    <div>
                      <div className="text-sm text-ink">
                        {reused ? 'Reused previous analysis' : 'Re-analysed'}
                        {version.reused_from ? ` (from v${version.reused_from})` : ''}
                      </div>
                      <div className="text-xs text-muted">{formatDate(version.created_at)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-sm tabular-nums text-ink">
                        {version.similarity_score ?? '—'}
                        {version.similarity_score !== null && '%'}
                      </div>
                      <div className="text-xs text-muted tabular-nums">
                        {version.node_count} nodes · {version.gap_count} gaps
                      </div>
                    </div>
                    <Button variant="ghost" onClick={() => onView(version.version)}>
                      View graph
                    </Button>
                  </div>
                </div>
                {version.gate?.reason && (
                  <p className="mt-2 text-xs text-muted">{version.gate.reason}</p>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}
