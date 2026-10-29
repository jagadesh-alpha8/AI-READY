import React, { useState } from 'react';
import { EvidenceCoverageCard } from './EvidenceCoverageCard';
import { useParams, useNavigate } from 'react-router-dom';
import { approveBaseline, approveBaselineProvisional, getBaseline, returnBaseline, reviseBaseline } from '../../api/baseline';
import { getSprint } from '../../api/sprints';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Baseline, BaselineChangedResponse, SprintBaseline } from '../../types';
import { Lock, ArrowRight, ShieldCheck, AlertTriangle, TrendingUp, TrendingDown, Undo2, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useAccess } from '../../utils/access';
import { isLocalDev } from '../../utils/devMode';
import { isRealSprintId } from '../../utils/selectedSprint';

const STATUS_LABEL: Record<string, string> = {
  pending: 'Provisional Baseline Active',
  approved: 'Baseline Locked & Approved',
  provisional: 'Provisionally Approved (Baseline Locked)',
  returned: 'Returned for Correction',
};

const HISTORY_LABEL: Record<string, string> = {
  submitted: 'Submitted', approved: 'Approved', approved_provisional: 'Approved provisionally',
  returned: 'Returned for correction', refreshed: 'Preview recalculated',
};

/** Which calculation this is: short run id and when it was calculated. */
const runLabel = (b: Baseline) =>
  `Calculation ${b.scoring_run_id.slice(0, 8)} · ${new Date(b.scoring_run_calculated_at).toLocaleString()}`;

const STATUS_BADGE_CLASS: Record<string, string> = {
  pending: 'text-warning',
  approved: 'text-success',
  provisional: 'text-brand-800',
  returned: 'text-danger',
};

/** Every baseline decision-cycle with its own audit trail. Cycles are numbered oldest = 1. */
const ApprovalHistory: React.FC<{ cycles: Baseline[]; currentId: string }> = ({ cycles, currentId }) => {
  if (!cycles.some((c) => c.history.length)) return null;
  const number = (id: string | null) => (id ? cycles.length - cycles.findIndex((c) => c.id === id) : 0);
  return (
    <div className="glass-card p-5 sm:p-6" data-tour="approval-history">
      <h2 className="eyebrow mb-4">Approval History ({cycles.length} cycle{cycles.length === 1 ? '' : 's'})</h2>
      <div className="space-y-4">
        {cycles.map((c) => (
          <div key={c.id} className="space-y-2">
            <p className="text-sm text-ink-900 flex flex-wrap items-center gap-2">
              <strong>Cycle {number(c.id)}</strong>
              {c.id === currentId && <span className="badge badge-brand">current</span>}
              <span className={`font-semibold ${STATUS_BADGE_CLASS[c.status]}`}>{STATUS_LABEL[c.status]}</span>
              <span className="text-ink-500">
                · Raw CRI {c.overall_cri.toFixed(1)} · {runLabel(c)}
                {c.revises ? ` · revises cycle ${number(c.revises)}` : ''}
              </span>
            </p>
            {c.history.map((h) => (
              <div key={h.id} className="flex items-center justify-between gap-3 p-2.5 bg-surface rounded-lg border border-line-200 text-sm">
                <div className="min-w-0">
                  <span className="font-semibold text-ink-900">{HISTORY_LABEL[h.action] || h.action}</span>
                  <span className="text-ink-500"> by {h.user_name || 'system'}</span>
                  {h.comments && <span className="text-ink-400 italic"> — "{h.comments}"</span>}
                </div>
                <span className="text-ink-400 text-xs shrink-0">{new Date(h.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

export const BaselineApproval: React.FC = () => {
  const { can, step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();

  const isRealSprint = isRealSprintId(sprintId);
  const {
    data,
    setData,
    loading,
    error,
    refetch,
  } = useApiResource<SprintBaseline>(() => getBaseline(sprintId!), [sprintId], isRealSprint);
  const { data: sprint } = useApiResource(() => getSprint(sprintId!), [sprintId], isRealSprint);

  const [comments, setComments] = useState('');
  // Required by the server to decide while included documents are not fully processed.
  const [overrideReason, setOverrideReason] = useState('');
  const [returning, setReturning] = useState(false);
  const [acting, setActing] = useState<'approve' | 'provisional' | 'return' | 'revise' | null>(null);
  const [revising, setRevising] = useState(false);
  const [reviseReason, setReviseReason] = useState('');
  const [actionError, setActionError] = useState('');
  // The score changed between loading and approving: what it was, so the reviewer sees the difference.
  const [changedFrom, setChangedFrom] = useState<{ cri: number; run: string } | null>(null);
  // Shown only after the server confirms the decision is pinned to the calculation on screen.
  const [decided, setDecided] = useState('');

  const baseline = data?.baseline;
  const scorecard = data?.score;
  const isDecided = baseline ? baseline.status !== 'pending' : false;
  const canApprove = !!data?.can_approve && !isDecided;

  /** Approve exactly the calculation on screen; a 409 means it changed -- show the new one for review. */
  const decide = async (kind: 'approve' | 'provisional') => {
    if (!sprintId || !baseline) return;
    const shown = baseline;
    setActing(kind);
    setActionError('');
    setDecided('');
    try {
      const call = kind === 'approve' ? approveBaseline : approveBaselineProvisional;
      const res = await call(sprintId, shown.scoring_run_id, comments, overrideReason);
      if (res.data.scoring_run_id !== shown.scoring_run_id) {
        setActionError('The server pinned a different calculation than the one shown. Reload and review it.');
      } else {
        setChangedFrom(null);
        setDecided(`${kind === 'approve' ? 'Approved' : 'Provisionally approved'}: the baseline is locked to `
          + `calculation ${res.data.scoring_run_id.slice(0, 8)} (Raw CRI ${res.data.overall_cri.toFixed(1)}).`);
      }
      setData((prev) => (prev ? { ...prev, baseline: res.data } : prev));
      refetch();
    } catch (err: any) {
      const body = err?.response?.data as BaselineChangedResponse | undefined;
      if (err?.response?.status === 409 && body?.baseline) {
        setChangedFrom({ cri: shown.overall_cri, run: shown.scoring_run_id });
        setData(body);
      } else {
        setActionError(getErrorMessage(err, kind === 'approve' ? 'Failed to approve the baseline.'
          : 'Failed to provisionally approve the baseline.'));
      }
    } finally {
      setActing(null);
    }
  };
  const handleApprove = () => decide('approve');
  const handleApproveProvisional = () => decide('provisional');

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

  /** Replace a decided baseline explicitly: a new pending cycle on the current data, with a reason. */
  const handleRevise = async () => {
    if (!sprintId || !reviseReason.trim()) return;
    setActing('revise');
    setActionError('');
    try {
      await reviseBaseline(sprintId, reviseReason.trim());
      setRevising(false);
      setReviseReason('');
      setDecided('');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to start a new baseline revision.'));
    } finally {
      setActing(null);
    }
  };

  /** Reason + confirm for opening a revision (the server requires the reason and checks the role). */
  const revisionControls = (label: string) => (revising ? (
    <div className="flex flex-col sm:flex-row gap-2">
      <input className="input flex-1 text-sm" value={reviseReason} onChange={(e) => setReviseReason(e.target.value)}
        placeholder="Why the decided baseline should be revised (required)" />
      <button className="btn-primary btn-sm" disabled={!reviseReason.trim() || acting !== null} onClick={handleRevise}>
        {acting === 'revise' ? 'Starting…' : 'Start revision'}
      </button>
      <button className="btn-secondary btn-sm" disabled={acting !== null} onClick={() => setRevising(false)}>Cancel</button>
    </div>
  ) : (
    <button className="btn-secondary btn-sm" onClick={() => setRevising(true)}>
      <RefreshCw className="w-3.5 h-3.5" /> {label}
    </button>
  ));

  const blockingGaps = (data?.high_priority_gaps || []).filter((g) => g.priority === 'blocking');
  const highPriorityGaps = data?.high_priority_gaps || [];

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div className="flex justify-end" data-tour="approval-header">
        <button onClick={() => navigate(`/sprint/${sprintId}/recommendations`)} className="btn-primary shrink-0">
          <span>Proceed to Recommendations</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {decided && (
        <div role="status" className="rounded-lg border border-success-line bg-success-bg p-3 text-sm text-success flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" /> {decided}
        </div>
      )}

      {loading ? (
        <LoadingState message="Loading baseline for approval..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !baseline || !scorecard ? (
        <LoadingState message="No score available for this sprint yet." />
      ) : (
        <>
          {isDecided && baseline.processing_incomplete && (
            <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-sm text-ink-700">
              <strong className="text-warning">Decided with incomplete document processing: </strong>
              {baseline.processing_snapshot?.description} Reason recorded: &ldquo;{baseline.processing_override_reason}&rdquo;
            </div>
          )}
          {!isDecided && changedFrom && (
            <div role="alert" className="rounded-lg border-2 border-warning-line bg-warning-bg p-3 text-sm text-ink-700 flex items-start gap-2">
              <RefreshCw className="w-4 h-4 text-warning shrink-0 mt-0.5" />
              <span>
                <strong className="text-warning">Not approved - the score changed. </strong>
                The sprint data changed after you loaded this page, so the baseline was recalculated: Raw CRI
                {' '}{changedFrom.cri.toFixed(1)} → <strong>{baseline.overall_cri.toFixed(1)}</strong>. Review the new
                snapshot below, then approve again.
              </span>
            </div>
          )}
          {!isDecided && !changedFrom && data?.refreshed && (
            <div className="rounded-lg border border-line-200 bg-surface p-3 text-sm text-ink-700 flex items-start gap-2">
              <RefreshCw className="w-4 h-4 text-brand-800 shrink-0 mt-0.5" />
              <span>The sprint data changed since this baseline was last calculated, so it now shows the latest
                calculation. Review it before approving.</span>
            </div>
          )}
          {!isDecided && baseline.revises && (
            <div className="rounded-lg border border-line-200 bg-surface p-3 text-sm text-ink-700">
              This is a <strong>revision</strong> of the decided baseline. That decision stays in force (and in reports)
              until this revision is approved.
            </div>
          )}
          {isDecided && baseline.status !== 'returned' && data?.baseline_is_current === false && (
            <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-sm text-ink-700 space-y-2">
              <p>
                <strong className="text-warning">The Live CRI has moved on since this decision: </strong>
                it is now {scorecard.overall_cri.toFixed(1)}. The baseline below keeps the {baseline.overall_cri.toFixed(1)} it
                was decided on (it never changes); strengths and areas for improvement further down show the Live CRI.
                Reports show both.
              </p>
              {can('sprint.manage') && revisionControls('Start a new baseline revision')}
            </div>
          )}
          {/* Local development only (never in a production build): open a revision of a CURRENT decided baseline to
              demonstrate the workflow. Same endpoint, same reason requirement and permissions; nothing is approved. */}
          {isLocalDev && isDecided && (baseline.status === 'approved' || baseline.status === 'provisional')
            && data?.baseline_is_current !== false && can('sprint.manage') && (
            <div className="rounded-lg border-2 border-dashed border-warning-line p-3 text-sm text-ink-700 space-y-2">
              <p>
                <span className="badge badge-warning mr-2">Local development only</span>
                Open a new revision cycle to demonstrate the workflow, although the score has not changed. The current
                decision stays in force and unchanged until the revision is decided.
              </p>
              {revisionControls('Start demo revision')}
            </div>
          )}

          {/* Approval Status + Score Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6" data-tour="approval-metrics-card">
            <div className="glass-card p-6 text-center">
              <span className="text-xs font-bold text-brand-800 uppercase tracking-wide">Baseline Raw CRI</span>
              <div className="text-3xl sm:text-4xl font-bold text-ink-900 my-3 tracking-tight tabular-nums">
                {baseline.overall_cri.toFixed(1)} <span className="text-base font-normal text-ink-500">/ 100</span>
              </div>
              <span className="text-xs text-ink-500">
                {(baseline.overall_confidence * 100).toFixed(0)}% evidence confidence
                {sprint ? ` · ${sprint.completion_percentage}% complete` : ''}
              </span>
              <p className="text-[11px] text-ink-500 mt-1 font-mono" title={baseline.scoring_run_id}>{runLabel(baseline)}</p>
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
              ) : !can('sprint.manage') ? (
                <div className="w-full mt-4 py-2.5 px-3 text-sm rounded-lg bg-line-100 text-ink-500 text-center border border-line-200">
                  Waiting for a decision. InGage or the institution admin approves or returns the baseline.
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
                  {!returning && data?.processing && !data.processing.complete && (
                    <label className="block text-xs text-ink-700 space-y-1">
                      <span className="font-semibold text-warning">
                        Documents are not fully processed. To approve anyway, record why (it is kept with the baseline
                        and printed in every report):
                      </span>
                      <textarea
                        value={overrideReason}
                        onChange={(e) => setOverrideReason(e.target.value)}
                        placeholder="Reason for deciding with incomplete processing (required to approve now)..."
                        rows={2}
                        className="input input-error"
                      />
                    </label>
                  )}
                  <div className="flex flex-col sm:flex-row items-stretch gap-2" data-tour="approval-actions">
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

          <EvidenceCoverageCard
            rawCri={baseline.overall_cri}
            adjustedCri={baseline.coverage_adjusted_cri}
            coverage={baseline.evidence_coverage}
            missingHint="This baseline's run was made before coverage existed."
          />

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

          {/* Decision history / audit trail: every cycle of the sprint, newest first (returned and replaced ones too) */}
          <ApprovalHistory cycles={data?.cycles?.length ? data.cycles : [baseline]} currentId={baseline.id} />
        </>
      )}
    </div>
  );
};
