/** The shape of the statistics report.
 *
 * Mirrors `backend/stats/report.py` exactly. Every table carries a `reading` —
 * a plain-English sentence generated from that table's own numbers — because
 * the page's job is to be understood, not merely to be correct.
 */

export interface StudyRow {
  label: string
  value: string | number
  detail: string
}

export interface StudyTable {
  number: number
  title: string
  rows: StudyRow[]
  projects: number
  project_names: string[]
  commits: number
  runs: number
  gates: string[]
  has_oracle: boolean
  reading: string
}

export interface GateRow {
  gate: string
  description: string
  runs: number
  reanalysed: number
  skipped: number
  skip_rate: number | null
  skip_low: number | null
  skip_high: number | null
  checked_for_misses: number
  missed: number | null
  /** Misses over EVERY run. Most commits change nothing, so this flatters a
   *  gate that skips a long quiet stretch. Read it beside `recall`. */
  miss_rate: number | null
  miss_low: number | null
  miss_high: number | null
  /** Commits where an oracle established that conformance really changed. */
  changed_checked: number
  unchanged_checked: number
  /** Of the commits that really changed, the share this gate re-analysed. */
  recall: number | null
  recall_low: number | null
  recall_high: number | null
  /** Of the commits that changed nothing, the share it correctly skipped. */
  specificity: number | null
  specificity_low: number | null
  specificity_high: number | null
  recovery: RecoveryHorizon
  tokens: number
  tokens_saved: number | null
  percent_saved: number | null
  median_latency_ms: number | null
  is_baseline: boolean
  enough_runs: boolean
  reading: string
}

/** How long a missed change stays missed.
 *
 * A miss still outstanding when a project's history ends is *censored* — known
 * to be at least this long, exact length unknown. Those are never counted as
 * zero and never dropped, so `median_commits` is null rather than invented when
 * too many are outstanding for a median to exist. */
export interface RecoveryHorizon {
  measured: boolean
  reason: string
  misses_tracked: number
  resolved_count: number
  censored_count: number
  median_commits: number | null
  censored_beyond: number | null
  max_resolved: number | null
}

export interface Recommendation {
  gate: string | null
  skip_rate?: number | null
  missed?: number | null
  tokens_saved?: number | null
  safe?: boolean
  reason: string
}

export interface GateTable {
  number: number
  title: string
  rows: GateRow[]
  baseline_gate: string
  baseline_is_always: boolean
  recommended: Recommendation
  reading: string
}

export interface ProjectGateRow {
  gate: string
  runs: number
  reanalysed?: number
  skipped: number
  skip_rate: number | null
  missed: number | null
  miss_rate?: number | null
  tokens: number
  tokens_saved: number | null
  median_latency_ms?: number | null
  enough_runs: boolean
}

export interface ProjectRow {
  project: string
  commits: number
  runs: number
  skipped: number
  skip_rate: number | null
  missed: number | null
  tokens_saved: number | null
  drift_per_commit: number | null
  median_similarity: number | null
  best_gate: string | null
  ranking: string[]
  enough_runs: boolean
  per_gate: ProjectGateRow[]
}

export interface ProjectTable {
  number: number
  title: string
  gate: string | null
  rows: ProjectRow[]
  consistent_ranking: boolean
  lowest_skip_rate: number | null
  highest_skip_rate: number | null
  reading: string
}

export interface DeviationRow {
  gate: string
  caught: number
  missed: number
  false_alarms: number
  correctly_ignored: number
  precision: number | null
  recall: number | null
  reading: string
}

export interface DeviationTable {
  number: number
  title: string
  available: boolean
  rows: DeviationRow[]
  conformance_breaking?: number
  reading: string
}

export interface Comparison {
  left: string | null
  right: string | null
  paired_observations?: number
  left_only?: number
  right_only?: number
  discordant?: number
  agreed?: number
  p_value: number | null
  p_text?: string
  usable: boolean
  reason?: string
  reading: string
}

export interface SkipDatum {
  gate: string
  skip_rate: number | null
  low: number | null
  high: number | null
  miss_rate: number | null
  missed: number | null
  runs: number
}

export interface DriftSeries {
  project: string
  points: Array<{
    commit_index: number
    divergences: number
    absences: number
    violations: number
  }>
}

/** One gate as a point in the savings-versus-accuracy plane. */
export interface ParetoDatum {
  gate: string
  skip_rate: number | null
  skip_low: number | null
  skip_high: number | null
  recall: number | null
  recall_low: number | null
  recall_high: number | null
  changed_checked: number
  /** Gates that beat this one on both axes at once. */
  dominated_by: string[]
  /** Of those, the ones whose intervals do not overlap — the claim that
   *  survives a reviewer asking whether the difference is real. */
  robustly_dominated_by: string[]
  on_frontier: boolean
}

export interface Charts {
  skip_by_gate: { title: string; caption: string; data: SkipDatum[] }
  drift: { title: string; caption: string; data: DriftSeries[] }
  pareto: {
    title: string
    caption: string
    available: boolean
    reason: string
    data: ParetoDatum[]
  }
}

export interface Glossary {
  term: string
  meaning: string
}

export interface ConfigurationRow {
  label: string
  value: string | number | boolean
  note: string
  consistent: boolean
}

export interface Configuration {
  title: string
  rows: ConfigurationRow[]
  consistent: boolean
  reading: string
}

export interface StatisticsReport {
  usable: boolean
  reason?: string
  source?: string
  projects_included?: string[]
  inferred_labels?: number
  study: StudyTable
  gates: GateTable
  projects: ProjectTable
  deviations: DeviationTable
  comparison: Comparison
  configuration?: Configuration
  charts: Charts
  headline: string
  how_to_read: Glossary[]
  tokens: { n: number; median: number | null; mean: number | null; total: number | null }
}
