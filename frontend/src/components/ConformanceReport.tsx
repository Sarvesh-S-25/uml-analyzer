import { useMemo, useState } from 'react'
import type { AnalysisResult } from '../lib/types'
import { formatMs } from '../lib/theme'
import { Badge, Banner, Card } from './ui'

type Presence = 'yes' | 'no' | 'unknown'
type FindingSource = 'parser' | 'model'

interface DifferenceRow {
  id: string
  element: string
  detail: string
  category: 'Class' | 'Member' | 'Relationship' | 'Architecture' | 'Observation'
  code: Presence
  diagram: Presence
  source: FindingSource
  evidence: string
  sourceFile?: string
  suggestion: string
}

const CATEGORY_TONE: Record<DifferenceRow['category'], { color: string; wash: string }> = {
  Class: { color: 'var(--critical)', wash: 'var(--critical-wash)' },
  Member: { color: 'var(--serious)', wash: 'var(--serious-wash)' },
  Relationship: { color: 'var(--warning)', wash: 'var(--warning-wash)' },
  Architecture: { color: 'var(--proposed)', wash: 'var(--proposed-wash)' },
  Observation: { color: 'var(--neutral)', wash: 'var(--surface-2)' },
}

function PresenceMark({ value }: { value: Presence }) {
  if (value === 'yes') {
    return <span className="inline-flex items-center gap-1 text-xs text-good"><b>✓</b> Yes</span>
  }
  if (value === 'no') {
    return <span className="inline-flex items-center gap-1 text-xs text-critical"><b>×</b> No</span>
  }
  return <span className="text-xs text-muted">—</span>
}

function CategoryChip({ category }: { category: DifferenceRow['category'] }) {
  const tone = CATEGORY_TONE[category]
  return (
    <span
      className="inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium"
      style={{ color: tone.color, background: tone.wash }}
    >
      {category}
    </span>
  )
}

function buildRows(result: AnalysisResult): DifferenceRow[] {
  const { difference } = result
  const rows: DifferenceRow[] = []
  const sourceFileFor = (name: string) =>
    result.graph_data.nodes.find((node) => node.label === name && node.source_file)?.source_file ?? undefined

  difference.missing_classes.forEach((name, index) => {
    rows.push({
      id: `missing-code-${index}-${name}`,
      element: name,
      detail: 'Missing from code',
      category: 'Class',
      code: 'no',
      diagram: 'yes',
      source: 'parser',
      evidence: `The StarUML model defines “${name}”, but the source parser found no class or interface with that name.`,
      suggestion: 'Implement the class, or remove it from the diagram if it is no longer part of the intended design.',
    })
  })

  difference.extra_classes.forEach((name, index) => {
    const sourceFile = sourceFileFor(name)
    rows.push({
      id: `not-diagrammed-${index}-${name}`,
      element: name,
      detail: 'Not in diagram',
      category: 'Class',
      code: 'yes',
      diagram: 'no',
      source: 'parser',
      evidence: sourceFile
        ? `The parser found “${name}” in ${sourceFile}, but no matching element exists in the StarUML model.`
        : `The parser found “${name}” in the source, but no matching element exists in the StarUML model.`,
      sourceFile,
      suggestion: 'Add the class to the diagram, or remove it from the code if it is unintended.',
    })
  })

  difference.missing_relations.forEach((relation, index) => {
    rows.push({
      id: `missing-relation-${index}`,
      element: relation,
      detail: 'Relationship not implemented',
      category: 'Relationship',
      code: 'no',
      diagram: 'yes',
      source: 'parser',
      evidence: 'The relationship is present in the diagram, but the structural parser could not corroborate it in the source.',
      suggestion: 'Implement the relationship in code, or update the diagram to reflect the current design.',
    })
  })

  difference.unimplemented_associations.forEach((relation, index) => {
    rows.push({
      id: `association-${index}`,
      element: relation,
      detail: 'No association evidence',
      category: 'Relationship',
      code: 'unknown',
      diagram: 'yes',
      source: 'parser',
      evidence: 'The diagram contains this association, but the parser found no strong or weak implementation evidence.',
      suggestion: 'Check the involved fields and calls, then decide whether the association or the implementation should change.',
    })
  })

  difference.element_differences.forEach((element, index) => {
    const parts = [
      element.missing_methods.length > 0 ? `methods missing from code: ${element.missing_methods.join(', ')}` : '',
      element.missing_attributes.length > 0 ? `fields missing from code: ${element.missing_attributes.join(', ')}` : '',
      element.extra_methods.length > 0 ? `methods not in diagram: ${element.extra_methods.join(', ')}` : '',
      element.extra_attributes.length > 0 ? `fields not in diagram: ${element.extra_attributes.join(', ')}` : '',
    ].filter(Boolean)
    rows.push({
      id: `member-${index}-${element.element_name}`,
      element: element.element_name,
      detail: 'Member mismatch',
      category: 'Member',
      code: 'yes',
      diagram: 'yes',
      source: 'parser',
      evidence: parts.join('; '),
      sourceFile: sourceFileFor(element.element_name),
      suggestion: 'Align the class fields and methods with the intended StarUML definition.',
    })
  })

  result.rule_violations.forEach((violation, index) => {
    rows.push({
      id: `rule-${index}`,
      element: violation.rule,
      detail: violation.message,
      category: 'Architecture',
      code: 'yes',
      diagram: 'unknown',
      source: 'parser',
      evidence: `${violation.evidence} (${violation.confidence} confidence)`,
      sourceFile: violation.file,
      suggestion: 'Review this dependency against the intended layer boundaries before changing the design or source.',
    })
  })

  result.ai_gaps.forEach((gap, index) => {
    rows.push({
      id: `model-${index}`,
      element: `Model observation ${index + 1}`,
      detail: gap,
      category: 'Observation',
      code: 'unknown',
      diagram: 'unknown',
      source: 'model',
      evidence: 'Suggested by the configured language model; this item is not parser-verified.',
      suggestion: 'Inspect the relevant code and diagram before acting on this suggestion.',
    })
  })

  return rows
}

function DifferenceWorkbench({ result }: { result: AnalysisResult }) {
  const rows = useMemo(() => buildRows(result), [result])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [source, setSource] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = rows.filter((row) => {
    const query = search.trim().toLowerCase()
    return (
      (category === 'all' || row.category === category) &&
      (source === 'all' || row.source === source) &&
      (!query || `${row.element} ${row.detail} ${row.evidence}`.toLowerCase().includes(query))
    )
  })
  const selected = rows.find((row) => row.id === selectedId) ?? filtered[0] ?? rows[0]

  return (
    <section className="overflow-hidden rounded-md border border-hairline bg-surface shadow-[var(--shadow-card)]">
      <div className="border-b border-hairline px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-md font-semibold text-ink">Differences</h2>
            <p className="mt-0.5 text-xs text-muted">Parser findings and model observations remain clearly separated.</p>
          </div>
          <span className="text-xs tabular-nums text-muted">{filtered.length} of {rows.length}</span>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-[10rem_9rem_minmax(12rem,1fr)]">
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            aria-label="Filter by difference type"
            className="rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-xs text-ink"
          >
            <option value="all">All difference types</option>
            <option value="Class">Classes</option>
            <option value="Member">Members</option>
            <option value="Relationship">Relationships</option>
            <option value="Architecture">Architecture</option>
            <option value="Observation">Observations</option>
          </select>
          <select
            value={source}
            onChange={(event) => setSource(event.target.value)}
            aria-label="Filter by source"
            className="rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-xs text-ink"
          >
            <option value="all">All sources</option>
            <option value="parser">Parser verified</option>
            <option value="model">Model suggested</option>
          </select>
          <label className="relative">
            <span aria-hidden="true" className="absolute left-2.5 top-1.5 text-xs text-muted">⌕</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search findings…"
              className="w-full rounded-md border border-hairline bg-surface py-1.5 pl-7 pr-2.5 text-xs text-ink placeholder:text-muted"
            />
          </label>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <div className="text-lg text-good">✓</div>
          <h3 className="mt-1 text-sm font-semibold text-ink">No differences found</h3>
          <p className="mt-1 text-xs text-muted">The parser found no structural mismatches in this result.</p>
        </div>
      ) : (
        <div className="grid min-h-[28rem] xl:grid-cols-[minmax(0,1.55fr)_minmax(20rem,1fr)]">
          <div className="min-w-0 overflow-x-auto border-b border-hairline xl:border-b-0 xl:border-r">
            <table className="w-full min-w-[46rem] text-left text-xs">
              <thead className="bg-surface-2 text-[10px] uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Element</th>
                  <th className="w-28 px-3 py-2 font-medium">In code</th>
                  <th className="w-28 px-3 py-2 font-medium">In diagram</th>
                  <th className="w-28 px-3 py-2 font-medium">Category</th>
                  <th className="w-28 px-3 py-2 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => {
                  const active = selected?.id === row.id
                  return (
                    <tr
                      key={row.id}
                      onClick={() => setSelectedId(row.id)}
                      className={`cursor-pointer border-t border-hairline transition ${
                        active ? 'bg-series-1/8' : 'hover:bg-surface-2'
                      }`}
                    >
                      <td className={`relative px-3 py-2.5 ${active ? 'before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-series-1' : ''}`}>
                        <div className="max-w-md truncate font-medium text-ink" title={row.element}>{row.element}</div>
                        <div className="mt-0.5 max-w-md truncate text-[11px] text-muted" title={row.detail}>{row.detail}</div>
                      </td>
                      <td className="px-3 py-2.5"><PresenceMark value={row.code} /></td>
                      <td className="px-3 py-2.5"><PresenceMark value={row.diagram} /></td>
                      <td className="px-3 py-2.5"><CategoryChip category={row.category} /></td>
                      <td className="px-3 py-2.5">
                        <span className={row.source === 'parser' ? 'text-good' : 'text-proposed'}>
                          {row.source === 'parser' ? '✓ Parser' : '◇ Model'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="px-5 py-10 text-center text-xs text-muted">No findings match these filters.</div>
            )}
          </div>

          {selected && (
            <aside className="min-w-0 bg-surface px-4 py-4" aria-label="Difference details">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">Difference details</p>
                  <h3 className="mt-1 break-words text-lg font-semibold text-ink">{selected.element}</h3>
                  <p className="mt-1 text-xs text-critical">{selected.detail}</p>
                </div>
                <CategoryChip category={selected.category} />
              </div>

              <dl className="mt-4 divide-y divide-hairline border-y border-hairline text-xs">
                <div className="grid grid-cols-[6rem_1fr] gap-2 py-2">
                  <dt className="text-muted">Found in code</dt>
                  <dd><PresenceMark value={selected.code} /></dd>
                </div>
                <div className="grid grid-cols-[6rem_1fr] gap-2 py-2">
                  <dt className="text-muted">Found in diagram</dt>
                  <dd><PresenceMark value={selected.diagram} /></dd>
                </div>
                <div className="grid grid-cols-[6rem_1fr] gap-2 py-2">
                  <dt className="text-muted">Source</dt>
                  <dd className={selected.source === 'parser' ? 'text-good' : 'text-proposed'}>
                    {selected.source === 'parser' ? 'Parser verified' : 'Model suggested'}
                  </dd>
                </div>
                {selected.sourceFile && (
                  <div className="grid grid-cols-[6rem_1fr] gap-2 py-2">
                    <dt className="text-muted">Code location</dt>
                    <dd className="break-all font-mono text-[11px] text-series-1">{selected.sourceFile}</dd>
                  </div>
                )}
              </dl>

              <div className="mt-4">
                <h4 className="text-xs font-semibold text-ink">Evidence</h4>
                <div className="mt-1.5 rounded-md border border-hairline bg-plane p-3 text-xs leading-relaxed text-ink-2">
                  {selected.evidence}
                </div>
              </div>

              <div className="mt-4">
                <h4 className="text-xs font-semibold text-ink">Suggested action</h4>
                <div className="mt-1.5 rounded-md border border-warning/40 bg-warning-wash p-3 text-xs leading-relaxed text-ink-2">
                  {selected.suggestion}
                </div>
              </div>

              <p className="mt-4 text-[11px] leading-relaxed text-muted">
                {selected.source === 'parser'
                  ? 'This finding comes from the deterministic structural comparison.'
                  : 'Treat this model output as a review prompt, not a verified defect.'}
              </p>
            </aside>
          )}
        </div>
      )}
    </section>
  )
}

export function ConformanceReport({ result }: { result: AnalysisResult }) {
  const { gate, llm, difference, graph_validation: validation } = result
  const reused = !gate.should_invoke_llm
  const valid = result.evaluation?.valid ?? (result.uml.element_count > 0 && result.source.file_count > 0)
  const changedTotal = gate.delta.changed_nodes + gate.delta.added_nodes + gate.delta.removed_nodes
  const differenceCount =
    difference.missing_classes.length +
    difference.extra_classes.length +
    difference.missing_relations.length +
    difference.unimplemented_associations.length +
    difference.element_differences.length

  return (
    <div className="space-y-4">
      {!result.evaluation && (
        <Banner tone="warning" title="Result from an earlier analyzer version">
          Force a full re-check to apply the corrected language support, input validation and structural scoring.
        </Banner>
      )}
      {result.uml.error && (
        <Banner tone="critical" title="Your diagram could not be read">
          {result.uml.error} This result cannot be treated as a code-to-diagram comparison.
        </Banner>
      )}
      {result.uml.warnings.map((warning, index) => <Banner key={index} tone="warning">{warning}</Banner>)}
      {!result.uml.error && result.uml.element_count === 0 && (
        <Banner tone="warning" title="No diagram to compare against">
          Upload a StarUML .mdj file on the Diagram screen. Without one there is nothing to compare.
        </Banner>
      )}
      {result.source.parse_errors.length > 0 && (
        <Banner tone="warning" title="Some files did not parse">
          {result.source.parse_errors.slice(0, 5).join(', ')}
          {result.source.parse_errors.length > 5 ? ` and ${result.source.parse_errors.length - 5} more` : ''}.
          Their contents are missing from the map and comparison.
        </Banner>
      )}
      {llm.degraded && (
        <Banner tone="warning" title="Ran without the language model">
          {llm.notes.join(' ')} Structural findings remain available, but model observations are unavailable.
        </Banner>
      )}

      <Card dense>
        {valid ? (
          <div>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-semibold tabular-nums text-ink">{result.similarity_score_rule_based}%</span>
                  <span className="text-md font-semibold text-ink">structural match</span>
                </div>
                <p className="mt-1 text-xs text-muted">
                  Passed {difference.checks_passed} of {difference.checks_total} parser checks · version {result.version}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge color="var(--good)" wash="var(--good-wash)" glyph="✓">Parser verified</Badge>
                <Badge
                  color={llm.invoked ? 'var(--proposed)' : 'var(--neutral)'}
                  wash={llm.invoked ? 'var(--proposed-wash)' : 'var(--surface-2)'}
                  glyph={llm.invoked ? '◇' : '—'}
                >
                  {llm.invoked ? `${llm.model} used` : 'Model not called'}
                </Badge>
                <Badge color={reused ? 'var(--good)' : 'var(--series-1)'} glyph={reused ? '=' : '↻'}>
                  {reused ? 'Reused' : 'Re-checked'}
                </Badge>
              </div>
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-surface-3">
              <div
                className="h-full rounded-full bg-series-1"
                style={{ width: `${Math.max(0, Math.min(100, result.similarity_score_rule_based))}%` }}
              />
            </div>
            <dl className="mt-4 grid grid-cols-2 divide-x divide-hairline border-t border-hairline pt-3 sm:grid-cols-4">
              <div className="px-3 first:pl-0">
                <dt className="text-[10px] uppercase tracking-wide text-muted">Classes</dt>
                <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{result.source_class_count ?? '—'}</dd>
              </div>
              <div className="px-3">
                <dt className="text-[10px] uppercase tracking-wide text-muted">Relationships</dt>
                <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{result.networkx_edges}</dd>
              </div>
              <div className="px-3">
                <dt className="text-[10px] uppercase tracking-wide text-muted">Differences</dt>
                <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{differenceCount}</dd>
              </div>
              <div className="px-3">
                <dt className="text-[10px] uppercase tracking-wide text-muted">Analysis time</dt>
                <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{formatMs(result.elapsed_ms)}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <Banner tone="warning" title="Cannot evaluate">
            {result.evaluation?.issues.join(' ') || 'A usable class diagram and supported source code are required.'}
          </Banner>
        )}
      </Card>

      {valid && <DifferenceWorkbench result={result} />}

      <details className="group rounded-md border border-hairline bg-surface shadow-[var(--shadow-card)]">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div>
            <span className="text-sm font-semibold text-ink">Analysis details</span>
            <span className="ml-2 text-xs text-muted">Relationship evidence, recommendations, and model diagnostics</span>
          </div>
          <span aria-hidden="true" className="text-muted transition group-open:rotate-90">›</span>
        </summary>
        <div className="grid gap-5 border-t border-hairline p-4 lg:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Relationship evidence</h3>
            {difference.relation_findings.length === 0 ? (
              <p className="mt-2 text-xs text-muted">No modelled relationships to report.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {difference.relation_findings.map((finding, index) => (
                  <li key={index} className="rounded-md border border-hairline bg-plane p-2.5 text-xs">
                    <div className="break-words font-mono text-ink-2">
                      {finding.source} →{finding.relation}→ {finding.target}
                    </div>
                    <div className="mt-1 text-muted">
                      {finding.evidence} evidence · {finding.scored ? 'counted' : 'not counted'} · {finding.evidence_detail}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Recommendations</h3>
            {result.recommendations.length === 0 ? (
              <p className="mt-2 text-xs text-muted">No recommendations returned.</p>
            ) : (
              <ul className="mt-2 space-y-2 text-xs text-ink-2">
                {result.recommendations.map((item, index) => (
                  <li key={index} className="flex gap-2"><span className="text-proposed">◇</span><span>{item}</span></li>
                ))}
              </ul>
            )}
            <dl className="mt-4 grid grid-cols-2 gap-3 rounded-md bg-plane p-3 text-xs">
              <div><dt className="text-muted">Changed nodes</dt><dd className="mt-0.5 font-medium tabular-nums text-ink">{changedTotal}</dd></div>
              <div><dt className="text-muted">Impact set</dt><dd className="mt-0.5 font-medium tabular-nums text-ink">{gate.impact_node_count}</dd></div>
              <div><dt className="text-muted">Call resolution</dt><dd className="mt-0.5 font-medium tabular-nums text-ink">{result.call_resolution.resolution_rate === null ? '—' : `${Math.round(result.call_resolution.resolution_rate * 100)}%`}</dd></div>
              <div><dt className="text-muted">Grounded model nodes</dt><dd className="mt-0.5 font-medium tabular-nums text-ink">{validation.grounded_node_ratio === null ? '—' : `${Math.round(validation.grounded_node_ratio * 100)}%`}</dd></div>
            </dl>
          </div>
        </div>
      </details>

      {result.unit_tests.length > 0 && (
        <Card title="Suggested tests" subtitle="Model-generated drafts. Review them before using them.">
          <div className="space-y-3">
            {result.unit_tests.map((test, index) => (
              <div key={index} className="overflow-hidden rounded-lg border border-hairline">
                <div className="flex items-center justify-between border-b border-hairline bg-surface-2 px-3 py-1.5 text-xs">
                  <span className="break-all font-mono text-ink-2">{test.target_file}</span>
                  <span className="uppercase text-muted">{test.framework}</span>
                </div>
                <pre className="overflow-x-auto bg-plane p-3 font-mono text-xs text-ink-2"><code>{test.code}</code></pre>
              </div>
            ))}
          </div>
        </Card>
      )}

      {!result.source.typescript_grammar && result.source.files_without_types.length > 0 && (
        <Banner tone="warning">
          {result.source.files_without_types.length} TypeScript file(s) were parsed without type annotations because the TypeScript grammar is unavailable.
        </Banner>
      )}
    </div>
  )
}
