import React, { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listExtractionJobs, cancelSprintExtraction, deleteExtractionJob } from '../../api/extraction';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { humanizeExtractionError } from '../../utils/errors';
import { ACTIVE_EXTRACTION_STATUSES, type ExtractionJob, type Fact, type Gap } from '../../types';
import { Activity, CheckCircle2, AlertTriangle, ArrowRight, Cpu, Layers, XCircle, Loader2, Trash2 } from 'lucide-react';

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
  const facts = factsData || [];
  const gaps = gapsData || [];
  const conflictCount = gaps.filter((g) => g.gap_type === 'conflict').length;

  const hasActiveJob = jobs.some((j) => ACTIVE_EXTRACTION_STATUSES.includes(j.status));

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
  });
  refetchAllRef.current = () => {
    refetch();
    refetchFacts();
    refetchGaps();
  };

  useEffect(() => {
    if (!hasActiveJob) return;
    const timer = setInterval(() => refetchAllRef.current(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [hasActiveJob]);

  const completedCount = jobs.filter((j) => j.status === 'completed').length;

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Activity className="w-5 h-5 text-brand-800" /> Screen 3: AI Processing Monitor
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Transparent tracking of document classification, table parsing, entity extraction, and gap identification.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
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
                const Icon =
                  job.status === 'completed' ? CheckCircle2 : job.status === 'failed' ? XCircle : Loader2;
                const iconClass =
                  job.status === 'completed'
                    ? 'text-success bg-success-bg border-success-line'
                    : job.status === 'failed'
                    ? 'text-danger bg-danger-bg border-danger-line'
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
                          {job.current_step_label || 'Queued'}
                          {stepIndex >= 0 && ` (step ${stepIndex + 1} of ${STEP_LABELS.length})`}
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
                      <span className="text-sm font-mono text-ink-500 tabular-nums">{job.progress_percentage}%</span>
                      <span className={badgeClass}>{job.status}</span>
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
