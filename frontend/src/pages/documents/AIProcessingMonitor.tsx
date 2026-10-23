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
  startExtraction,
} from '../../api/extraction';
import { listSprintDocuments } from '../../api/documents';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { getErrorMessage, humanizeExtractionError } from '../../utils/errors';
import { formatDuration, formatEstimate, latestRunTiming, type RunTiming } from '../../utils/extractionTiming';
import {
  ACTIVE_EXTRACTION_STATUSES, type ExtractionJob, type Fact, type Gap, type SprintAIUsage,
} from '../../types';
import type { SprintDocument } from '../../types/documents';
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

type DocState = 'complete' | 'partial' | 'failed' | 'active' | 'not_processed' | 'excluded';

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
  const { data: documentsData, loading: documentsLoading, error: documentsError, refetch: refetchDocuments } =
    useApiResource<SprintDocument[]>(() => listSprintDocuments(sprintId!), [sprintId], isRealSprint);
  const documents = documentsData || [];
  const latestJobByDocument = new Map<string, ExtractionJob>();
  for (const job of [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    if (!latestJobByDocument.has(job.document_id)) latestJobByDocument.set(job.document_id, job);
  }

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
  const factCountsByDocument = new Map<string, number>();
  for (const fact of facts) {
    const documentId = fact.document_id || fact.source_document_id;
    if (documentId) factCountsByDocument.set(documentId, (factCountsByDocument.get(documentId) || 0) + 1);
  }
  const gaps = gapsData || [];
  const conflictCount = gaps.filter((g) => g.gap_type === 'conflict').length;

  const hasActiveJob = jobs.some((j) => ACTIVE_EXTRACTION_STATUSES.includes(j.status));
  // Rows the user can run again: not processed, failed, stopped, or partially extracted.
  const isPartial = (job?: ExtractionJob) => job?.status === 'completed' && job.completeness === 'partial';
  const incompleteDocuments = documents.filter((doc) => {
    if (doc.status === 'rejected' || doc.superseded_at) return false;
    const job = latestJobByDocument.get(doc.id);
    return !job || isPartial(job) || (job.status !== 'completed' && !ACTIVE_EXTRACTION_STATUSES.includes(job.status));
  });
  const incompleteCount = incompleteDocuments.length;
  const [busyJobId, setBusyJobId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  // Document list filter: a processing state (the count chips) and a filename search.
  const [stateFilter, setStateFilter] = useState<DocState | 'all'>('all');
  const [search, setSearch] = useState('');

  const runRowAction = async (document: SprintDocument, job: ExtractionJob | undefined, action: 'stop' | 'process') => {
    setBusyJobId(document.id);
    setActionError('');
    try {
      if (!job) await startExtraction(sprintId!, [document.id]);
      else if (action === 'stop') await cancelExtractionJob(job.id);
      else await processExtractionJob(job.id);
      refetchAllRef.current();
    } catch (err) {
      setActionError(getErrorMessage(err, `Failed to ${action} "${document.original_filename}".`));
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
      refetchAllRef.current();
    } catch (err) {
      console.error('Failed to delete extraction job:', err);
      alert('Failed to delete the job. Please try again.');
    }
  };

  const refetchAllRef = useRef(() => {
    refetch();
    refetchDocuments();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  });
  refetchAllRef.current = () => {
    refetch();
    refetchDocuments();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  };

  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = setInterval(() => refetchAllRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasActiveJob]);

  // The same five states as the server (apps/extraction/services/completeness.py) and the baseline gate.
  const includedDocuments = documents.filter((doc) => doc.status !== 'rejected' && !doc.superseded_at);
  const completedCount = includedDocuments.filter((doc) => {
    const job = latestJobByDocument.get(doc.id);
    return job?.status === 'completed' && !isPartial(job);
  }).length;
  const partialCount = includedDocuments.filter((doc) => isPartial(latestJobByDocument.get(doc.id))).length;
  const notProcessedCount = includedDocuments.filter((doc) => !latestJobByDocument.get(doc.id)).length;
  const processingCount = includedDocuments.filter((doc) => {
    const status = latestJobByDocument.get(doc.id)?.status;
    return !!status && ACTIVE_EXTRACTION_STATUSES.includes(status);
  }).length;
  const needsAttentionCount = documents.filter((doc) => {
    const job = latestJobByDocument.get(doc.id);
    return !doc.superseded_at && doc.status !== 'rejected' && !!job && ['failed', 'cancelled'].includes(job.status);
  }).length;
  const allComplete = includedDocuments.length > 0 && completedCount === includedDocuments.length;
  const excludedCount = documents.length - includedDocuments.length;
  // The same states as the counts above, per document, for the list filter.
  const docState = (doc: SprintDocument): DocState => {
    if (doc.status === 'rejected' || doc.superseded_at) return 'excluded';
    const job = latestJobByDocument.get(doc.id);
    if (!job) return 'not_processed';
    if (ACTIVE_EXTRACTION_STATUSES.includes(job.status)) return 'active';
    if (job.status === 'completed') return isPartial(job) ? 'partial' : 'complete';
    return 'failed';
  };
  const needle = search.trim().toLowerCase();
  const shownDocuments = documents.filter((doc) =>
    (stateFilter === 'all' || docState(doc) === stateFilter)
    && (!needle || (doc.original_filename || '').toLowerCase().includes(needle)));

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

      {loading || documentsLoading ? (
        <LoadingState message="Loading extraction jobs..." />
      ) : error || documentsError ? (
        <ErrorState message={getErrorMessage(error || documentsError, 'Could not load sprint processing status.')} onRetry={() => { refetch(); refetchDocuments(); }} />
      ) : documents.length === 0 ? (
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
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{completedCount} / {includedDocuments.length}</p>
              <span className={`text-xs mt-1 inline-block font-medium ${allComplete ? 'text-success' : 'text-warning'}`}>
                {allComplete ? 'All included documents fully processed' : 'Not all documents are fully processed'}
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

          {/* One count per state; only "fully processed" counts as done (review, CRI, baseline and reports say so too). */}
          <div className="glass-card p-4 flex flex-wrap items-center gap-2 text-xs">
            {([
              ['all', 'All', includedDocuments.length + excludedCount, 'badge-neutral'],
              ['complete', 'Fully processed', completedCount, 'badge-success'],
              ['partial', 'Partially processed', partialCount, partialCount ? 'badge-warning' : 'badge-neutral'],
              ['failed', 'Failed or stopped', needsAttentionCount, needsAttentionCount ? 'badge-danger' : 'badge-neutral'],
              ['active', 'Processing', processingCount, processingCount ? 'badge-info' : 'badge-neutral'],
              ['not_processed', 'Not processed yet', notProcessedCount, notProcessedCount ? 'badge-warning' : 'badge-neutral'],
              ['excluded', 'Rejected / earlier versions', excludedCount, 'badge-neutral'],
            ] as [DocState | 'all', string, number, string][]).map(([key, label, count, cls]) => (
              <button key={key} type="button" onClick={() => setStateFilter(key)} aria-pressed={stateFilter === key}
                className={`${cls} cursor-pointer ${stateFilter === key ? 'ring-2 ring-brand-500' : 'opacity-80 hover:opacity-100'}`}
                title={`Show ${label.toLowerCase()} documents`}>
                {label} {count}
              </button>
            ))}
            <input className="input text-xs ml-auto w-56" placeholder="Search file name…" value={search}
              onChange={(e) => setSearch(e.target.value)} />
            {!allComplete && !hasActiveJob && (
              <span className="text-ink-600">
                Partial and failed documents can be processed again; facts are updated in place, never duplicated.
              </span>
            )}
          </div>

          {/* Sprint coverage includes documents without a job, so an unqueued item is visible. */}
          <div className="glass-card p-5 sm:p-6 space-y-4">
            <h2 className="eyebrow">Sprint Document Processing ({completedCount}/{includedDocuments.length} fully processed)</h2>
            {(stateFilter !== 'all' || search.trim()) && (
              <p className="text-xs text-ink-500">
                Showing {shownDocuments.length} of {documents.length} documents.{' '}
                <button type="button" className="text-brand-800 hover:underline" onClick={() => { setStateFilter('all'); setSearch(''); }}>
                  Clear filter
                </button>
              </p>
            )}
            {shownDocuments.length === 0 && <p className="text-sm text-ink-500">No documents match this filter.</p>}
            <div className="space-y-3">
              {shownDocuments.map((document) => {
                const job = latestJobByDocument.get(document.id);
                const status = job?.status || 'not_started';
                const documentFactCount = factCountsByDocument.get(document.id) || 0;
                const partial = isPartial(job);
                const completedWithoutFacts = status === 'completed' && !partial && documentFactCount === 0;
                const stepIndex = job ? STEP_LABELS.indexOf(job.current_step) : -1;
                const isActive = !!job && ACTIVE_EXTRACTION_STATUSES.includes(job.status);
                const canProcess = document.status !== 'rejected' && !isActive && (!job || job.status !== 'completed' || partial);
                const rowBusy = busyJobId === document.id;
                const Icon =
                  completedWithoutFacts || partial
                    ? AlertTriangle
                    : status === 'completed'
                    ? CheckCircle2
                    : status === 'failed'
                    ? XCircle
                    : status === 'cancelled'
                    ? Square
                    : Loader2;
                const iconClass =
                  completedWithoutFacts || partial
                    ? 'text-warning bg-warning-bg border-warning-line'
                    : status === 'completed'
                    ? 'text-success bg-success-bg border-success-line'
                    : status === 'failed'
                    ? 'text-danger bg-danger-bg border-danger-line'
                    : status === 'cancelled'
                    ? 'text-ink-500 bg-line-100 border-line-300'
                    : 'text-brand-800 bg-brand-500/10 border-brand-500/30';
                const badgeClass =
                  completedWithoutFacts || partial
                    ? 'badge-warning'
                    : status === 'completed'
                    ? 'badge-success'
                    : status === 'failed'
                    ? 'badge-danger'
                    : status === 'cancelled'
                    ? 'badge-neutral'
                    : status === 'not_started'
                    ? 'badge-warning'
                    : 'badge-brand';
                return (
                  <div
                    key={document.id}
                    className="p-3.5 bg-surface rounded-xl border border-line-200 flex items-center justify-between gap-3 flex-wrap"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${iconClass}`}>
                        <Icon className={`w-4 h-4 ${job?.status === 'running' || job?.status === 'retrying' ? 'animate-spin' : ''}`} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-ink-900 truncate">{document.original_filename}{document.version_number > 1 ? ` · v${document.version_number}` : ''}</p>
                        <p className="text-xs text-ink-500">
                          {!job ? 'Not yet queued in this sprint'
                            : job.status === 'cancelled'
                            ? job.current_step_label
                              ? `Stopped at: ${job.current_step_label}`
                              : 'Stopped before it started'
                            : job.current_step_label || 'Queued'}
                          {stepIndex >= 0 && ` (step ${stepIndex + 1} of ${STEP_LABELS.length})`}
                          {job?.ai_router && ` · ${job.ai_router}`}
                        </p>
                        {partial && job && (
                          <div className="text-xs text-warning mt-0.5 space-y-0.5">
                            <p className="font-semibold">
                              Partially processed: {job.chunks_completed} of {job.chunks_total} text chunk{job.chunks_total === 1 ? '' : 's'} read
                              {' '}· {documentFactCount} fact{documentFactCount === 1 ? '' : 's'} extracted. Some content was not read.
                            </p>
                            {job.extraction_warnings.map((w, i) => <p key={i}>• {w.detail}</p>)}
                          </div>
                        )}
                        {status === 'completed' && !partial && (
                          <p className={`text-xs mt-0.5 ${completedWithoutFacts ? 'text-warning' : 'text-ink-500'}`}>
                            {completedWithoutFacts
                              ? 'Processing completed, but no facts were extracted. Check the PDF text/pages and extraction logs.'
                              : `${documentFactCount} fact${documentFactCount === 1 ? '' : 's'} extracted`}
                          </p>
                        )}
                        {job?.status === 'failed' && job.error_message && (
                          <p className="text-xs text-danger mt-0.5">
                            {humanizeExtractionError(job.error_message, false)}
                          </p>
                        )}
                        {job?.status === 'retrying' && job.error_message && (
                          <p className="text-xs text-warning mt-0.5">
                            {humanizeExtractionError(job.error_message, true)}
                          </p>
                        )}
                        {document.superseded_at && <p className="text-xs text-ink-500 mt-0.5">Earlier file version retained for sprint history</p>}
                        {!job && document.status === 'failed' && <p className="text-xs text-danger mt-0.5">Document processing failed before a job was recorded.</p>}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {job && job.ai_input_tokens + job.ai_output_tokens > 0 && (
                        <span
                          className="text-xs text-ink-500 tabular-nums"
                          title={`AI: ${job.ai_input_tokens.toLocaleString()} input + ${job.ai_output_tokens.toLocaleString()} output tokens`}
                        >
                          {formatTokens(job.ai_input_tokens + job.ai_output_tokens)} tokens
                          {job.ai_cost_usd !== null && ` · ${formatUsd(job.ai_cost_usd)}`}
                        </span>
                      )}
                      <span className="text-sm font-mono text-ink-500 tabular-nums">{job?.progress_percentage || 0}%</span>
                      <span className={badgeClass}>
                        {partial ? 'partial' : completedWithoutFacts ? 'completed · 0 facts' : status === 'not_started' ? 'not started' : status === 'cancelled' ? 'stopped' : status}
                      </span>
                      {isActive && (
                        <button
                          onClick={() => runRowAction(document, job, 'stop')}
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
                          onClick={() => runRowAction(document, job, 'process')}
                          disabled={rowBusy}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-brand-500 text-on-brand hover:brightness-95 transition-all disabled:opacity-60"
                          title={partial ? 'Process again to read what was missed (facts are updated, never duplicated)'
                            : job ? 'Retry extraction for this document in this sprint' : 'Start extraction for this document in this sprint'}
                        >
                          <Play className="w-3 h-3 fill-current" />
                          <span>{rowBusy ? 'Starting…' : 'Process'}</span>
                        </button>
                      )}
                      {job?.status === 'failed' && (
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
  // One request that classified the document and extracted its first chunk's facts; tokens are not split.
  document_analysis: 'Document analysis (classification + facts)',
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
