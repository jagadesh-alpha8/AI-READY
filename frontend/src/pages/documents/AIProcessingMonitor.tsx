import React, { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getSprintAIUsage,
  listExtractionJobs,
  cancelSprintExtraction,
  cancelExtractionJob,
  deleteExtractionJob,
  processExtractionJob,
  processIncompleteExtraction,
} from '../../api/extraction';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { getErrorMessage, humanizeExtractionError } from '../../utils/errors';
import { formatDuration, formatEstimate, latestRunTiming, type RunTiming } from '../../utils/extractionTiming';
import {
  ACTIVE_EXTRACTION_STATUSES, type ExtractionJob, type Fact, type Gap, type SprintAIUsage,
} from '../../types';
import {
  Activity, CheckCircle2, AlertTriangle, ArrowRight, Cpu, Layers, XCircle, Loader2, Trash2, Square, Play, RotateCcw,
  Timer, Coins,
} from 'lucide-react';
import { useAccess } from '../../utils/access';

const POLL_INTERVAL_MS = 3000;

const STEP_LABELS = [
  'classifying_documents',
  'reading_pages',
  'extracting_facts',
  'mapping_audit_fields',
  'detecting_gaps',
  'checking_conflicts',
  'preparing_review_workspace',
];

export const AIProcessingMonitor: React.FC = () => {
  const { step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const { data: jobsData, loading, error, refetch } = useApiResource<ExtractionJob[]>(
    () => listExtractionJobs(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const jobs = jobsData || [];

  // Facts/gaps counts back the same four stat-card labels the original
  // design used ("Facts Extracted", "Gaps Detected", "Conflicts Detected")
  // -- ExtractionJob itself doesn't carry those counts, so they're fetched
  // alongside the jobs rather than the cards being relabeled.
  const { data: factsData, refetch: refetchFacts } = useApiResource<Fact[]>(
    () => listSprintFacts(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const { data: gapsData, refetch: refetchGaps } = useApiResource<Gap[]>(
    () => listSprintGaps(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const { data: usage, refetch: refetchUsage } = useApiResource<SprintAIUsage>(
    () => getSprintAIUsage(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const facts = factsData || [];
  const gaps = gapsData || [];
  const conflictCount = gaps.filter((g) => g.gap_type === 'conflict').length;

  const hasActiveJob = jobs.some((j) => ACTIVE_EXTRACTION_STATUSES.includes(j.status));
  // Rows the user can run again: failed or stopped.
  const incompleteCount = jobs.filter((j) => j.status === 'failed' || j.status === 'cancelled').length;
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const runRowAction = async (job: ExtractionJob, action: 'stop' | 'process') => {
    setBusyJobId(job.id);
    setActionError('');
    try {
      if (action === 'stop') await cancelExtractionJob(job.id);
      else await processExtractionJob(job.id);
      refetchAllRef.current();
    } catch (err) {
      setActionError(getErrorMessage(err, `Failed to ${action} "${job.document_filename}".`));
    } finally {
      setBusyJobId(null);
    }
  };

  const handleProcessIncomplete = async () => {
    setBulkBusy(true);
    setActionError('');
    try {
      await processIncompleteExtraction(sprintId!);
      refetchAllRef.current();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to start processing the unfinished documents.'));
    } finally {
      setBulkBusy(false);
    }
  };

  const handleStop = async () => {
    if (!window.confirm('Are you sure you want to stop the AI monitoring process? All active jobs will be cancelled.')) {
      return;
    }

    try {
      await cancelSprintExtraction(sprintId!);
      navigate(`/sprint/${sprintId}/upload`);
    } catch (err) {
      console.error('Failed to cancel extraction:', err);
      alert('Failed to stop the process. Please try again.');
    }
  };

  const handleDeleteJob = async (job: ExtractionJob) => {
    if (!window.confirm(`Delete this failed job for "${job.document_filename}"? You can start a fresh extraction run for this document afterwards.`)) {
      return;
    }

    try {
      await deleteExtractionJob(job.id);
      refetch();
    } catch (err) {
      console.error('Failed to delete extraction job:', err);
      alert('Failed to delete the job. Please try again.');
    }
  };

  const refetchAllRef = useRef(() => {
    refetch();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  });
  refetchAllRef.current = () => {
    refetch();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  };

  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = setInterval(() => refetchAllRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasActiveJob]);

  const completedCount = jobs.filter((j) => j.status === 'completed').length;

  // Ticks every second while a run is active, so elapsed / time-left update
  // between the 3-second data polls.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [hasActiveJob]);
  const run = latestRunTiming(jobs, hasActiveJob ? now : Date.now());

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Activity className="w-5 h-5 text-brand-800" /> Step {step('sprint-monitor')}: AI Processing Monitor
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Transparent tracking of document classification, table parsing, entity extraction, and gap identification.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {incompleteCount > 0 && (
              <button onClick={handleProcessIncomplete} disabled={bulkBusy} className="btn-secondary">
                <RotateCcw className={`w-4 h-4 ${bulkBusy ? 'animate-spin' : ''}`} />
                <span>{bulkBusy ? 'Starting…' : `Process Unfinished (${incompleteCount})`}</span>
              </button>
            )}
            {hasActiveJob && (
              <button onClick={handleStop} className="btn-secondary text-danger">
                <XCircle className="w-4 h-4" />
                <span>Stop Processing</span>
              </button>
            )}
            <button onClick={() => navigate(`/sprint/${sprintId}/facts`)} className="btn-primary shrink-0">
              <span>Proceed to Extracted Facts</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="p-3 rounded-lg border border-danger-line bg-danger-bg text-danger text-sm flex items-start justify-between gap-3">
          <span>{actionError}</span>
          <button onClick={() => setActionError('')} className="text-xs font-semibold shrink-0">Dismiss</button>
        </div>
      )}

      {loading ? (
        <LoadingState message="Loading extraction jobs..." />
      ) : error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : jobs.length === 0 ? (
        <div className="panel-muted">
          <p className="text-sm text-ink-500">
            No extraction jobs yet. Upload documents and start an extraction run first.
          </p>
        </div>
      ) : (
        <>
          {run && <RunTimingPanel run={run} />}
          {usage && usage.calls > 0 && <AIUsagePanel usage={usage} />}

          {/* Progress Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Documents Processed</span>
                <CheckCircle2 className="w-4 h-4 text-success" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{completedCount} / {jobs.length}</p>
              <span className="text-xs text-success mt-1 inline-block font-medium">
                {hasActiveJob ? 'OCR & Table Parsing in progress' : 'OCR & Table Parsing 100%'}
              </span>
            </div>

            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Facts Extracted</span>
                <Cpu className="w-4 h-4 text-brand-800" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{facts.length} Facts</p>
              <span className="text-xs text-brand-800 mt-1 inline-block font-medium">Mapped to Audit Fields</span>
            </div>

            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Gaps Detected</span>
                <AlertTriangle className="w-4 h-4 text-warning" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{gaps.length} Fields</p>
              <span className="text-xs text-warning mt-1 inline-block font-medium">Assigned to Owners</span>
            </div>

            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Conflicts Detected</span>
                <Layers className="w-4 h-4 text-accent" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{conflictCount} Conflict{conflictCount === 1 ? '' : 's'}</p>
              <span className="text-xs text-accent mt-1 inline-block font-medium">
                {conflictCount > 0 ? 'Review in Gap Dashboard' : 'None detected'}
              </span>
            </div>
          </div>

          {/* Extraction Pipeline Progress -- one row per job, in the fixed stage order */}
          <div className="glass-card p-5 sm:p-6 space-y-4">
            <h2 className="eyebrow">AI Task Contract Pipeline Status</h2>
            <div className="space-y-3">
              {jobs.map((job) => {
                const stepIndex = STEP_LABELS.indexOf(job.current_step);
                const isActive = ACTIVE_EXTRACTION_STATUSES.includes(job.status);
                const canProcess = job.status === 'failed' || job.status === 'cancelled';
                const rowBusy = busyJobId === job.id;
                const Icon =
                  job.status === 'completed'
                    ? CheckCircle2
                    : job.status === 'failed'
                    ? XCircle
                    : job.status === 'cancelled'
                    ? Square
                    : Loader2;
                const iconClass =
                  job.status === 'completed'
                    ? 'text-success bg-success-bg border-success-line'
                    : job.status === 'failed'
                    ? 'text-danger bg-danger-bg border-danger-line'
                    : job.status === 'cancelled'
                    ? 'text-ink-500 bg-line-100 border-line-300'
                    : 'text-brand-800 bg-brand-500/10 border-brand-500/30';
                const badgeClass =
                  job.status === 'completed'
                    ? 'badge-success'
                    : job.status === 'failed'
                    ? 'badge-danger'
                    : job.status === 'cancelled'
                    ? 'badge-neutral'
                    : 'badge-brand';
                return (
                  <div
                    key={job.id}
                    className="p-3.5 bg-surface rounded-xl border border-line-200 flex items-center justify-between gap-3 flex-wrap"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${iconClass}`}>
                        <Icon className={`w-4 h-4 ${job.status === 'running' || job.status === 'retrying' ? 'animate-spin' : ''}`} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-ink-900 truncate">{job.document_filename}</p>
                        <p className="text-xs text-ink-500">
                          {job.status === 'cancelled'
                            ? job.current_step_label
                              ? `Stopped at: ${job.current_step_label}`
                              : 'Stopped before it started'
                            : job.current_step_label || 'Queued'}
                          {stepIndex >= 0 && ` (step ${stepIndex + 1} of ${STEP_LABELS.length})`}
                          {job.ai_router && ` · ${job.ai_router}`}
                        </p>
                        {job.status === 'failed' && job.error_message && (
                          <p className="text-xs text-danger mt-0.5">
                            {humanizeExtractionError(job.error_message, false)}
                          </p>
                        )}
                        {job.status === 'retrying' && job.error_message && (
                          <p className="text-xs text-warning mt-0.5">
                            {humanizeExtractionError(job.error_message, true)}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {job.ai_input_tokens + job.ai_output_tokens > 0 && (
                        <span
                          className="text-xs text-ink-500 tabular-nums"
                          title={`AI: ${job.ai_input_tokens.toLocaleString()} input + ${job.ai_output_tokens.toLocaleString()} output tokens`}
                        >
                          {formatTokens(job.ai_input_tokens + job.ai_output_tokens)} tokens
                          {job.ai_cost_usd !== null && ` · ${formatUsd(job.ai_cost_usd)}`}
                        </span>
                      )}
                      <span className="text-sm font-mono text-ink-500 tabular-nums">{job.progress_percentage}%</span>
                      <span className={badgeClass}>{job.status === 'cancelled' ? 'stopped' : job.status}</span>
                      {isActive && (
                        <button
                          onClick={() => runRowAction(job, 'stop')}
                          disabled={rowBusy}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg border border-danger/40 text-danger hover:bg-danger/10 transition-colors disabled:opacity-60"
                          title={job.status === 'pending' ? 'Remove from the queue' : 'Stop after the current step'}
                        >
                          <Square className="w-3 h-3 fill-current" />
                          <span>{rowBusy ? 'Stopping…' : 'Stop'}</span>
                        </button>
                      )}
                      {canProcess && (
                        <button
                          onClick={() => runRowAction(job, 'process')}
                          disabled={rowBusy}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-brand-500 text-on-brand hover:brightness-95 transition-all disabled:opacity-60"
                          title="Run AI extraction for this document again"
                        >
                          <Play className="w-3 h-3 fill-current" />
                          <span>{rowBusy ? 'Starting…' : 'Process'}</span>
                        </button>
                      )}
                      {job.status === 'failed' && (
                        <button
                          onClick={() => handleDeleteJob(job)}
                          className="btn-icon hover:text-danger hover:bg-danger-bg"
                          title="Delete Failed Job"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** Elapsed time, rounded time-left estimate, and a finished-run summary. */
const RunTimingPanel: React.FC<{ run: RunTiming }> = ({ run }) => {
  const finished = run.completed + run.failed + run.stopped;
  const outcome = [
    run.failed > 0 && `${run.failed} failed`,
    run.stopped > 0 && `${run.stopped} stopped`,
  ].filter(Boolean).join(' · ');

  return (
    <div className="glass-card p-5 flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="w-10 h-10 rounded-lg border border-brand-500/30 bg-brand-500/10 text-brand-800 flex items-center justify-center shrink-0">
        <Timer className="w-5 h-5" />
      </div>

      {run.waitingToStart ? (
        <div>
          <p className="text-sm font-bold text-ink-900">Queued: waiting for the extraction worker to start</p>
          <p className="text-xs text-ink-500 mt-0.5">
            {run.total} document{run.total === 1 ? '' : 's'} in the queue. If this doesn't change for a few minutes,
            the worker may not be running.
          </p>
        </div>
      ) : run.active ? (
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <p className="text-xs text-ink-500">Running for</p>
            <p className="text-lg font-bold text-ink-900 tabular-nums">{formatDuration(run.elapsedMs)}</p>
            {run.startedAt !== null && <p className="text-xs text-ink-500">started {clock(run.startedAt)}</p>}
          </div>
          <div>
            <p className="text-xs text-ink-500">Progress this run</p>
            <p className="text-lg font-bold text-ink-900 tabular-nums">{finished} / {run.total}</p>
            <p className="text-xs text-ink-500">{run.remaining} remaining{outcome && ` · ${outcome}`}</p>
          </div>
          <div>
            <p className="text-xs text-ink-500">Estimated time left</p>
            {run.etaRangeMs ? (
              <>
                <p className="text-lg font-bold text-ink-900">{formatEstimate(run.etaRangeMs)}</p>
                <p className="text-xs text-ink-500">based on documents finished so far; sizes vary</p>
              </>
            ) : (
              <>
                <p className="text-lg font-bold text-ink-500">Calculating…</p>
                <p className="text-xs text-ink-500">shown after a few documents finish</p>
              </>
            )}
          </div>
        </div>
      ) : (
        <div>
          <p className="text-sm font-bold text-ink-900">
            Last run: {finished} document{finished === 1 ? '' : 's'} in {formatDuration(run.elapsedMs)}
          </p>
          <p className="text-xs text-ink-500 mt-0.5">
            {run.startedAt !== null && `${clock(run.startedAt)} – ${clock(run.finishedAt ?? run.startedAt)}`}
            {run.avgPerDocMs !== null && ` · about ${formatDuration(run.avgPerDocMs)} per document`}
            {` · ${run.completed} completed`}
            {outcome && ` · ${outcome}`}
          </p>
        </div>
      )}
    </div>
  );
};

const STAGE_LABELS: Record<string, string> = {
  classification: 'Classification',
  fact_extraction: 'Fact extraction',
  conflict_check: 'Conflict check',
  other: 'Other',
};

/** 1234 -> "1.2K", 3456789 -> "3.46M". */
const formatTokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : String(n);

/** Exact decimal string -> "$0.021", "$3.14". */
const formatUsd = (value: string) => {
  const n = Number(value);
  return `$${n >= 1 ? n.toFixed(2) : n.toFixed(3)}`;
};

/** Real AI tokens and cost recorded for this sprint -- the basis for billing. */
const AIUsagePanel: React.FC<{ usage: SprintAIUsage }> = ({ usage }) => (
  <div className="glass-card p-5 space-y-3">
    <div className="flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="w-10 h-10 rounded-lg border border-brand-500/30 bg-brand-500/10 text-brand-800 flex items-center justify-center shrink-0">
        <Coins className="w-5 h-5" />
      </div>
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <p className="text-xs text-ink-500">AI cost (this sprint)</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{formatUsd(usage.cost_usd)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-500">Input tokens</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{formatTokens(usage.input_tokens + usage.cache_read_tokens)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-500">Output tokens</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{formatTokens(usage.output_tokens)}</p>
        </div>
        <div>
          <p className="text-xs text-ink-500">AI calls · documents</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{usage.calls} · {usage.documents || '—'}</p>
        </div>
      </div>
    </div>
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500">
      {usage.by_stage.map((row) => (
        <span key={row.stage}>
          {STAGE_LABELS[row.stage] || row.stage}: {formatTokens(row.total_tokens)} tokens · {formatUsd(row.cost_usd)}
        </span>
      ))}
      {usage.by_model.length > 0 && (
        <span>Model{usage.by_model.length > 1 ? 's' : ''}: {usage.by_model.map((m) => m.model).join(', ')}</span>
      )}
    </div>
    {usage.imported_calls + usage.estimated_calls > 0 && (
      <p className="text-xs text-info" title={usage.notes.join(' | ')}>
        Includes {usage.imported_calls > 0 && `${usage.imported_calls} request${usage.imported_calls === 1 ? '' : 's'} imported from a provider dashboard`}
        {usage.imported_calls > 0 && usage.estimated_calls > 0 && ' and '}
        {usage.estimated_calls > 0 && `${usage.estimated_calls} estimated`} (totals only, not per document).
        {usage.notes.length > 0 && ` Source: ${usage.notes.join(' | ')}`}
      </p>
    )}
    {usage.unpriced_calls > 0 && (
      <p className="text-xs text-warning">
        {usage.unpriced_calls} call{usage.unpriced_calls === 1 ? '' : 's'} used a model with no configured price
        ({usage.unpriced_models.join(', ')}), so the cost above is incomplete. Tokens are still counted.
      </p>
    )}
  </div>
);
