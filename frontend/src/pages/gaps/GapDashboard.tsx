import React, { useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  getSprintGapFacets, listSprintGapsPage, resolveGap, markGapUnavailable, skipGap, type GapFacets,
} from '../../api/gaps';
import { DEFAULT_PAGE_SIZE, type Page } from '../../api/pagination';
import { Pagination, optionsFromCounts, pillarOptions, useDebounced } from '../../components/Pagination';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Gap } from '../../types';
import { ACTIVE_GAP_STATUSES } from '../../types/gaps';
import { AlertCircle, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { UploadEvidenceModal } from './UploadEvidenceModal';
import { LowConfidenceGapPanel } from './LowConfidenceGapPanel';
import { ConflictComparisonDialog } from './ConflictComparison';
import { GapSnippetCell } from './GapSnippetCell';
import { promptDialog } from '../../components/Dialog';
import { isRealSprintId } from '../../utils/selectedSprint';

export const GapDashboard: React.FC = () => {
  const { canSee, step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = isRealSprintId(sprintId);

  // Filters and paging run on the server (apps/gaps/filters.py): one page of gaps is loaded, never the whole
  // sprint; the filter options and totals come from aggregate counts (facets).
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [pillarFilter, setPillarFilter] = useState('');
  const q = useDebounced(search.trim());
  const query = { q, gap_type: typeFilter, priority: priorityFilter, status: statusFilter,
    source_document: sourceFilter, pillar: pillarFilter };
  const queryKey = JSON.stringify(query);
  // The page belongs to its filters: a new filter starts at page 1 in the same render (never a request for
  // page 2 of a filter that may have only one page).
  const [pageState, setPageState] = useState({ key: queryKey, page: 1 });
  const page = pageState.key === queryKey ? pageState.page : 1;
  const setPage = (next: number) => setPageState({ key: queryKey, page: next });
  const {
    data: pageData,
    loading,
    error,
    refetch: refetchPage,
  } = useApiResource<Page<Gap>>(() => listSprintGapsPage(sprintId!, { ...query, page, page_size: DEFAULT_PAGE_SIZE }),
    [sprintId, queryKey, page], isRealSprint);
  const { data: facets, refetch: refetchFacets } = useApiResource<GapFacets>(
    () => getSprintGapFacets(sprintId!), [sprintId], isRealSprint);
  const refetch = () => { refetchPage(); refetchFacets(); };
  const gaps = pageData?.results || [];
  const filteredGaps = gaps;
  const totalGaps = facets?.total ?? 0;
  // `open` and `in_progress` are both live work; resolved, unavailable and
  // skipped are closed out.
  const openGapCount = facets?.open ?? 0;

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
  const askReason = async (what: string) => (await promptDialog(
    `Why is this gap being ${what}? (kept in its history)`, { title: 'Reason required', required: true },
  )) || null;

  const handleMarkUnavailable = async (gapId: string) => {
    const reason = await askReason('marked unavailable');
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
    const reason = await askReason('skipped');
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
      {comparingGap && <ConflictComparisonDialog gap={comparingGap} onClose={() => setComparingId(null)} onResolved={refetch} />}
      {uploadingGap && (
        <UploadEvidenceModal gap={uploadingGap} sprintLabel={sprintLabel} onClose={() => setUploadingGap(null)}
          onUploaded={(message) => { setUploadingGap(null); setUploadMessage(message); refetch(); }} />
      )}
      {/* Action Bar */}
      <div className="flex justify-end">
        <button
          data-tour="gaps-proceed-btn"
          onClick={() => navigate(`/sprint/${sprintId}/score`)}
          className="btn-primary shrink-0"
        >
          <span>Open assessment</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {uploadMessage && (
        <div className="rounded-lg border border-line-200 bg-surface-50 px-4 py-2 text-sm text-ink-700 flex justify-between gap-3" role="status">
          <span>{uploadMessage}</span>
          <button className="text-xs text-ink-500 hover:underline" onClick={() => setUploadMessage('')}>Dismiss</button>
        </div>
      )}

      {/* Gaps List Table */}
      <div className="glass-card p-5 sm:p-6" data-tour="gaps-summary-bar">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Identified Data Gaps &amp; Score Penalties</h2>
          {/* The table below lists every gap, resolved ones included, so this
              label must not call the whole list "open" -- it read "318 gaps
              open" on a sprint with 306 open and 12 already resolved. */}
          <span className="text-xs text-ink-500">
            {openGapCount} open
            {totalGaps > openGapCount && ` · ${totalGaps - openGapCount} closed`}
          </span>
        </div>

        {loading && !pageData ? (
          <LoadingState message="Loading gaps..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : totalGaps === 0 && gaps.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No gaps detected yet. Gaps are raised automatically when AI extraction finds missing, conflicting or unconfirmed data.</p>
            <Link to={`/sprint/${sprintId}/facts`} className="btn-secondary btn-sm mt-3 inline-flex">Review extracted facts</Link>
          </div>
        ) : (
          <>
          <div data-tour="gaps-filters">
            <TableFilters
              search={search}
              onSearch={setSearch}
              placeholder="Search title, field ID, source or snippet…"
              shown={pageData?.count ?? 0}
              total={totalGaps}
              selects={[
                { key: 'type', label: 'Gap type', value: typeFilter, onChange: setTypeFilter,
                  options: optionsFromCounts(facets?.gap_type, (v: string) => v.replace(/_/g, ' ')) },
                { key: 'priority', label: 'Priority', value: priorityFilter, onChange: setPriorityFilter,
                  options: optionsFromCounts(facets?.priority) },
                // The CRI pillars are the 9 AI-QIF criteria in framework order; one with no gaps still shows, as (0).
                { key: 'pillar', label: 'CRI Pillar', value: pillarFilter, onChange: setPillarFilter,
                  options: pillarOptions(facets?.pillars) },
                { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                  options: optionsFromCounts(facets?.status, (v: string) => v.replace(/_/g, ' ')) },
                { key: 'source', label: 'Source', value: sourceFilter, onChange: setSourceFilter,
                  options: optionsFromCounts(facets?.source_document) },
              ]}
            />
          </div>
          {filteredGaps.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No gaps match these filters.</p>
            </div>
          ) : (
          <div data-tour="gaps-table">
            <ScrollableTable>
              <table className="table-base min-w-[1750px]">
                <thead>
                  <tr>
                    <th>S.No</th>
                    <th>Audit Field ID</th>
                    <th>Gap Type</th>
                    <th>Priority</th>
                    <th title="The CRI pillar whose score this gap's penalty is taken from while it is open.">CRI Pillar</th>
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
                      <td className="text-ink-500 tabular-nums">{(page - 1) * DEFAULT_PAGE_SIZE + index + 1}</td>
                      <td className="font-mono text-xs font-bold text-brand-800">
                        {gap.audit_field_id || '—'}
                      </td>
                      <td className="text-ink-700 font-medium capitalize">
                        {gap.gap_type.replace('_', ' ')}
                      </td>
                      <td>
                        <span className={priorityBadgeClass(gap.priority)}>{gap.priority}</span>
                      </td>
                      <td>
                        <span className="badge-neutral">{gap.pillar_label || gap.pillar || '—'}</span>
                      </td>
                      <td className="text-ink-600">
                        {gap.title}
                        {/* Who it is assigned to (every owner is the college's IQAC Coordinator, so no Owner column). */}
                        {(gap.assigned_to_name || gap.due_date) && (
                          <span className="block text-[11px] text-ink-500">
                            {gap.assigned_to_name ? `→ ${gap.assigned_to_name}` : ''}
                            {gap.due_date ? `${gap.assigned_to_name ? ' · ' : ''}due ${gap.due_date}` : ''}
                          </span>
                        )}
                      </td>
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
                          <Link to={`/sprint/${sprintId}/evidence?tab=review`}
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
                          <button
                            data-tour={index === 0 ? "gaps-evidence-btn" : undefined}
                            onClick={() => { setUploadMessage(''); setUploadingGap(gap); }}
                            aria-haspopup="dialog"
                            className="px-3 py-1 bg-line-200 hover:bg-line-300 text-accent font-semibold text-xs rounded transition-colors"
                          >
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
          </div>
          )}
          {pageData && (
            <Pagination page={page} pageSize={DEFAULT_PAGE_SIZE} count={pageData.count} onPage={setPage} />
          )}
          </>
        )}
      </div>
    </div>
  );
};
