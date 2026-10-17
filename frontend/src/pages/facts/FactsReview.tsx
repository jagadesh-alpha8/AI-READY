import React, { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listSprintFacts, confirmFact, correctFact, rejectFact, requestFactEvidence, reviewFactMapping } from '../../api/facts';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Fact } from '../../types';
import { FileSearch, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters, matchesSearch, optionsFrom } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';

export const FactsReview: React.FC = () => {
  const { step, can } = useAccess();
  const canReview = can('facts.review');
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: factsData,
    loading,
    error,
    refetch,
  } = useApiResource<Fact[]>(() => listSprintFacts(sprintId!), [sprintId], isRealSprint);
  const facts = factsData || [];

  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [correctionValue, setCorrectionValue] = useState('');
  const [actionError, setActionError] = useState('');
  const [actingOnId, setActingOnId] = useState<string | null>(null);

  // Filters (client-side: the full fact list is already loaded).
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [pillarFilter, setPillarFilter] = useState('');
  const [criterionFilter, setCriterionFilter] = useState('');
  const [mappingFilter, setMappingFilter] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [confidenceFilter, setConfidenceFilter] = useState('');
  const filteredFacts = useMemo(
    () => facts.filter((fact) =>
      (!statusFilter || fact.status === statusFilter)
      && (!pillarFilter || (fact.pillar_label || fact.pillar || '') === pillarFilter)
      && (!criterionFilter || fact.aiqif_mappings.some((m) => m.criterion === criterionFilter))
      && (!mappingFilter || fact.aiqif_mapping_status === mappingFilter)
      && (!ownerFilter || (fact.owner_role || '') === ownerFilter)
      && (!sourceFilter || (fact.source_document_filename || '') === sourceFilter)
      && (!confidenceFilter || confidenceBand(fact.confidence) === confidenceFilter)
      && matchesSearch(
        search, fact.audit_field_id, fact.field_name, fact.value, fact.source_snippet, fact.source_document_filename,
        ...fact.aiqif_mappings.flatMap((m) => [m.indicator_code, m.indicator_name]),
      )),
    [facts, search, statusFilter, pillarFilter, criterionFilter, mappingFilter, ownerFilter, sourceFilter,
      confidenceFilter],
  );
  const criterionGroups = useMemo(() => aiqifCriterionGroups(facts), [facts]);

  const handleConfirm = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await confirmFact(factId);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to confirm fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleMappingReview = async (factId: string, code: string, decision: 'confirm' | 'reject') => {
    setActingOnId(factId);
    setActionError('');
    try {
      await reviewFactMapping(factId, code, decision);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to save the AI-QIF tag decision.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleCorrectSubmit = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await correctFact(factId, correctionValue);
      setEditingFactId(null);
      setCorrectionValue('');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to correct fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleReject = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await rejectFact(factId);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to reject fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleRequestEvidence = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await requestFactEvidence(factId);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to request evidence.'));
    } finally {
      setActingOnId(null);
    }
  };

  const statusBadgeClass = (status: Fact['status']) => {
    switch (status) {
      case 'confirmed': return 'badge-success';
      case 'corrected': return 'badge-brand';
      case 'rejected': return 'badge-danger';
      case 'evidence_requested': return 'badge-accent';
      default: return 'badge-warning';
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <FileSearch className="w-5 h-5 text-brand-800" /> Step {step('sprint-facts')}: Extracted Facts Review
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Review candidate facts extracted by AIOS. Confirm, correct, or reject values with complete source snippet lineage.
            </p>
          </div>
          <button onClick={() => navigate(`/sprint/${sprintId}/gaps`)} className="btn-primary shrink-0">
            <span>Proceed to Gap Dashboard</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {/* Facts Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Candidate & Extracted Fact Records</h2>
          <span className="text-xs text-ink-500">{facts.length} facts registered</span>
        </div>

        {loading ? (
          <LoadingState message="Loading extracted facts..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : facts.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No facts extracted yet. Seed facts or run extraction.</p>
            <button
              onClick={() => setActionError(
                'Demo fact seeding is disabled: facts are only ever created by the extraction pipeline, never fabricated.',
              )}
              className="btn-primary btn-sm mt-3"
            >
              Seed Sample Facts
            </button>
          </div>
        ) : (
          <>
          <AIQIFCriterionStrip
            groups={criterionGroups}
            facts={facts}
            criterion={criterionFilter}
            mapping={mappingFilter}
            onCriterion={(value) => { setCriterionFilter(value); setMappingFilter(''); }}
            onMapping={(value) => { setMappingFilter(value); setCriterionFilter(''); }}
          />
          <TableFilters
            search={search}
            onSearch={setSearch}
            placeholder="Search field ID, value, snippet, document or AI-QIF indicator…"
            shown={filteredFacts.length}
            total={facts.length}
            selects={[
              { key: 'criterion', label: 'AI-QIF criterion', value: criterionFilter, onChange: setCriterionFilter,
                options: criterionGroups.map((g) => ({
                  value: g.criterion, label: `${shortCode(g.code)} ${g.name}`, count: g.count,
                })) },
              { key: 'mapping', label: 'AI-QIF mapping', value: mappingFilter, onChange: setMappingFilter,
                options: optionsFrom(facts, (f) => f.aiqif_mapping_status, (v: string) => MAPPING_STATUS_LABELS[v] || v) },
              { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                options: optionsFrom(facts, (f) => f.status, (v: string) => v.replace(/_/g, ' ')) },
              { key: 'pillar', label: 'CRI pillar', value: pillarFilter, onChange: setPillarFilter,
                options: optionsFrom(facts, (f) => f.pillar_label || f.pillar) },
              { key: 'confidence', label: 'Confidence', value: confidenceFilter, onChange: setConfidenceFilter,
                options: optionsFrom(facts, (f) => confidenceBand(f.confidence)) },
              { key: 'owner', label: 'Owner', value: ownerFilter, onChange: setOwnerFilter,
                options: optionsFrom(facts, (f) => f.owner_role) },
              { key: 'source', label: 'Source document', value: sourceFilter, onChange: setSourceFilter,
                options: optionsFrom(facts, (f) => f.source_document_filename) },
            ]}
          />
          {filteredFacts.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No facts match these filters.</p>
            </div>
          ) : (
          <ScrollableTable>
            <table className="table-base min-w-[1640px]">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>Audit Field ID</th>
                  <th>Extracted Value</th>
                  <th title="The AI-QIF criteria and key indicators this fact is evidence for. A category only: it does not change any score.">
                    AI-QIF Category
                  </th>
                  <th title="The pillar the CRI scores this fact under once it is confirmed.">CRI Pillar</th>
                  <th>Source Document</th>
                  <th>Source Snippet</th>
                  <th>Confidence</th>
                  <th>Owner</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFacts.map((fact, index) => (
                  <tr key={fact.id}>
                    <td className="text-ink-500 tabular-nums">{index + 1}</td>
                    <td className="font-mono text-xs font-bold text-brand-800">
                      {fact.audit_field_id}
                    </td>
                    <td className="font-semibold text-ink-900">
                      {editingFactId === fact.id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={correctionValue}
                            onChange={(e) => setCorrectionValue(e.target.value)}
                            className="input py-1.5 px-2 text-xs"
                          />
                          <button
                            onClick={() => handleCorrectSubmit(fact.id)}
                            disabled={actingOnId === fact.id}
                            className="btn-primary btn-sm"
                          >
                            {actingOnId === fact.id ? 'Saving...' : 'Save'}
                          </button>
                        </div>
                      ) : (
                        <span>{typeof fact.value_json === 'object' ? JSON.stringify(fact.value_json) : String(fact.value_json)}</span>
                      )}
                    </td>
                    <td><AIQIFCategoryCell fact={fact} busy={actingOnId === fact.id} onReview={canReview ? (code, d) => handleMappingReview(fact.id, code, d) : undefined} /></td>
                    <td>
                      <span className="badge-neutral">
                        {fact.pillar_label || fact.pillar || '—'}
                      </span>
                    </td>
                    <td className="text-ink-600 max-w-[10rem] truncate" title={fact.source_document_filename}>
                      {fact.source_document_filename || '—'}
                    </td>
                    <td className="text-ink-500 max-w-xs italic" title={fact.confidence_reason}>
                      <div className="truncate">&ldquo;{fact.source_snippet}&rdquo; ({fact.source_page || 'n/a'})</div>
                      {fact.confidence_reason && (
                        <div className="not-italic text-xs text-ink-400 truncate mt-0.5">
                          {fact.confidence_reason}
                        </div>
                      )}
                    </td>
                    <td className="font-mono font-semibold text-success tabular-nums">
                      {(fact.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="text-ink-700 font-medium">{fact.owner_role || 'IQAC'}</td>
                    <td>
                      <span className={statusBadgeClass(fact.status)}>{fact.status}</span>
                    </td>
                    <td className="text-right space-x-1 whitespace-nowrap">
                      {fact.status !== 'confirmed' && (
                        <button
                          onClick={() => handleConfirm(fact.id)}
                          disabled={actingOnId === fact.id}
                          className="px-2.5 py-1 bg-success-solid text-white text-xs font-semibold rounded transition-colors disabled:opacity-60 hover:brightness-95"
                        >
                          {actingOnId === fact.id ? 'Working...' : 'Confirm'}
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setEditingFactId(fact.id);
                          setCorrectionValue(String(fact.value_json));
                        }}
                        className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-ink-700 text-xs font-semibold rounded transition-colors"
                      >
                        Correct
                      </button>
                      {fact.status !== 'evidence_requested' && (
                        <button
                          onClick={() => handleRequestEvidence(fact.id)}
                          disabled={actingOnId === fact.id}
                          className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-accent text-xs font-semibold rounded transition-colors disabled:opacity-60"
                        >
                          Request Evidence
                        </button>
                      )}
                      {fact.status !== 'rejected' && (
                        <button
                          onClick={() => handleReject(fact.id)}
                          disabled={actingOnId === fact.id}
                          className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-danger text-xs font-semibold rounded transition-colors disabled:opacity-60"
                        >
                          Reject
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollableTable>
          )}
          </>
        )}
      </div>
    </div>
  );
};

/** Same bands a reviewer reads off the Confidence column. */
function confidenceBand(confidence: number): string {
  if (confidence >= 0.8) return 'High (80%+)';
  if (confidence >= 0.5) return 'Medium (50-79%)';
  return 'Low (<50%)';
}

const MAPPING_STATUS_LABELS: Record<string, string> = {
  mapped: 'Mapped',
  needs_review: 'Needs review',
  unmapped: 'Unmapped',
  pending: 'Not yet mapped',
};

/** 'AIQIF-C4.1' -> 'C4.1' for compact display. */
const shortCode = (code: string) => code.replace(/^AIQIF-/, '');

interface CriterionGroup { criterion: string; code: string; name: string; count: number }

/** Each AI-QIF criterion the facts are tagged with, and how many facts it
 * has (a fact tagged under two criteria counts in both), in framework order. */
function aiqifCriterionGroups(facts: Fact[]): CriterionGroup[] {
  const groups = new Map<string, CriterionGroup>();
  for (const fact of facts) {
    for (const criterion of new Set(fact.aiqif_mappings.map((m) => m.criterion))) {
      const m = fact.aiqif_mappings.find((x) => x.criterion === criterion)!;
      const group = groups.get(criterion) || { criterion, code: m.criterion_code, name: m.criterion_name, count: 0 };
      group.count += 1;
      groups.set(criterion, group);
    }
  }
  return [...groups.values()].sort((a, b) => a.code.localeCompare(b.code, undefined, { numeric: true }));
}

/** Facts grouped by AI-QIF criterion, as one-click filters, plus the facts
 * that still need a person to look at their category. */
const AIQIFCriterionStrip: React.FC<{
  groups: CriterionGroup[];
  facts: Fact[];
  criterion: string;
  mapping: string;
  onCriterion: (value: string) => void;
  onMapping: (value: string) => void;
}> = ({ groups, facts, criterion, mapping, onCriterion, onMapping }) => {
  const countOf = (status: Fact['aiqif_mapping_status']) => facts.filter((f) => f.aiqif_mapping_status === status).length;
  const unclear = (['needs_review', 'unmapped', 'pending'] as const).filter((s) => countOf(s) > 0);
  if (groups.length === 0 && unclear.length === 0) return null;
  const chip = (active: boolean) =>
    `px-2.5 py-1 rounded-full border text-xs font-semibold transition-colors ${
      active ? 'bg-brand-50 border-brand-500 text-brand-800' : 'bg-surface border-line-200 text-ink-600 hover:border-line-300'
    }`;

  return (
    <div className="mb-4 space-y-2">
      <p className="text-xs text-ink-500">
        Facts by AI-QIF criterion. The tags never change the Raw CRI. A tag counts toward AI-QIF evidence coverage
        only after a reviewer confirms it (✓ on the tag) and the fact itself is confirmed or corrected.
      </p>
      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => { onCriterion(''); onMapping(''); }} className={chip(!criterion && !mapping)}>
          All ({facts.length})
        </button>
        {groups.map((g) => (
          <button
            key={g.criterion}
            onClick={() => onCriterion(criterion === g.criterion ? '' : g.criterion)}
            className={chip(criterion === g.criterion)}
            title={g.name}
          >
            {shortCode(g.code)} {g.name} ({g.count})
          </button>
        ))}
        {unclear.map((status) => (
          <button
            key={status}
            onClick={() => onMapping(mapping === status ? '' : status)}
            className={`${chip(mapping === status)} ${status === 'needs_review' && mapping !== status ? 'text-warning' : ''}`}
          >
            {MAPPING_STATUS_LABELS[status]} ({countOf(status)})
          </button>
        ))}
      </div>
    </div>
  );
};

/** The fact's AI-QIF criterion and indicator(s), each with its confidence;
 * the AI's reason on hover. Unclear tags say so instead of guessing. */
const AIQIFCategoryCell: React.FC<{
  fact: Fact;
  busy?: boolean;
  /** Reviewers only: confirm or reject one tag. */
  onReview?: (indicatorCode: string, decision: 'confirm' | 'reject') => void;
}> = ({ fact, busy, onReview }) => {
  if (fact.aiqif_mapping_status === 'pending') {
    return <span className="text-xs text-ink-400" title="Extracted before AI-QIF tagging; re-run extraction to tag it.">Not yet mapped</span>;
  }
  if (fact.aiqif_mappings.length === 0) {
    return (
      <span className="badge-neutral" title="The AI found no AI-QIF indicator this fact clearly supports.">
        Unmapped
      </span>
    );
  }
  return (
    <div className="min-w-[230px] max-w-[300px] space-y-1.5">
      {fact.aiqif_mapping_status === 'needs_review' && <span className="badge-warning">Needs review</span>}
      {fact.aiqif_mappings.map((m) => (
        <div key={m.indicator_code} title={`${m.criterion_code} ${m.criterion_name}\n${m.indicator_code} ${m.indicator_name}\n\nWhy: ${m.reason}`}>
          <div className="flex items-start gap-1.5">
            <span className="font-mono text-[11px] font-bold text-brand-800 shrink-0 mt-px">{shortCode(m.indicator_code)}</span>
            <span className="text-xs font-semibold text-ink-800 leading-snug">{m.indicator_name}</span>
            <span className={`ml-auto shrink-0 ${m.status === 'mapped' ? 'badge-success' : 'badge-warning'}`}>
              {Math.round(m.confidence * 100)}%
            </span>
          </div>
          <p className="text-[11px] text-ink-500 truncate">
            {shortCode(m.criterion_code)} · {m.criterion_name}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {m.review_status === 'confirmed' && (
              <span className="text-[11px] font-semibold text-success" title={m.review_note || undefined}>
                ✓ Confirmed{m.reviewed_by_name ? ` by ${m.reviewed_by_name}` : ''}
              </span>
            )}
            {m.review_status === 'rejected' && (
              <span className="text-[11px] font-semibold text-danger" title={m.review_note || undefined}>
                ✕ Rejected{m.reviewed_by_name ? ` by ${m.reviewed_by_name}` : ''}
              </span>
            )}
            {m.review_status === 'unreviewed' && <span className="text-[11px] text-ink-400">Not reviewed</span>}
            {onReview && m.review_status !== 'confirmed' && (
              <button disabled={busy} onClick={() => onReview(m.indicator_code, 'confirm')}
                className="ml-auto text-[11px] font-semibold text-success hover:underline disabled:opacity-50"
                title="This fact is evidence for this indicator">✓ Confirm tag</button>
            )}
            {onReview && m.review_status !== 'rejected' && (
              <button disabled={busy} onClick={() => onReview(m.indicator_code, 'reject')}
                className={`${m.review_status === 'confirmed' ? 'ml-auto ' : ''}text-[11px] font-semibold text-danger hover:underline disabled:opacity-50`}
                title="This fact is not evidence for this indicator">✕ Reject</button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
