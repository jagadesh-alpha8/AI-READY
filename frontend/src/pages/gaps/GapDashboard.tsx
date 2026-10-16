import React, { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listSprintGaps, resolveGap, markGapUnavailable, skipGap } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Gap } from '../../types';
import { AlertCircle, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters, matchesSearch, optionsFrom } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';

export const GapDashboard: React.FC = () => {
  const { canSee } = useAccess();
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
    (gap) => gap.status === 'open' || gap.status === 'in_progress',
  ).length;

  const [actionError, setActionError] = useState('');
  const [resolvingId, setResolvingId] = useState<string | null>(null);

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
      && matchesSearch(search, gap.title, gap.description, gap.audit_field_id, gap.source_document_filename)),
    [gaps, search, typeFilter, priorityFilter, statusFilter, ownerFilter, sourceFilter],
  );

  const handleResolveGap = async (gapId: string) => {
    setResolvingId(gapId);
    setActionError('');
    try {
      await resolveGap(gapId, 'Resolved by user input');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to resolve gap.'));
    } finally {
      setResolvingId(null);
    }
  };

  const handleMarkUnavailable = async (gapId: string) => {
    setResolvingId(gapId);
    setActionError('');
    try {
      await markGapUnavailable(gapId, 'Marked unavailable by user');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to mark gap unavailable.'));
    } finally {
      setResolvingId(null);
    }
  };

  const handleSkipGap = async (gapId: string) => {
    setResolvingId(gapId);
    setActionError('');
    try {
      await skipGap(gapId, 'Skipped by user');
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
      default: return 'badge-neutral';
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-warning" /> Screen 5: Gap Dashboard
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
            placeholder="Search title, field ID or source…"
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
            <table className="table-base min-w-[1280px]">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>Audit Field ID</th>
                  <th>Gap Type</th>
                  <th>Priority</th>
                  <th>Assigned Owner</th>
                  <th>Title</th>
                  <th>Source</th>
                  <th>Score Impact</th>
                  <th>Status</th>
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
                    <td className="font-semibold text-ink-900">{gap.owner_role || '—'}</td>
                    <td className="text-ink-600">{gap.title}</td>
                    <td
                      className="text-ink-600 max-w-[14rem] truncate"
                      title={gap.source_document_filename || undefined}
                    >
                      {gap.source_document_filename || '—'}
                    </td>
                    <td className="font-mono font-bold text-danger tabular-nums">
                      -{gap.score_impact} pts
                    </td>
                    <td>
                      <span className={statusBadgeClass(gap.status)}>{gap.status}</span>
                    </td>
                    <td className="text-right space-x-1 whitespace-nowrap">
                      {gap.status !== 'resolved' && (
                        <button
                          onClick={() => handleResolveGap(gap.id)}
                          disabled={resolvingId === gap.id}
                          className="px-3 py-1 bg-brand-500 hover:brightness-95 text-on-brand font-semibold text-xs rounded transition-all disabled:opacity-60"
                        >
                          {resolvingId === gap.id ? 'Resolving...' : 'Resolve Gap'}
                        </button>
                      )}
                      {gap.status !== 'unavailable' && (
                        <button
                          onClick={() => handleMarkUnavailable(gap.id)}
                          disabled={resolvingId === gap.id}
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-warning font-semibold text-xs rounded transition-colors disabled:opacity-60"
                        >
                          Mark Unavailable
                        </button>
                      )}
                      {gap.status !== 'skipped' && (
                        <button
                          onClick={() => handleSkipGap(gap.id)}
                          disabled={resolvingId === gap.id}
                          className="px-3 py-1 bg-line-200 hover:bg-line-300 text-ink-700 font-semibold text-xs rounded transition-colors disabled:opacity-60"
                        >
                          Skip
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
