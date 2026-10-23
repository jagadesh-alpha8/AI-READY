import React, { useMemo, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { listSprintGaps, resolveGap, markGapUnavailable, skipGap } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Gap } from '../../types';
import { ACTIVE_GAP_STATUSES } from '../../types/gaps';
import { AlertCircle, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters, matchesSearch, optionsFrom } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { UploadEvidenceModal } from './UploadEvidenceModal';
import { LowConfidenceGapPanel } from './LowConfidenceGapPanel';
import { ConflictComparisonDialog } from './ConflictComparison';
import { GapSnippetCell } from './GapSnippetCell';
import { snippetSearchText } from './gapSnippets.ts';

export const GapDashboard: React.FC = () => {
  const { canSee, step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: gapsData,
    loading,
    error,
    refetch,
  } = useApiResource<Gap[]>(() => listSprintGaps(sprintId!), [sprintId], isRealSprint);
  const gaps = gapsData || [];
  // `open` and `in_progress` are both live work; resolved, unavailable and
  // skipped are closed out.
  const openGapCount = gaps.filter(
    (gap) => ACTIVE_GAP_STATUSES.includes(gap.status),
  ).length;

  const [actionError, setActionError] = useState('');
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  // The low-confidence gap whose fact panel is open (looked up in the fresh list after every refetch).
  const [reviewingGapId, setReviewingGapId] = useState<string | null>(null);
  // The gap whose "Upload Evidence" dialog is open, and the last upload's message.
  const [uploadingGap, setUploadingGap] = useState<Gap | null>(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const { sprint } = useSelectedSprint();
  const sprintLabel = sprint && sprint.id === sprintId
    ? (sprint.academic_year && !sprint.name.includes(sprint.academic_year)
      ? `${sprint.name} · ${sprint.academic_year}` : sprint.name)
    : (sprintId || '');
  const reviewingGap = gaps.find((g) => g.id === reviewingGapId) || null;
  // Low-confidence gaps on a fact are settled by evidence (LowConfidenceGapPanel), not the row buttons.
  const settledByEvidence = (gap: Gap) => gap.gap_type === 'low_confidence' && !!gap.source_fact_id;
  // The conflict gap whose two sources are being compared (in a dialog, so the table stays compact).
  const [comparingId, setComparingId] = useState<string | null>(null);
  const comparingGap = gaps.find((g) => g.id === comparingId) || null;

  // Filters (client-side: the full gap list is already loaded).
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const filteredGaps = useMemo(
    () => gaps.filter((gap) =>
      (!typeFilter || gap.gap_type === typeFilter)
      && (!priorityFilter || gap.priority === priorityFilter)
      && (!statusFilter || gap.status === statusFilter)
      && (!ownerFilter || (gap.owner_role || '') === ownerFilter)
      && (!sourceFilter || (gap.source_document_filename || '') === sourceFilter)
      && matchesSearch(search, gap.title, gap.description, gap.audit_field_id, gap.source_document_filename,
        ...snippetSearchText(gap))),
    [gaps, search, typeFilter, priorityFilter, statusFilter, ownerFilter, sourceFilter],
  );

  const handleResolveGap = async (gapId: string) => {
    setResolvingId(gapId);
    setActionError('');
    try {
      await resolveGap(gapId, 'Resolved on the Gap Dashboard');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to resolve gap.'));
    } finally {
      setResolvingId(null);
    }
  };

  // Closing a gap without fixing it always needs a reason (the server refuses a blank one).
  const askReason = (what: string) => {
    const reason = window.prompt(`Why is this gap being ${what}? (required, kept in its history)`, '');
    return reason && reason.trim() ? reason.trim() : null;
  };

  const handleMarkUnavailable = async (gapId: string) => {
    const reason = askReason('marked unavailable');
    if (!reason) return;
    setResolvingId(gapId);
    setActionError('');
    try {
      await markGapUnavailable(gapId, reason);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to mark gap unavailable.'));
    } finally {
      setResolvingId(null);
    }
  };

  const handleSkipGap = async (gapId: string) => {
    const reason = askReason('skipped');
    if (!reason) return;
    setResolvingId(gapId);
    setActionError('');
    try {
      await skipGap(gapId, reason);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to skip gap.'));
    } finally {
      setResolvingId(null);
    }
  };

  const priorityBadgeClass = (priority: Gap['priority']) => (priority === 'blocking' ? 'badge-danger' : 'badge-warning');
  const statusBadgeClass = (status: Gap['status']) => {
    switch (status) {
      case 'resolved': return 'badge-success';
      case 'unavailable': return 'badge-warning';
      case 'skipped': return 'badge-neutral';
      case 'needs_replacement': return 'badge-danger';
      default: return 'badge-neutral';
    }
  };

  return (
    <div className="space-y-6">
      {reviewingGap && (
        <LowConfidenceGapPanel gap={reviewingGap} onClose={() => setReviewingGapId(null)} onChanged={refetch} />
      )}
      {comparingGap && <ConflictComparisonDialog gap={comparingGap} onClose={() => setComparingId(null)} />}
      {uploadingGap && (
        <UploadEvidenceModal gap={uploadingGap} sprintLabel={sprintLabel} onClose={() => setUploadingGap(null)}
          onUploaded={(message) => { setUploadingGap(null); setUploadMessage(message); refetch(); }} />
      )}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-warning" /> Step {step('sprint-gaps')}: Gap Dashboard
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Identify missing required fields, weak evidence, stale documents, and conflicts affecting score and confidence.
            </p>
          </div>
          <button
            onClick={() => navigate(`/sprint/${sprintId}/${canSee('sprint-confirmation') ? 'confirmation' : 'score'}`)}
            className="btn-primary shrink-0"
          >
            <span>{canSee('sprint-confirmation') ? 'Proceed to Owner Workspace' : 'Proceed to Live CRI Preview'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {uploadMessage && (
        <div className="rounded-lg border border-line-200 bg-surface-50 px-4 py-2 text-sm text-ink-700 flex justify-between gap-3" role="status">
          <span>{uploadMessage}</span>
          <button className="text-xs text-ink-500 hover:underline" onClick={() => setUploadMessage('')}>Dismiss</button>
        </div>
      )}

      {/* Gaps List Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Identified Data Gaps &amp; Score Penalties</h2>
          {/* The table below lists every gap, resolved ones included, so this
              label must not call the whole list "open" -- it read "318 gaps
              open" on a sprint with 306 open and 12 already resolved. */}
          <span className="text-xs text-ink-500">
            {openGapCount} open
            {gaps.length > openGapCount && ` · ${gaps.length - openGapCount} closed`}
          </span>
        </div>

        {loading ? (
          <LoadingState message="Loading gaps..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : gaps.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No gaps detected yet.</p>
            <button
              onClick={() => setActionError(
                'Demo gap seeding is disabled: gaps are only ever raised by automatic detection during extraction, never fabricated.',
              )}
              className="mt-3 px-3 py-1.5 bg-warning-solid text-white text-xs rounded-lg font-medium hover:brightness-95"
            >
              Seed Sample Gaps
            </button>
          </div>
        ) : (
          <>
          <TableFilters
            search={search}
            onSearch={setSearch}
            placeholder="Search title, field ID, source or snippet…"
            shown={filteredGaps.length}
            total={gaps.length}
            selects={[
              { key: 'type', label: 'Gap type', value: typeFilter, onChange: setTypeFilter,
                options: optionsFrom(gaps, (g) => g.gap_type, (v: string) => v.replace(/_/g, ' ')) },
              { key: 'priority', label: 'Priority', value: priorityFilter, onChange: setPriorityFilter,
                options: optionsFrom(gaps, (g) => g.priority) },
              { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                options: optionsFrom(gaps, (g) => g.status, (v: string) => v.replace(/_/g, ' ')) },
              { key: 'owner', label: 'Owner', value: ownerFilter, onChange: setOwnerFilter,
                options: optionsFrom(gaps, (g) => g.owner_role) },
              { key: 'source', label: 'Source', value: sourceFilter, onChange: setSourceFilter,
                options: optionsFrom(gaps, (g) => g.source_document_filename) },
            ]}
          />
          {filteredGaps.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No gaps match these filters.</p>
            </div>
          ) : (
          <ScrollableTable>
            <table className="table-base min-w-[1600px]">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>Audit Field ID</th>
                  <th>Gap Type</th>
                  <th>Priority</th>
                  <th title="The role that owns this data -- not a named person">Owner Role</th>
                  <th>Title</th>
                  <th>Source</th>
                  <th title="The linked fact's snippet and page; both sources for a conflict">Source Snippet</th>
                  <th>Score Impact</th>
                  <th>Status</th>
                  <th title="The fact's evidence request and the person it is assigned to">Evidence Request</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredGaps.map((gap, index) => (
                  <tr key={gap.id}>
                    <td className="text-ink-500 tabular-nums">{index + 1}</td>
                    <td className="font-mono text-xs font-bold text-brand-800">
                      {gap.audit_field_id || '—'}
                    </td>
                    <td className="text-ink-700 font-medium capitalize">
                      {gap.gap_type.replace('_', ' ')}
                    </td>
                    <td>
                      <span className={priorityBadgeClass(gap.priority)}>{gap.priority}</span>
                    </td>
                    <td className="text-ink-900">
                      <span className="font-semibold">{gap.owner_role || '—'}</span>
                      <span className="block text-[11px] text-ink-500">
                        {gap.assigned_to_name ? `→ ${gap.assigned_to_name}` : 'unassigned'}
                        {gap.due_date ? ` · due ${gap.due_date}` : ''}
                      </span>
                    </td>
                    <td className="text-ink-600">{gap.title}</td>
                    <td
                      className="text-ink-600 max-w-[14rem] truncate"
                      title={gap.source_document_filename || undefined}
                    >
                      {gap.source_document_filename || '—'}
                    </td>
                    <td className="max-w-[18rem] min-w-[12rem] align-top">
                      <GapSnippetCell gap={gap} />
                    </td>
                    <td className="font-mono font-bold text-danger tabular-nums">
                      -{gap.score_impact} pts
                    </td>
                    <td>
                      <span className={statusBadgeClass(gap.status)}>{gap.status}</span>
                    </td>
                    <td className="text-xs">
                      {gap.evidence_state && gap.evidence_state.state !== 'still_open' && gap.evidence_state.state !== 'evidence_requested' && (
                        <div className="mb-1 max-w-[16rem] whitespace-normal">
                          <span className={gap.evidence_state.state === 'processing_failed' ? 'badge-danger'
                            : gap.evidence_state.state === 'resolved' ? 'badge-success'
                              : gap.evidence_state.state === 'awaiting_review' ? 'badge-warning' : 'badge-info'}>
                            {gap.evidence_state.label}
                          </span>
                          <span className="block text-ink-600 mt-0.5">{gap.evidence_state.reason}</span>
                          {gap.evidence_state.next_action && (
                            <span className="block text-ink-500">Next: {gap.evidence_state.next_action}{' '}
                              {['processing', 'uploaded', 'processing_failed'].includes(gap.evidence_state.state) && (
                                <Link to={`/sprint/${sprintId}/monitor`} className="text-brand-800 hover:underline">Monitor</Link>
                              )}
                              {gap.evidence_state.state === 'awaiting_review' && (
                                <Link to={`/sprint/${sprintId}/${gap.gap_type === 'missing_document' ? 'upload' : 'facts'}`}
                                  className="text-brand-800 hover:underline">
                                  {gap.gap_type === 'missing_document' ? 'Upload Data Pack' : 'Facts Review'}
                                </Link>
                              )}
                            </span>
                          )}
                        </div>
                      )}
                      {gap.evidence_request ? (
                        <Link to={`/evidence-requests?view=all&id=${gap.evidence_request.id}`}
                          className="font-semibold text-accent hover:underline">
                          {gap.evidence_request.overdue ? 'Overdue' : gap.evidence_request.status_label}
                          <span className="block font-normal text-ink-500">
                            {gap.evidence_request.assigned_to_name || 'not assigned yet'}
                          </span>
                        </Link>
                      ) : <span className="text-ink-500">—</span>}
                    </td>
                    <td className="text-right space-x-1 whitespace-nowrap">
                      {gap.can_upload_evidence && gap.can_act !== false && (
                        <button onClick={() => { setUploadMessage(''); setUploadingGap(gap); }} aria-haspopup="dialog"
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-accent font-semibold text-xs rounded transition-colors">
                          Upload Evidence
                        </button>
                      )}
                      {gap.gap_type === 'conflict' && (
                        <button
                          onClick={() => setComparingId(gap.id)}
                          aria-haspopup="dialog"
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-brand-800 font-semibold text-xs rounded transition-colors"
                        >
                          Compare sources
                        </button>
                      )}
                      {settledByEvidence(gap) ? (
                        <button
                          onClick={() => setReviewingGapId(gap.id)}
                          className="px-3 py-1 bg-brand-500 hover:brightness-95 text-on-brand font-semibold text-xs rounded transition-all"
                        >
                          {ACTIVE_GAP_STATUSES.includes(gap.status) ? 'Review fact' : 'View fact'}
                        </button>
                      ) : gap.can_act === false ? (
                        // The server's ownership rule (apps/facts/ownership.py): say who may act instead.
                        <span className="inline-block max-w-[16rem] whitespace-normal text-left text-xs text-ink-500">
                          {gap.act_blocked_reason}
                        </span>
                      ) : (
                      <>
                      {gap.status !== 'resolved' && (
                        <button
                          onClick={() => handleResolveGap(gap.id)}
                          disabled={resolvingId === gap.id || !!gap.resolve_blocked_reason}
                          title={gap.resolve_blocked_reason || undefined}
                          className="px-3 py-1 bg-brand-500 hover:brightness-95 text-on-brand font-semibold text-xs rounded transition-all disabled:opacity-60"
                        >
                          {resolvingId === gap.id ? 'Resolving...' : 'Resolve Gap'}
                        </button>
                      )}
                      {gap.status !== 'unavailable' && (
                        <button
                          onClick={() => handleMarkUnavailable(gap.id)}
                          disabled={resolvingId === gap.id || !!gap.close_blocked_reason}
                          title={gap.close_blocked_reason || undefined}
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-warning font-semibold text-xs rounded transition-colors disabled:opacity-60"
                        >
                          Mark Unavailable
                        </button>
                      )}
                      {gap.status !== 'skipped' && (
                        <button
                          onClick={() => handleSkipGap(gap.id)}
                          disabled={resolvingId === gap.id || !!gap.close_blocked_reason}
                          title={gap.close_blocked_reason || undefined}
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-ink-700 font-semibold text-xs rounded transition-colors disabled:opacity-60"
                        >
                          Skip
                        </button>
                      )}
                      </>
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
