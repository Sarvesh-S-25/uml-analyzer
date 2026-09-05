export interface ModelInfo {
  spec: string
  provider: string
  model: string
  available: boolean
}

export interface PublicConfig {
  github_client_id: string
  github_configured: boolean
  llm_enabled: boolean
  llm_model: string
  available_models: ModelInfo[]
  default_gate_strategy: GateStrategy
  gate_strategies: GateStrategy[]
  max_versions: number
  association_scoring: boolean
  exact_token_counts: boolean
}

export type GateStrategy = 'always' | 'content' | 'structural' | 'isomorphism'

export interface ProjectSummary {
  name: string
  versions: number
  latest_version: number | null
  latest_score: number | null
  last_analysed: string | null
  file_count: number
  has_uml: boolean
}

export interface Repo {
  name: string
  full_name: string
  clone_url: string
  default_branch: string
  private: boolean
}

export interface TreeNode {
  path: string
  type: 'tree' | 'blob'
  size: number | null
  editable: boolean
}

export interface WorkspaceStats {
  files: number
  directories: number
  bytes: number
}

export interface FileContent {
  path: string
  content: string
  size: number
  modified_at: string
}

export interface UmlModelInfo {
  filename: string
  size: number
  modified_at: string
  active: boolean
}

export interface GraphNode {
  id: string
  label: string
  kind: string
  group: string
  status: string
  source_file?: string | null
}

export interface GraphLink {
  source: string
  target: string
  relation: string
}

export interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

export interface GateInfo {
  strategy: GateStrategy
  should_invoke_llm: boolean
  decision: string
  reason: string
  delta: {
    added_nodes: number
    removed_nodes: number
    changed_nodes: number
    added_edges: number
    removed_edges: number
    unchanged_nodes: number
  }
  impact_node_count: number
  isomorphic: boolean | null
  edit_distance: number | null
}

export interface LlmInfo {
  model: string
  provider?: string
  invoked: boolean
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  attempts: number
  degraded: boolean
  notes: string[]
}

export interface RuleViolation {
  rule: string
  file: string
  message: string
  evidence: string
  confidence: string
}

export interface ElementDifference {
  element_name: string
  missing_attributes: string[]
  missing_methods: string[]
  extra_attributes: string[]
  extra_methods: string[]
}

export interface RelationFinding {
  source: string
  target: string
  relation: string
  evidence: 'strong' | 'weak' | 'none'
  evidence_detail: string
  scored: boolean
  satisfied: boolean
}

export interface DifferenceModel {
  missing_classes: string[]
  extra_classes: string[]
  missing_relations: string[]
  unimplemented_associations: string[]
  relation_findings: RelationFinding[]
  element_differences: ElementDifference[]
  similarity_score: number
  checks_total: number
  checks_passed: number
  association_scoring: boolean
}

export interface UnitTest {
  target_file: string
  framework: string
  code: string
}

export interface CallResolution {
  total_call_sites: number
  resolved: number
  resolution_rate: number | null
  ambiguous: number
  external: number
  self: number
  field: number
  local: number
  static: number
  import: number
  same_file: number
  unique_global: number
  instantiation: number
}

export interface AnalysisResult {
  status: string
  version: number
  gate: GateInfo
  llm: LlmInfo
  reused_from_version: number | null
  renamed_components: Record<string, string>
  similarity_score: number
  similarity_score_rule_based: number
  similarity_score_source: string
  ai_gaps: string[]
  recommendations: string[]
  unit_tests: UnitTest[]
  rule_violations: RuleViolation[]
  difference: DifferenceModel
  graph_validation: {
    llm_node_count: number
    grounded_nodes: number
    grounded_node_ratio: number | null
    ungrounded_nodes: number
  }
  graph_data: GraphData
  networkx_nodes: number
  networkx_edges: number
  call_resolution: CallResolution
  uml: {
    filename: string | null
    error: string | null
    warnings: string[]
    element_count: number
    relation_count: number
  }
  source: {
    file_count: number
    parse_errors: string[]
    typescript_grammar: boolean
    files_without_types: string[]
  }
  elapsed_ms: number
}

export interface VersionRecord {
  version: number
  created_at: string
  parent_version: number | null
  reused_from: number | null
  similarity_score: number | null
  gap_count: number
  node_count: number
  edge_count: number
  gate: Partial<GateInfo>
  llm: Partial<LlmInfo>
}

export interface Metrics {
  total_runs: number
  reanalyses: number
  llm_calls: number
  cached_runs: number
  cache_hit_rate: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  baseline_total_tokens: number
  tokens_saved: number
  actual_cost_usd: number
  baseline_cost_usd: number
  cost_saved_usd: number
  mean_latency_ms_llm: number
  mean_latency_ms_cached: number
  latency_saved_ms: number
  by_strategy: Record<string, { runs: number; reanalyses: number; llm_calls: number }>
  similarity_scores: number[]
  score_variance: number | null
}

export interface RunRow {
  timestamp: string
  version: number
  gate_strategy: string
  gate_allowed_llm: boolean
  llm_invoked: boolean
  decision: string
  reason: string
  files_scanned: number
  changed_nodes: number
  impact_nodes: number
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  model: string
  similarity_score: number
  call_resolution_rate: number | null
}

export interface Benchmark {
  raw_tokens: number
  optimized_tokens: number
  token_reduction_percentage: number
  files_considered: number
  exact_token_counts: boolean
  note: string
}

export interface Spread {
  values: number[]
  mean: number
  stdev: number
  min: number
  max: number
  range: number
}

export interface ModelComparison {
  models: Array<{
    spec: string
    model?: string
    provider?: string
    invoked?: boolean
    similarity_score?: number
    gap_count?: number
    gaps?: string[]
    graph_nodes?: number
    grounded_node_ratio?: number | null
    prompt_tokens?: number
    completion_tokens?: number
    latency_ms?: number
    error?: string
  }>
  agreement: Array<{
    pair: [string, string]
    score_difference: number
    gap_jaccard: number | null
    graph_node_difference: number
  }>
  score_spread: Spread | null
  note: string
}
