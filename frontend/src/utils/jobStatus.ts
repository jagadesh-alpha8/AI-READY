/**
 * What the AI Processing Monitor says about one extraction job (`npm test` runs these on Node directly). The
 * backend decides the phase (apps/extraction/services/job_phase.py); this only words it. Pipeline progress and
 * document completeness stay apart: a job that reached its last stage but skipped pages or chunks is Partial.
 */
import type { ExtractionJob } from '../types/extraction.ts';

const ACTIVE = ['pending', 'running', 'retrying'];

/** The line under the file name while a job is queued or running, e.g. "Reading pages 12 of 40 (3 by OCR)". */
export function jobActivity(job: ExtractionJob): string {
  if (job.phase_label && ACTIVE.includes(job.status)) return job.phase_label;
  return job.current_step_label || 'Queued';
}

/** The status badge's text: the precise phase while active, otherwise its outcome. */
export function jobBadge(job: ExtractionJob | undefined): string {
  if (!job) return 'not started';
  if (job.status === 'completed') return job.completeness === 'partial' ? 'partial' : 'completed';
  if (job.status === 'cancelled') return 'stopped';
  if (job.status === 'failed') return 'failed';
  const phase = job.phase;
  if (!phase) return job.status;
  return ({
    queued: 'queued', reading_pages: 'reading pages', classifying: 'classifying', extracting_facts: 'extracting facts',
    finishing: 'finishing', continuing: 'continuing', retrying: 'retrying', waiting_for_router: 'waiting for router',
  } as Record<string, string>)[phase] || job.status;
}

/** "next attempt at 10:42" for a scheduled retry; '' otherwise. */
export function nextRetry(job: ExtractionJob, now = Date.now()): string {
  if (job.status !== 'retrying' || !job.next_retry_at) return '';
  const at = new Date(job.next_retry_at).getTime();
  if (Number.isNaN(at)) return '';
  if (at <= now) return 'next attempt starting';
  return `next attempt at ${new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

/** Who an attempt ran on: its router, or "single provider" -- single-provider mode has no router to show. */
export function attemptSource(job: ExtractionJob, router: string): string {
  if (router) return router;
  return job.processing_mode === 'multi_router' ? 'router not assigned' : 'single provider';
}

const OUTCOME_LABELS: Record<string, string> = {
  out_of_credit: 'out of credit', continued: 'continued (large document)', recovered: 'recovered after an interruption',
};

export function attemptOutcome(outcome: string): string {
  return OUTCOME_LABELS[outcome] || outcome.replace(/_/g, ' ');
}

/** Why a finished job is Partial, from its own counts: chunks not read and pages that could not be read. */
export function partialSummary(job: ExtractionJob, factCount: number): string {
  const parts: string[] = [];
  if (job.chunks_total && job.chunks_completed < job.chunks_total) {
    parts.push(`${job.chunks_completed} of ${job.chunks_total} text chunk${job.chunks_total === 1 ? '' : 's'} read`);
  }
  if (job.unreadable_pages) {
    parts.push(`${job.unreadable_pages} page${job.unreadable_pages === 1 ? '' : 's'} could not be read`);
  }
  if (!parts.length && job.chunks_total) parts.push(`all ${job.chunks_total} text chunks read`);
  parts.push(`${factCount} fact${factCount === 1 ? '' : 's'} extracted`);
  return `Partially processed: ${parts.join(' · ')}. Some content was not read.`;
}
