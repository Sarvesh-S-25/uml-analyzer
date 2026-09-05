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
  miss_rate: number | null
  miss_low: number | null
  miss_high: number | null
  tokens: number
  tokens_saved: number | null
  percent_saved: number | null
  median_latency_ms: number | null
  is_baseline: boolean
  enough_runs: boolean
  reading: string
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

export interface Charts {
  skip_by_gate: { title: string; caption: string; data: SkipDatum[] }
  drift: { title: string; caption: string; data: DriftSeries[] }
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
