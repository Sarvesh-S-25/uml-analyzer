import type { AnalysisResult } from '../lib/types'
import { formatMs, statusStyle } from '../lib/theme'
import { Badge, Banner, Card, ScoreBar, Section, StatTile } from './ui'

/** What the check found.
 *
 * Organised by how much you can trust it, not by where it came from: the
 * structural differences are computed by parsing and are exact, and everything
 * the language model contributed is kept visibly separate and labelled as
 * suggestion. That separation is the honest presentation of a pipeline that is
 * part parser and part model.
 */

const EVIDENCE: Record<string, { color: string; glyph: string; word: string }> = {
  strong: { color: 'var(--good)', glyph: '✓', word: 'strong evidence' },
  weak: { color: 'var(--warning)', glyph: '~', word: 'weak evidence' },
  none: { color: 'var(--critical)', glyph: '✗', word: 'no evidence' },
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) return <p className="text-xs text-muted">{empty}</p>
  return (
    <ul className="space-y-1 text-sm text-ink-2">
      {items.map((item, index) => (
        <li key={index} className="flex gap-2">
          <span aria-hidden="true" className="text-muted">
            •
          </span>
          <span className="min-w-0 break-words font-mono text-xs">{item}</span>
        </li>
      ))}
    </ul>
  )
}

export function ConformanceReport({ result }: { result: AnalysisResult }) {
  const { gate, llm, difference, graph_validation: validation } = result
  const reused = !gate.should_invoke_llm
  const changedTotal =
    gate.delta.changed_nodes + gate.delta.added_nodes + gate.delta.removed_nodes

  return (
    <div className="space-y-4">
      {result.uml.error && (
        <Banner tone="critical" title="Your diagram could not be read">
          {result.uml.error} The score below therefore describes the code only — it is not a
          comparison against your diagram.
        </Banner>
      )}

      {result.uml.warnings.map((warning, index) => (
        <Banner key={index} tone="warning">
          {warning}
        </Banner>
      ))}

      {!result.uml.error && result.uml.element_count === 0 && (
        <Banner tone="warning" title="No diagram to compare against">
          Upload a StarUML .mdj file on the Diagram screen. Without one there is nothing to check
          the code against.
        </Banner>
      )}

      {result.source.parse_errors.length > 0 && (
        <Banner tone="warning" title="Some files did not parse">
          {result.source.parse_errors.slice(0, 5).join(', ')}
          {result.source.parse_errors.length > 5
            ? ` and ${result.source.parse_errors.length - 5} more`
            : ''}
          . Their contents are missing from the map and from the comparison.
        </Banner>
      )}

      {llm.degraded && (
        <Banner tone="warning" title="Ran without the language model">
          {llm.notes.join(' ')} The structural findings below are still exact; suggested tests and
          plain-English gaps are unavailable for this run.
        </Banner>
      )}

      <Card
        title={`Result — version ${result.version}`}
        subtitle={gate.reason}
        actions={
          <Badge
            color={reused ? 'var(--good)' : 'var(--series-1)'}
            wash={reused ? 'var(--good-wash)' : undefined}
            glyph={reused ? '=' : '↻'}
          >
            {reused ? 'Reused the previous answer' : 'Re-checked'}
          </Badge>
        }
      >
        <div className="mb-4">
          <ScoreBar value={result.similarity_score} />
          <p className="mt-1.5 text-xs text-muted">
            {result.similarity_score_source === 'cache'
              ? 'Carried over from the previous version, because nothing relevant changed. '
              : ''}
            The parser-only check, which uses no model at all, gives{' '}
            <span className="text-ink-2">{result.similarity_score_rule_based}%</span>.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile
            label="Classes in the map"
            value={result.networkx_nodes}
            detail={`${result.networkx_edges} relationships between them`}
          />
          <StatTile
            label="Changed since last time"
            value={changedTotal}
            detail={`${gate.impact_node_count} class(es) affected by those changes`}
            hint="What the gate looked at when deciding whether this run needed re-checking. It reads the code's structure only — never the diagram."
          />
          <StatTile
            label="Model called"
            value={llm.invoked ? 'yes' : 'no'}
            detail={
              llm.invoked
                ? `${llm.model} · ${llm.attempts} attempt(s)`
                : 'Answered from the parser and the stored version'
            }
            hint="The gate allowing a re-check and the model actually being reached are different facts; in offline mode the gate can allow a call that never happens."
          />
          <StatTile label="Took" value={formatMs(result.elapsed_ms)} detail="Wall clock" />
        </div>

        {validation.grounded_node_ratio !== null && (
          <p className="mt-4 text-xs leading-relaxed text-muted">
            Of the classes the model proposed for the map,{' '}
            <span className="text-ink-2">
              {validation.grounded_nodes} of {validation.llm_node_count} (
              {Math.round((validation.grounded_node_ratio ?? 0) * 100)}%)
            </span>{' '}
            were also found in the code by the parser. The rest are shown as{' '}
            {statusStyle('model_inferred').label.toLowerCase()} and are not corroborated.
          </p>
        )}

        {Object.keys(result.renamed_components).length > 0 && (
          <p className="mt-2 text-xs text-muted">
            {Object.keys(result.renamed_components).length} class(es) were renamed. The stored
            answer was relabelled rather than recomputed.
          </p>
        )}

        {result.call_resolution?.total_call_sites > 0 && (
          <p className="mt-2 text-xs leading-relaxed text-muted">
            Call resolution:{' '}
            <span className="text-ink-2">
              {result.call_resolution.resolved} of {result.call_resolution.total_call_sites} (
              {Math.round((result.call_resolution.resolution_rate ?? 0) * 100)}%)
            </span>{' '}
            were traced to exactly one definition; {result.call_resolution.ambiguous} were
            ambiguous and {result.call_resolution.external} pointed outside the project. An
            ambiguous call is counted and left unlinked, never linked to every candidate — linking
            to all of them would invent relationships that are not there.
          </p>
        )}

        {!result.source.typescript_grammar && result.source.files_without_types.length > 0 && (
          <p className="mt-2 text-xs text-muted">
            {result.source.files_without_types.length} TypeScript file(s) were read with the
            JavaScript grammar, so their type annotations are invisible. Install{' '}
            <code className="text-ink-2">tree-sitter-typescript</code> for full fidelity.
          </p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="Differences"
          subtitle="Found by reading the code and the diagram directly. These are exact — no model was involved."
        >
          <div className="space-y-4">
            <Section
              title="In the diagram, never built"
              count={difference.missing_classes.length}
              hint="Classes your diagram describes that do not exist in the code."
            >
              <List items={difference.missing_classes} empty="None — everything drawn exists." />
            </Section>

            <Section
              title="In the code, not in the diagram"
              count={difference.extra_classes.length}
              hint="Classes the code defines that were never drawn. Not necessarily wrong — but undocumented."
            >
              <List items={difference.extra_classes} empty="None — everything built is drawn." />
            </Section>

            <Section
              title="Missing inheritance"
              count={difference.missing_relations.length}
              hint="An 'extends' or 'implements' the diagram shows but the code does not have."
            >
              <List items={difference.missing_relations} empty="None." />
            </Section>

            {difference.relation_findings.length > 0 && (
              <Section title="Relationships" collapsible defaultOpen={false}>
                <p className="mb-2 text-xs leading-relaxed text-muted">
                  Inheritance can be recovered from the code exactly. An association cannot: a
                  typed field is strong evidence, a name match or an instantiation is weak.
                  Associations{' '}
                  <span className="text-ink-2">
                    {difference.association_scoring ? 'count' : 'do not count'}
                  </span>{' '}
                  toward the score in this run.
                </p>
                <ul className="space-y-1.5">
                  {difference.relation_findings.map((finding, index) => {
                    const evidence = EVIDENCE[finding.evidence]
                    return (
                      <li key={index} className="rounded border border-hairline p-2 text-xs">
                        <div className="flex items-start gap-2">
                          <span
                            aria-hidden="true"
                            className="mt-0.5 shrink-0 font-bold"
                            style={{ color: evidence.color }}
                          >
                            {evidence.glyph}
                          </span>
                          <div className="min-w-0">
                            <div className="font-mono text-ink-2">
                              {finding.source} →{finding.relation}→ {finding.target}
                            </div>
                            <div className="text-muted">
                              <span style={{ color: evidence.color }}>{evidence.word}</span>
                              {finding.scored ? ', counted' : ', not counted'} ·{' '}
                              {finding.evidence_detail}
                            </div>
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </Section>
            )}

            {difference.element_differences.length > 0 && (
              <Section
                title="Member differences"
                count={difference.element_differences.length}
                collapsible
                defaultOpen={false}
              >
                <ul className="space-y-2">
                  {difference.element_differences.slice(0, 20).map((element) => (
                    <li key={element.element_name} className="rounded border border-hairline p-2">
                      <div className="font-mono text-xs font-medium text-ink">
                        {element.element_name}
                      </div>
                      {element.missing_methods.length > 0 && (
                        <div className="mt-1 text-xs text-critical">
                          Not built: {element.missing_methods.join(', ')}
                        </div>
                      )}
                      {element.missing_attributes.length > 0 && (
                        <div className="text-xs text-critical">
                          Fields not built: {element.missing_attributes.join(', ')}
                        </div>
                      )}
                      {element.extra_methods.length > 0 && (
                        <div className="text-xs text-serious">
                          Not in the diagram: {element.extra_methods.join(', ')}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                {difference.element_differences.length > 20 && (
                  <p className="mt-2 text-xs text-muted">
                    Showing the first 20 of {difference.element_differences.length}.
                  </p>
                )}
              </Section>
            )}
          </div>
        </Card>

        <Card
          title="Observations"
          subtitle={
            llm.invoked
              ? 'Layering rules, plus the language model reading your design. Treat the model’s items as suggestions.'
              : 'Layering rules only — no model was called for this run.'
          }
        >
          <div className="space-y-4">
            <Section
              title="Layering problems"
              count={result.rule_violations.length}
              hint="A class reaching across a layer boundary it should not — for example a controller talking straight to a repository."
            >
              {result.rule_violations.length === 0 ? (
                <p className="text-xs text-muted">None found.</p>
              ) : (
                <ul className="space-y-1.5">
                  {result.rule_violations.map((violation, index) => (
                    <li
                      key={index}
                      className="rounded border p-2 text-xs"
                      style={{ borderColor: 'var(--warning)', background: 'var(--warning-wash)' }}
                    >
                      <div className="flex items-start gap-2">
                        <span
                          aria-hidden="true"
                          className="mt-0.5 shrink-0 font-bold text-warning"
                        >
                          !
                        </span>
                        <div className="min-w-0">
                          <div className="text-ink-2">{violation.message}</div>
                          <div className="mt-0.5 break-words font-mono text-[11px] text-muted">
                            {violation.file} · {violation.evidence} · {violation.confidence}
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
                title="Relationships with no evidence"
                count={difference.unimplemented_associations.length}
              >
                <List items={difference.unimplemented_associations} empty="None." />
              </Section>
            )}

            <Section
              title="Gaps the model noticed"
              count={result.ai_gaps.length}
              hint="Written by the language model, not verified by the parser. Read them as prompts to go and look, not as findings."
            >
              <List items={result.ai_gaps} empty="None reported." />
            </Section>

            <Section title="Suggestions" count={result.recommendations.length}>
              <List items={result.recommendations} empty="None." />
            </Section>
          </div>
        </Card>
      </div>

      {result.unit_tests.length > 0 && (
        <Card
          title="Suggested tests"
          subtitle="Written by the language model. Read them before you commit them — they are drafts, not verified tests."
        >
          <div className="space-y-3">
            {result.unit_tests.map((test, index) => (
              <div key={index} className="overflow-hidden rounded-lg border border-hairline">
                <div className="flex items-center justify-between border-b border-hairline bg-surface-2 px-3 py-1.5 text-xs">
                  <span className="break-all font-mono text-ink-2">{test.target_file}</span>
                  <span className="uppercase text-muted">{test.framework}</span>
                </div>
                <pre className="overflow-x-auto bg-plane p-3 font-mono text-xs text-ink-2">
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
