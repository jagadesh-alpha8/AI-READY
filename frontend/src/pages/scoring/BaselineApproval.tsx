import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { approveBaseline, approveBaselineProvisional, getBaseline, returnBaseline } from '../../api/baseline';
import { getSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { SprintBaseline } from '../../types';
import { Lock, ArrowRight, ShieldCheck, AlertTriangle, TrendingUp, TrendingDown, Undo2 } from 'lucide-react';

const STATUS_LABEL: Record<string, string> = {
  pending: 'Provisional Baseline Active',
  approved: 'Baseline Locked & Approved',
  provisional: 'Provisionally Approved (Baseline Locked)',
  returned: 'Returned for Correction',
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  pending: 'text-warning',
  approved: 'text-success',
  provisional: 'text-brand-800',
  returned: 'text-danger',
};

export const BaselineApproval: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();

  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';
  const {
    data,
    setData,
    loading,
    error,
    refetch,
  } = useApiResource<SprintBaseline>(() => getBaseline(sprintId!), [sprintId], isRealSprint);
  const { data: sprint } = useApiResource(() => getSprint(sprintId!), [sprintId], isRealSprint);

  const [comments, setComments] = useState('');
  const [returning, setReturning] = useState(false);
  const [acting, setActing] = useState<'approve' | 'provisional' | 'return' | null>(null);
  const [actionError, setActionError] = useState('');

  const baseline = data?.baseline;
  const scorecard = data?.score;
  const isDecided = baseline ? baseline.status !== 'pending' : false;
  const canApprove = !!data?.can_approve && !isDecided;

  const handleApprove = async () => {
    if (!sprintId) return;
    setActing('approve');
    setActionError('');
    try {
      const res = await approveBaseline(sprintId, comments);
      setData((prev) => (prev ? { ...prev, baseline: res.data } : prev));
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to approve the baseline.'));
    } finally {
      setActing(null);
    }
  };

  const handleApproveProvisional = async () => {
    if (!sprintId) return;
    setActing('provisional');
    setActionError('');
    try {
      const res = await approveBaselineProvisional(sprintId, comments);
      setData((prev) => (prev ? { ...prev, baseline: res.data } : prev));
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to provisionally approve the baseline.'));
    } finally {
      setActing(null);
    }
  };

  const handleReturn = async () => {
    if (!sprintId) return;
    if (!comments.trim()) {
      setActionError('A reason is required when returning a baseline for correction.');
      return;
    }
    setActing('return');
    setActionError('');
    try {
      const res = await returnBaseline(sprintId, comments);
      setData((prev) => (prev ? { ...prev, baseline: res.data } : prev));
      setReturning(false);
      setComments('');
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to return the baseline for correction.'));
    } finally {
      setActing(null);
    }
  };

  const blockingGaps = (data?.high_priority_gaps || []).filter((g) => g.priority === 'blocking');
  const highPriorityGaps = data?.high_priority_gaps || [];

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Lock className="w-5 h-5 text-success" /> Screen 8: Baseline Approval
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Review the CRI baseline's evidence backing, then lock and sign off before improvement recommendations are drafted.
            </p>
          </div>
          <button onClick={() => navigate(`/sprint/${sprintId}/recommendations`)} className="btn-primary shrink-0">
            <span>Proceed to Recommendations</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {loading ? (
        <LoadingState message="Loading baseline for approval..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !baseline || !scorecard ? (
        <LoadingState message="No score available for this sprint yet." />
      ) : (
        <>
          {/* Approval Status + Score Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="glass-card p-6 text-center">
              <span className="text-xs font-bold text-brand-800 uppercase tracking-wide">Baseline CRI Score</span>
              <div className="text-3xl sm:text-4xl font-bold text-ink-900 my-3 tracking-tight tabular-nums">
                {baseline.overall_cri.toFixed(1)} <span className="text-base font-normal text-ink-500">/ 100</span>
              </div>
              <span className="text-xs text-ink-500">
                {(baseline.overall_confidence * 100).toFixed(0)}% evidence confidence
                {sprint ? ` · ${sprint.completion_percentage}% complete` : ''}
              </span>
            </div>

            <div className="glass-card p-6 flex flex-col justify-between md:col-span-2">
              <div>
                <span className="text-xs font-bold text-success uppercase tracking-wide flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5" /> Baseline Approval Status
                </span>
                <p className={`text-base font-bold mt-2 ${STATUS_BADGE_CLASS[baseline.status]}`}>
                  {STATUS_LABEL[baseline.status]}
                </p>
                <p className="text-xs text-ink-500 mt-1">
                  Version {baseline.calculation_version || '—'}
                  {baseline.approved_by_name ? ` · Decided by ${baseline.approved_by_name}` : ''}
                  {baseline.approved_at ? ` on ${new Date(baseline.approved_at).toLocaleString()}` : ''}
                </p>
                {baseline.comments && (
                  <p className="text-xs text-ink-700 mt-2 italic">&ldquo;{baseline.comments}&rdquo;</p>
                )}
                {!canApprove && !isDecided && (
                  <p className="text-xs text-warning mt-2 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    {blockingGaps.length} blocking gap{blockingGaps.length === 1 ? '' : 's'} unresolved -- full approval is blocked until cleared (provisional approval is still available).
                  </p>
                )}
              </div>

              {isDecided ? (
                <div className="w-full mt-4 py-2.5 px-3 text-sm font-bold rounded-lg bg-line-100 text-ink-500 text-center border border-line-200">
                  This baseline is locked -- {baseline.status === 'returned' ? 'a new scoring run is required to submit a fresh baseline.' : 'its decision cannot be changed.'}
                </div>
              ) : (
                <div className="space-y-2 mt-4">
                  {returning && (
                    <textarea
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                      placeholder="Reason for returning this baseline for correction (required)..."
                      rows={2}
                      className="input input-error"
                    />
                  )}
                  {!returning && (
                    <textarea
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                      placeholder="Optional approval comments..."
                      rows={2}
                      className="input"
                    />
                  )}
                  <div className="flex flex-col sm:flex-row items-stretch gap-2">
                    <button
                      onClick={handleApprove}
                      disabled={!canApprove || acting !== null}
                      title={!canApprove ? 'Resolve blocking gaps first, or approve provisionally.' : undefined}
                      className="flex-1 py-2.5 px-3 text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 bg-success-solid text-white shadow-card hover:brightness-95 disabled:opacity-50"
                    >
                      <Lock className="w-4 h-4" />
                      <span>{acting === 'approve' ? 'Approving...' : 'Approve Baseline'}</span>
                    </button>
                    <button
                      onClick={handleApproveProvisional}
                      disabled={acting !== null}
                      className="flex-1 py-2.5 px-3 text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 bg-brand-500 text-on-brand shadow-card hover:brightness-95 disabled:opacity-50"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>{acting === 'provisional' ? 'Approving...' : 'Approve Provisionally'}</span>
                    </button>
                    {returning ? (
                      <button
                        onClick={handleReturn}
                        disabled={acting !== null}
                        className="flex-1 py-2.5 px-3 text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 bg-danger-solid text-white shadow-card hover:brightness-95 disabled:opacity-50"
                      >
                        <Undo2 className="w-4 h-4" />
                        <span>{acting === 'return' ? 'Returning...' : 'Confirm Return'}</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => { setReturning(true); setActionError(''); }}
                        disabled={acting !== null}
                        className="flex-1 py-2.5 px-3 text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-2 bg-line-200 hover:bg-line-300 text-danger disabled:opacity-50"
                      >
                        <Undo2 className="w-4 h-4" />
                        <span>Return for Correction</span>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Strengths / Weaknesses */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="glass-card p-5 sm:p-6">
              <h2 className="eyebrow mb-4 flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-success" /> Strong Pillars
              </h2>
              {scorecard.strengths.length === 0 ? (
                <p className="text-sm text-ink-500">No pillars have reached "strong" status yet.</p>
              ) : (
                <div className="space-y-2">
                  {scorecard.strengths.map((p) => (
                    <div key={p.pillar} className="flex items-center justify-between gap-2 p-2.5 bg-success-bg border border-success-line rounded-lg">
                      <span className="text-sm font-semibold text-success">{p.label}</span>
                      <span className="text-xs font-mono text-success tabular-nums">{p.raw_score} / 100</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="glass-card p-5 sm:p-6">
              <h2 className="eyebrow mb-4 flex items-center gap-1.5">
                <TrendingDown className="w-4 h-4 text-warning" /> Pillars Needing Attention
              </h2>
              {scorecard.weaknesses.length === 0 ? (
                <p className="text-sm text-ink-500">No at-risk pillars.</p>
              ) : (
                <div className="space-y-2">
                  {scorecard.weaknesses.map((p) => (
                    <div key={p.pillar} className="flex items-center justify-between gap-2 p-2.5 bg-warning-bg border border-warning-line rounded-lg">
                      <span className="text-sm font-semibold text-warning">{p.label}</span>
                      <span className="text-xs font-mono text-warning tabular-nums">{p.raw_score} / 100</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* High-priority gaps standing in the way of full approval */}
          <div className="glass-card p-5 sm:p-6">
            <h2 className="eyebrow mb-4 flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-danger" /> Blocking &amp; High-Priority Gaps ({highPriorityGaps.length})
            </h2>
            {highPriorityGaps.length === 0 ? (
              <p className="text-sm text-success">No blocking or high-priority gaps remain -- this baseline is clear to lock.</p>
            ) : (
              <div className="space-y-2">
                {highPriorityGaps.map((g) => (
                  <div
                    key={g.id}
                    className={`flex items-center justify-between gap-3 p-3 rounded-lg border ${
                      g.priority === 'blocking' ? 'bg-danger-bg border-danger-line' : 'bg-warning-bg border-warning-line'
                    }`}
                  >
                    <div className="min-w-0">
                      <span className={`text-[11px] font-bold uppercase tracking-wide ${g.priority === 'blocking' ? 'text-danger' : 'text-warning'}`}>
                        {g.priority}
                      </span>
                      <p className={`text-sm font-semibold ${g.priority === 'blocking' ? 'text-danger' : 'text-warning'}`}>{g.title}</p>
                      <p className="text-xs text-ink-500 mt-0.5">{g.description}</p>
                    </div>
                    <span className={`text-sm font-mono font-bold shrink-0 tabular-nums ${g.priority === 'blocking' ? 'text-danger' : 'text-warning'}`}>
                      -{g.score_impact} pts
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Evidence backing */}
          <div className="glass-card p-5 sm:p-6">
            <h2 className="eyebrow mb-4">Evidence Backing This Baseline</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-surface rounded-lg border border-line-200 text-center">
                <p className="text-xl font-bold text-ink-900 tabular-nums">{scorecard.evidence_metrics.confirmed_facts}</p>
                <p className="text-xs text-ink-500 mt-1">Confirmed Facts</p>
              </div>
              <div className="p-3 bg-surface rounded-lg border border-line-200 text-center">
                <p className="text-xl font-bold text-ink-900 tabular-nums">{scorecard.evidence_metrics.corrected_facts}</p>
                <p className="text-xs text-ink-500 mt-1">Corrected Facts</p>
              </div>
              <div className="p-3 bg-surface rounded-lg border border-line-200 text-center">
                <p className="text-xl font-bold text-ink-900 tabular-nums">{scorecard.evidence_metrics.documents_processed}</p>
                <p className="text-xs text-ink-500 mt-1">Documents Processed</p>
              </div>
              <div className="p-3 bg-surface rounded-lg border border-line-200 text-center">
                <p className="text-xl font-bold text-ink-900 tabular-nums">{scorecard.evidence_metrics.unresolved_gaps}</p>
                <p className="text-xs text-ink-500 mt-1">Unresolved Gaps</p>
              </div>
            </div>
          </div>

          {/* Decision history / audit trail */}
          {baseline.history.length > 0 && (
            <div className="glass-card p-5 sm:p-6">
              <h2 className="eyebrow mb-4">Approval History</h2>
              <div className="space-y-2">
                {baseline.history.map((h) => (
                  <div key={h.id} className="flex items-center justify-between gap-3 p-2.5 bg-surface rounded-lg border border-line-200 text-sm">
                    <div className="min-w-0">
                      <span className="font-semibold text-ink-900 capitalize">{h.action.replace('_', ' ')}</span>
                      <span className="text-ink-500"> by {h.user_name || 'system'}</span>
                      {h.comments && <span className="text-ink-400 italic"> — "{h.comments}"</span>}
                    </div>
                    <span className="text-ink-400 text-xs shrink-0">{new Date(h.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
