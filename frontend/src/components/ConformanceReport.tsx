import type { AnalysisResult } from '../lib/types'
import { formatMs, statusStyle } from '../lib/theme'
import { Badge, Banner, Card, Section, StatTile } from './ui'

// These read the same custom properties index.css defines (and lib/theme.ts's
// STATUS_STYLES draws its "conforming"/"missing" colours from) rather than
// re-declaring their own hex values, which had quietly drifted to a
// different green/red than the rest of the app.
function scoreTone(score: number): string {
  if (score >= 90) return 'var(--color-good)'
  if (score >= 70) return 'var(--color-warning)'
  return 'var(--color-critical)'
}

const EVIDENCE_COLORS: Record<string, string> = {
  strong: 'var(--color-good)',
  weak: 'var(--color-warning)',
  none: 'var(--color-critical)',
}

const EVIDENCE_GLYPHS: Record<string, string> = {
  strong: '✓',
  weak: '~',
  none: '✗',
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="text-xs text-muted">{empty}</p>
  return (
    <ul className="space-y-1.5 text-sm text-ink-2">
      {items.map((item, index) => (
        <li key={index} className="flex gap-2">
          <span aria-hidden="true" className="text-muted">
            •
          </span>
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  )
}

export function ConformanceReport({ result }: { result: AnalysisResult }) {
  const { gate, llm, difference, graph_validation: validation } = result
  const reused = !gate.should_invoke_llm

  return (
    <div className="space-y-4">
      {result.uml.error && (
        <Banner tone="critical" title="The UML model could not be read">
          {result.uml.error} The conformance score below therefore reflects the code only — it is
          not a comparison against your diagram.
        </Banner>
      )}

      {result.uml.warnings.map((warning, index) => (
        <Banner key={index} tone="warning">
          {warning}
        </Banner>
      ))}

      {!result.uml.error && result.uml.element_count === 0 && (
        <Banner tone="warning" title="No design model">
          No StarUML diagram has been uploaded, so there is nothing to compare the code against.
        </Banner>
      )}

      {result.source.parse_errors.length > 0 && (
        <Banner tone="warning" title="Some files did not parse cleanly">
          {result.source.parse_errors.slice(0, 5).join(', ')}
          {result.source.parse_errors.length > 5
            ? ` and ${result.source.parse_errors.length - 5} more`
            : ''}
          . Their contents are excluded from the graph.
        </Banner>
      )}

      {llm.degraded && (
        <Banner tone="warning" title="Ran without the language model">
          {llm.notes.join(' ')} Structural findings are still exact; generated tests and
          natural-language gaps are unavailable for this run.
        </Banner>
      )}

      <Card
        title={`Conformance report — version ${result.version}`}
        subtitle={gate.reason}
        actions={
          <Badge
            color={reused ? '#199e70' : '#3987e5'}
            glyph={reused ? '=' : '↻'}
          >
            {reused ? 'Reused cached analysis' : 'Re-analysed'}
          </Badge>
        }
      >
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile
            label={
              result.similarity_score_source === 'cache'
                ? 'Similarity (from cache)'
                : 'Similarity score'
            }
            value={`${result.similarity_score}%`}
            tone={scoreTone(result.similarity_score)}
            detail={`Rule-based check: ${result.similarity_score_rule_based}%`}
          />
          <StatTile
            label="Graph size"
            value={`${result.networkx_nodes}`}
            detail={`${result.networkx_edges} edges`}
          />
          <StatTile
            label="Changed since last run"
            value={`${gate.delta.changed_nodes + gate.delta.added_nodes + gate.delta.removed_nodes}`}
            detail={`${gate.impact_node_count} in the impact set`}
          />
          <StatTile
            label="Elapsed"
            value={formatMs(result.elapsed_ms)}
            detail={llm.invoked ? `${llm.model} · ${llm.attempts} attempt(s)` : llm.model}
          />
        </div>

        {validation.grounded_node_ratio !== null && (
          <p className="mt-4 text-xs text-muted">
            Model-proposed graph nodes matched to parsed code:{' '}
            <span className="text-ink-2">
              {validation.grounded_nodes}/{validation.llm_node_count} (
              {Math.round((validation.grounded_node_ratio ?? 0) * 100)}%)
            </span>
            . The remainder appear as {statusStyle('model_inferred').label.toLowerCase()} nodes and
            are not corroborated by the parser.
          </p>
        )}

        {Object.keys(result.renamed_components).length > 0 && (
          <p className="mt-2 text-xs text-muted">
            {Object.keys(result.renamed_components).length} component(s) were renamed; the cached
            analysis was relabelled rather than regenerated.
          </p>
        )}

        {result.call_resolution?.total_call_sites > 0 && (
          <p className="mt-2 text-xs text-muted">
            Call resolution:{' '}
            <span className="text-ink-2">
              {result.call_resolution.resolved}/{result.call_resolution.total_call_sites} (
              {Math.round((result.call_resolution.resolution_rate ?? 0) * 100)}%)
            </span>{' '}
            attributed to a single definition; {result.call_resolution.ambiguous} ambiguous,{' '}
            {result.call_resolution.external} external. Unresolved calls are left unlinked rather
            than linked to every candidate, so the impact set stays tight.
          </p>
        )}

        {!result.source.typescript_grammar && result.source.files_without_types.length > 0 && (
          <p className="mt-2 text-xs text-muted">
            {result.source.files_without_types.length} TypeScript file(s) were parsed with the
            JavaScript grammar, so their type annotations are invisible. Install{' '}
            <code className="text-ink-2">tree-sitter-typescript</code> for full fidelity.
          </p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title="Structural differences"
          subtitle="Computed by parsing, not by the model — these are exact."
        >
          <div className="space-y-4">
            <Section title={`Designed but not implemented (${difference.missing_classes.length})`}>
              <List items={difference.missing_classes} empty="None." />
            </Section>
            <Section title={`In code but not in the diagram (${difference.extra_classes.length})`}>
              <List items={difference.extra_classes} empty="None." />
            </Section>
            <Section title={`Missing inheritance (${difference.missing_relations.length})`}>
              <List items={difference.missing_relations} empty="None." />
            </Section>

            {difference.relation_findings.length > 0 && (
              <Section title="Modelled relationships">
                <p className="mb-2 text-xs text-muted">
                  Inheritance is recoverable exactly from the code. An association is not — a
                  typed field is strong evidence, a name match or an instantiation is weak.
                  Associations {difference.association_scoring ? 'count' : 'do not count'} toward
                  the score in this run.
                </p>
                <ul className="space-y-1.5">
                  {difference.relation_findings.map((finding, index) => (
                    <li key={index} className="rounded border border-hairline p-2.5 text-xs">
                      <div className="flex items-start gap-2">
                        <span
                          aria-hidden="true"
                          className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-plane"
                          style={{ background: EVIDENCE_COLORS[finding.evidence] }}
                        >
                          {EVIDENCE_GLYPHS[finding.evidence]}
                        </span>
                        <div className="min-w-0">
                          <div className="text-ink-2">
                            {finding.source} —{finding.relation}→ {finding.target}
                            <span className="ml-2 text-muted">
                              {finding.evidence} evidence
                              {finding.scored ? ', scored' : ', not scored'}
                            </span>
                          </div>
                          <div className="text-muted">{finding.evidence_detail}</div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {difference.element_differences.length > 0 && (
              <Section title="Member-level differences">
                <ul className="space-y-2 text-sm">
                  {difference.element_differences.slice(0, 20).map((element) => (
                    <li key={element.element_name} className="rounded border border-hairline p-2.5">
                      <div className="font-medium text-ink">{element.element_name}</div>
                      {element.missing_methods.length > 0 && (
                        <div className="mt-1 text-xs text-ink-2">
                          Missing methods: {element.missing_methods.join(', ')}
                        </div>
                      )}
                      {element.missing_attributes.length > 0 && (
                        <div className="text-xs text-ink-2">
                          Missing attributes: {element.missing_attributes.join(', ')}
                        </div>
                      )}
                      {element.extra_methods.length > 0 && (
                        <div className="text-xs text-muted">
                          Undocumented methods: {element.extra_methods.join(', ')}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
          </div>
        </Card>

        <Card
          title="Findings"
          subtitle={
            llm.invoked
              ? 'Layering heuristics plus the model’s reading of the design.'
              : 'Layering heuristics only — no model was called for this run.'
          }
        >
          <div className="space-y-4">
            <Section title={`Layering violations (${result.rule_violations.length})`}>
              {result.rule_violations.length === 0 ? (
                <p className="text-xs text-muted">None detected.</p>
              ) : (
                <ul className="space-y-2">
                  {result.rule_violations.map((violation, index) => (
                    <li key={index} className="rounded border border-warning/40 p-2.5 text-sm">
                      <div className="flex items-start gap-2">
                        <span
                          aria-hidden="true"
                          className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-warning text-[10px] font-bold text-plane"
                        >
                          !
                        </span>
                        <div className="min-w-0">
                          <div className="text-ink-2">{violation.message}</div>
                          <div className="mt-0.5 text-xs text-muted break-words">
                            {violation.file} · evidence: {violation.evidence} ·{' '}
                            {violation.confidence}
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            {difference.unimplemented_associations.length > 0 && (
              <Section
                title={`Associations without evidence (${difference.unimplemented_associations.length})`}
              >
                <List items={difference.unimplemented_associations} empty="None." />
              </Section>
            )}

            <Section title={`Gaps (${result.ai_gaps.length})`}>
              <List items={result.ai_gaps} empty="No gaps reported." />
            </Section>

            <Section title={`Recommendations (${result.recommendations.length})`}>
              <List items={result.recommendations} empty="No recommendations." />
            </Section>
          </div>
        </Card>
      </div>

      {result.unit_tests.length > 0 && (
        <Card
          title={`Generated unit tests (${result.unit_tests.length})`}
          subtitle="Produced by the language model. Review before committing — they are suggestions, not verified tests."
        >
          <div className="space-y-3">
            {result.unit_tests.map((test, index) => (
              <div key={index} className="rounded-lg border border-hairline">
                <div className="flex items-center justify-between border-b border-hairline px-3 py-2 text-xs">
                  <span className="text-ink-2 break-all">{test.target_file}</span>
                  <span className="text-muted uppercase">{test.framework}</span>
                </div>
                <pre className="overflow-x-auto bg-plane p-3 text-xs text-ink-2">
                  <code>{test.code}</code>
                </pre>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
