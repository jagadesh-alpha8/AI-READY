import React, { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listSprintFacts, confirmFact, correctFact, rejectFact, requestFactEvidence } from '../../api/facts';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Fact } from '../../types';
import { FileSearch, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters, matchesSearch, optionsFrom } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';

export const FactsReview: React.FC = () => {
  const { step } = useAccess();
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
  const [ownerFilter, setOwnerFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [confidenceFilter, setConfidenceFilter] = useState('');
  const filteredFacts = useMemo(
    () => facts.filter((fact) =>
      (!statusFilter || fact.status === statusFilter)
      && (!pillarFilter || (fact.pillar_label || fact.pillar || '') === pillarFilter)
      && (!ownerFilter || (fact.owner_role || '') === ownerFilter)
      && (!sourceFilter || (fact.source_document_filename || '') === sourceFilter)
      && (!confidenceFilter || confidenceBand(fact.confidence) === confidenceFilter)
      && matchesSearch(
        search, fact.audit_field_id, fact.field_name, fact.value, fact.source_snippet, fact.source_document_filename,
      )),
    [facts, search, statusFilter, pillarFilter, ownerFilter, sourceFilter, confidenceFilter],
  );

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
          <TableFilters
            search={search}
            onSearch={setSearch}
            placeholder="Search field ID, value, snippet or document…"
            shown={filteredFacts.length}
            total={facts.length}
            selects={[
              { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                options: optionsFrom(facts, (f) => f.status, (v: string) => v.replace(/_/g, ' ')) },
              { key: 'pillar', label: 'Pillar', value: pillarFilter, onChange: setPillarFilter,
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
            <table className="table-base min-w-[1400px]">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>Audit Field ID</th>
                  <th>Extracted Value</th>
                  <th>Pillar</th>
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
