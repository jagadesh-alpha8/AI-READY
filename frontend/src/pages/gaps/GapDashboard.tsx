import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listSprintGaps, resolveGap, markGapUnavailable, skipGap } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Gap } from '../../types';
import { AlertCircle, ArrowRight } from 'lucide-react';

export const GapDashboard: React.FC = () => {
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

  const [actionError, setActionError] = useState('');
  const [resolvingId, setResolvingId] = useState<string | null>(null);

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
          <button onClick={() => navigate(`/sprint/${sprintId}/confirmation`)} className="btn-primary shrink-0">
            <span>Proceed to Owner Workspace</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {/* Gaps List Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Identified Data Gaps &amp; Score Penalties</h2>
          <span className="text-xs text-ink-500">{gaps.length} gaps open</span>
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
          <div className="table-shell">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Audit Field ID</th>
                  <th>Gap Type</th>
                  <th>Priority</th>
                  <th>Assigned Owner</th>
                  <th>Title</th>
                  <th>Score Impact</th>
                  <th>Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((gap) => (
                  <tr key={gap.id}>
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
          </div>
        )}
      </div>
    </div>
  );
};
