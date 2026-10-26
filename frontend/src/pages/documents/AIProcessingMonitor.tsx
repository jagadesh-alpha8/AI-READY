import React, { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getProcessingSummary,
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
import { getSprintFactFacets, type FactFacets } from '../../api/facts';
import { getSprintGapFacets, type GapFacets } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { getErrorMessage, humanizeExtractionError } from '../../utils/errors';
import { formatDuration, formatEstimate, latestRunTiming, type RunTiming } from '../../utils/extractionTiming';
import {
  ACTIVE_EXTRACTION_STATUSES, type ExtractionJob, type ProcessingSummary, type SprintAIUsage,
} from '../../types';
import type { SprintDocument } from '../../types/documents';
import {
  Activity, CheckCircle2, AlertTriangle, ArrowRight, Cpu, Layers, XCircle, Loader2, Trash2, Square, Play, RotateCcw,
  Timer, Coins,
} from 'lucide-react';
import { useAccess } from '../../utils/access';

const POLL_INTERVAL_MS = 3000;
/** The AI usage panel (cost, tokens, requests) is hidden for now; set to true to show it again. */
const SHOW_AI_USAGE = false;

const STEP_LABELS = [
  'classifying_documents',
  'reading_pages',
  'extracting_facts',
  'mapping_audit_fields',
  'detecting_gaps',
  'checking_conflicts',
  'preparing_review_workspace',
];

// Current documents: the five server states (apps/extraction/services/completeness.py), which add up to the
// current-document total. Not current: earlier versions and rejected documents, never in those counts.
type DocState = 'complete' | 'partial' | 'failed' | 'active' | 'not_processed' | 'earlier_version' | 'rejected';

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
  // Every count, chip and row state comes from the server's processing summary, so this page, the review
  // screens and the baseline gate use one definition; the jobs list only adds per-row detail.
  const { data: summary, loading: summaryLoading, error: summaryError, refetch: refetchSummary } =
    useApiResource<ProcessingSummary>(() => getProcessingSummary(sprintId!), [sprintId], isRealSprint);
  const stateByDocument = new Map<string, DocState>();
  const excludedLabel = new Map<string, string>();
  for (const row of summary?.documents || []) stateByDocument.set(row.document_id, row.state);
  for (const row of summary?.excluded_documents || []) {
    stateByDocument.set(row.document_id, row.state);
    excludedLabel.set(row.document_id, row.label);
  }
  const latestJobByDocument = new Map<string, ExtractionJob>();
  for (const job of [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    if (!latestJobByDocument.has(job.document_id)) latestJobByDocument.set(job.document_id, job);
  }

  // Fact / gap / conflict counts for the stat cards and each row: database aggregates (facets), never the
  // whole fact and gap lists.
  const { data: factFacets, refetch: refetchFacts } = useApiResource<FactFacets>(
    () => getSprintFactFacets(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const { data: gapFacets, refetch: refetchGaps } = useApiResource<GapFacets>(
    () => getSprintGapFacets(sprintId!),
    [sprintId],
    isRealSprint,
  );
  const { data: usage, refetch: refetchUsage } = useApiResource<SprintAIUsage>(
    () => getSprintAIUsage(sprintId!),
    [sprintId],
    isRealSprint && SHOW_AI_USAGE,
  );
  const factCountsByDocument = new Map<string, number>(Object.entries(factFacets?.by_document || {}));
  const factTotal = factFacets?.total ?? 0;
  const gapTotal = gapFacets?.total ?? 0;
  const conflictCount = gapFacets?.gap_type?.conflict ?? 0;

  const hasActiveJob = jobs.some((j) => ACTIVE_EXTRACTION_STATUSES.includes(j.status));
  const isPartial = (job?: ExtractionJob) => job?.status === 'completed' && job.completeness === 'partial';
  // Current documents the user can run again: not processed, failed, stopped, or partially extracted.
  const counts = summary?.counts;
  const incompleteCount = counts ? counts.partial + counts.failed + counts.not_processed : 0;
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
    refetchSummary();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  });
  refetchAllRef.current = () => {
    refetch();
    refetchDocuments();
    refetchSummary();
    refetchFacts();
    refetchGaps();
    refetchUsage();
  };

  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = setInterval(() => refetchAllRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasActiveJob]);

  const currentTotal = counts?.total ?? 0;
  const completedCount = counts?.complete ?? 0;
  const partialCount = counts?.partial ?? 0;
  const failedCount = counts?.failed ?? 0;
  const processingCount = counts?.active ?? 0;
  const notProcessedCount = counts?.not_processed ?? 0;
  const earlierVersionCount = summary?.excluded?.earlier_version ?? 0;
  const rejectedCount = summary?.excluded?.rejected ?? 0;
  const allComplete = currentTotal > 0 && completedCount === currentTotal;
  // A document uploaded after the summary was fetched has no state yet: shown as not started until the next poll.
  const docState = (doc: SprintDocument): DocState => stateByDocument.get(doc.id) || 'not_processed';
  const isCurrent = (doc: SprintDocument) => !['earlier_version', 'rejected'].includes(docState(doc));
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

      {loading || documentsLoading || (summaryLoading && !summary) ? (
        <LoadingState message="Loading extraction jobs..." />
      ) : error || documentsError || summaryError ? (
        <ErrorState message={getErrorMessage(error || documentsError || summaryError, 'Could not load sprint processing status.')}
          onRetry={() => { refetch(); refetchDocuments(); refetchSummary(); }} />
      ) : documents.length === 0 ? (
        <div className="panel-muted">
          <p className="text-sm text-ink-500">
            No extraction jobs yet. Upload documents and start an extraction run first.
          </p>
        </div>
      ) : (
        <>
          {/* Only while documents are processing: progress and time left. A finished run is summarised by the
              sprint counts and document statuses below. */}
          {run?.active && <RunTimingPanel run={run} />}
          {SHOW_AI_USAGE && usage && usage.calls > 0 && <AIUsagePanel usage={usage} currentTotal={currentTotal} />}

          {/* Progress Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Fully processed current documents</span>
                <CheckCircle2 className="w-4 h-4 text-success" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{completedCount} / {currentTotal}</p>
              <span className={`text-xs mt-1 inline-block font-medium ${allComplete ? 'text-success' : 'text-warning'}`}>
                {allComplete ? 'All current documents fully processed'
                  : `${currentTotal - completedCount} current document${currentTotal - completedCount === 1 ? '' : 's'} not fully processed`}
              </span>
            </div>

            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Facts Extracted</span>
                <Cpu className="w-4 h-4 text-brand-800" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{factTotal} Facts</p>
              <span className="text-xs text-brand-800 mt-1 inline-block font-medium">Mapped to Audit Fields</span>
            </div>

            <div className="glass-card p-5">
              <div className="flex items-center justify-between text-ink-500">
                <span className="text-sm font-medium">Gaps Detected</span>
                <AlertTriangle className="w-4 h-4 text-warning" />
              </div>
              <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{gapTotal} Fields</p>
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
          <div className="glass-card p-4 space-y-3 text-xs">
            <div>
              <p className="text-sm font-semibold text-ink-900">Current documents: {currentTotal}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {([
                ['all', 'All files', documents.length, 'badge-neutral'],
                ['complete', 'Fully processed', completedCount, 'badge-success'],
                ['partial', 'Partially processed', partialCount, partialCount ? 'badge-warning' : 'badge-neutral'],
                ['failed', 'Failed or stopped', failedCount, failedCount ? 'badge-danger' : 'badge-neutral'],
                ['active', 'Processing', processingCount, processingCount ? 'badge-info' : 'badge-neutral'],
                ['not_processed', 'Not started', notProcessedCount, notProcessedCount ? 'badge-warning' : 'badge-neutral'],
                ['earlier_version', 'Earlier versions', earlierVersionCount, 'badge-neutral'],
                ['rejected', 'Rejected documents', rejectedCount, 'badge-neutral'],
              ] as [DocState | 'all', string, number, string][]).map(([key, label, count, cls]) => (
                <React.Fragment key={key}>
                  {key === 'earlier_version' && <span className="text-ink-500 ml-2">Not current:</span>}
                  <button type="button" onClick={() => setStateFilter(key)} aria-pressed={stateFilter === key}
                    className={`${cls} cursor-pointer ${stateFilter === key ? 'ring-2 ring-brand-500' : 'opacity-80 hover:opacity-100'}`}
                    title={`Show ${label.toLowerCase()}`}>
                    {label} {count}
                  </button>
                </React.Fragment>
              ))}
              <input className="input text-xs ml-auto w-56" placeholder="Search file name…" value={search}
                onChange={(e) => setSearch(e.target.value)} />
            </div>
          </div>

          {/* Sprint coverage includes documents without a job, so an unqueued item is visible. */}
          <div className="glass-card p-5 sm:p-6 space-y-4">
            <h2 className="eyebrow">Sprint Document Processing ({completedCount}/{currentTotal} current documents fully processed)</h2>
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
                const current = isCurrent(document);
                const canProcess = current && !isActive && (!job || job.status !== 'completed' || partial);
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
                          {!current ? excludedLabel.get(document.id)
                            : !job ? 'Not yet queued in this sprint'
                            : job.status === 'cancelled'
                            ? job.current_step_label
                              ? `Stopped at: ${job.current_step_label}`
                              : 'Stopped before it started'
                            : job.current_step_label || 'Queued'}
                          {current && stepIndex >= 0 && ` (step ${stepIndex + 1} of ${STEP_LABELS.length})`}
                          {current && job?.ai_router && ` · ${job.ai_router}`}
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
                        {current && job && (job.attempts || []).filter((a) => a.outcome !== 'reset').length > 1 && (
                          <details className="text-xs text-ink-500 mt-0.5">
                            <summary className="cursor-pointer">
                              {(job.attempts || []).filter((a) => a.outcome === 'out_of_credit').length > 0
                                ? 'Moved to another AI router (a router ran out of credit)' : 'Processed in more than one attempt'}
                              {' '}— each attempt's AI calls are billed
                            </summary>
                            <ul className="mt-0.5 space-y-0.5">
                              {(job.attempts || []).filter((a) => a.outcome !== 'reset').slice(-8).map((a, i) => (
                                <li key={i}>
                                  {new Date(a.at).toLocaleString()} · {a.router || 'no router'} · {a.outcome.replace(/_/g, ' ')}
                                  {a.detail && ` — ${a.detail}`}
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                        {!current && job && (
                          <p className="text-xs text-ink-500 mt-0.5">Its earlier processing ({job.status}) is kept for sprint history.</p>
                        )}
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
                        {!current ? (docState(document) === 'rejected' ? 'rejected' : 'earlier version')
                          : partial ? 'partial' : completedWithoutFacts ? 'completed · 0 facts' : status === 'not_started' ? 'not started' : status === 'cancelled' ? 'stopped' : status}
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

const OUTCOME_CLASS: Record<string, string> = {
  'fully processed': 'text-success', 'partially processed': 'text-warning', failed: 'text-danger',
  stopped: 'text-ink-500', processing: 'text-brand-800', queued: 'text-ink-500',
};

/** Which jobs the activity groups, how its time is measured, and each document in it with its outcome. */
const ActivityDetails: React.FC<{ run: RunTiming }> = ({ run }) => (
  <details className="text-xs text-ink-600 mt-2">
    <summary className="cursor-pointer text-brand-800">
      Which documents? ({run.jobs.length} document{run.jobs.length === 1 ? '' : 's'} in this activity)
    </summary>
    <p className="mt-1 text-ink-500">
      This is the latest group of extraction jobs whose processing overlapped or started within 5 minutes of each
      other (there is no separate batch id). A document processed again counts only in the activity of its latest
      attempt. Duration is from the first job's start to the last job's finish. It is recent activity, not the
      sprint total: see the current-document counts below.
    </p>
    <ul className="mt-1 space-y-0.5">
      {run.jobs.map((j) => (
        <li key={j.jobId} className="flex flex-wrap gap-x-2">
          <span className="text-ink-900 font-medium">{j.filename}</span>
          <span className={OUTCOME_CLASS[j.outcome] || ''}>{j.outcome}</span>
          {j.startedAt !== null && (
            <span className="text-ink-500 tabular-nums">
              {clock(j.startedAt)}{j.finishedAt !== null && ` – ${clock(j.finishedAt)}`}
            </span>
          )}
        </li>
      ))}
    </ul>
  </details>
);

/** While documents are processing: elapsed time, progress and a rounded time-left estimate. */
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
            <p className="text-xs text-ink-500">Progress of this activity</p>
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
          <div className="sm:col-span-3"><ActivityDetails run={run} /></div>
        </div>
      ) : null}
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
const AIUsagePanel: React.FC<{ usage: SprintAIUsage; currentTotal: number }> = ({ usage, currentTotal }) => (
  <div className="glass-card px-5 py-4 space-y-2">
    <div className="flex items-center gap-4">
      <div className="w-9 h-9 rounded-lg border border-brand-500/30 bg-brand-500/10 text-brand-800 flex items-center justify-center shrink-0">
        <Coins className="w-4 h-4" />
      </div>
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div>
          <p className="text-xs text-ink-500">AI cost</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">
            {formatUsd(usage.cost_usd)}
            {usage.unpriced_calls > 0 && <span className="text-xs font-normal text-warning" title="Some calls used a model with no configured price: see Usage details."> (incomplete)</span>}
          </p>
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
          <p className="text-xs text-ink-500">AI requests</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{usage.calls}</p>
        </div>
        <div>
          <p className="text-xs text-ink-500">Documents with usage</p>
          <p className="text-lg font-bold text-ink-900 tabular-nums">{usage.documents || '—'}</p>
        </div>
      </div>
    </div>
    <details className="text-xs text-ink-500">
      <summary className="cursor-pointer text-brand-800">Usage details</summary>
      <div className="mt-2 space-y-1.5">
        <p>
          Totals of every recorded AI request in this sprint, for every attempt (retries included) and every file
          version; requests that failed without a response are not recorded.
          {usage.current_documents !== undefined && ` Current documents with AI usage: ${usage.current_documents} of ${currentTotal}.`}
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
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
          <p className="text-info" title={usage.notes.join(' | ')}>
            Includes {usage.imported_calls > 0 && `${usage.imported_calls} request${usage.imported_calls === 1 ? '' : 's'} imported from a provider dashboard`}
            {usage.imported_calls > 0 && usage.estimated_calls > 0 && ' and '}
            {usage.estimated_calls > 0 && `${usage.estimated_calls} estimated`} (totals only, not per document).
            {usage.notes.length > 0 && ` Source: ${usage.notes.join(' | ')}`}
          </p>
        )}
        {usage.unpriced_calls > 0 && (
          <p className="text-warning">
            {usage.unpriced_calls} call{usage.unpriced_calls === 1 ? '' : 's'} used a model with no configured price
            ({usage.unpriced_models.join(', ')}), so the cost is incomplete. Tokens are still counted.
          </p>
        )}
      </div>
    </details>
  </div>
);
