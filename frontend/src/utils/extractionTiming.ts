import { ACTIVE_EXTRACTION_STATUSES, type ExtractionJob } from '../types';

/**
 * Timing for the latest extraction "run" of a sprint: elapsed time, a rounded
 * estimate of time left, and a summary once it finishes.
 *
 * A sprint can be extracted several times (first run, later re-processing), so
 * the run is found from the jobs' own timestamps: jobs whose work periods
 * overlap or follow each other with less than RUN_GAP_MS between them belong to
 * one run; the latest such group is "the run". Queued jobs that haven't
 * started yet belong to the current run too.
 */
const RUN_GAP_MS = 5 * 60 * 1000;
/** No estimate until this many documents of the run have finished. */
const MIN_FINISHED_FOR_ESTIMATE = 5;

export interface RunTiming {
  active: boolean;
  /** Jobs exist but none has started yet (waiting for a worker). */
  waitingToStart: boolean;
  startedAt: number | null;
  finishedAt: number | null;
  elapsedMs: number;
  total: number;
  completed: number;
  failed: number;
  stopped: number;
  remaining: number;
  /** Rounded [low, high] estimate of time left, or null while too early. */
  etaRangeMs: [number, number] | null;
  /** Wall-clock time per finished document (includes parallel workers). */
  avgPerDocMs: number | null;
}

const time = (iso: string | null) => (iso ? new Date(iso).getTime() : null);

export function latestRunTiming(jobs: ExtractionJob[], now: number): RunTiming | null {
  if (jobs.length === 0) return null;
  const isActive = (j: ExtractionJob) => ACTIVE_EXTRACTION_STATUSES.includes(j.status);

  // Work period of every job that has started.
  const periods = jobs
    .filter((j) => j.started_at)
    .map((j) => {
      const start = time(j.started_at)!;
      const end = time(j.completed_at) ?? (isActive(j) ? now : time(j.updated_at) ?? start);
      return { job: j, start, end: Math.max(end, start) };
    })
    .sort((a, b) => a.start - b.start);

  // Group into runs; keep the latest.
  let run: typeof periods = [];
  let runEnd = -Infinity;
  for (const p of periods) {
    if (run.length === 0 || p.start - runEnd > RUN_GAP_MS) {
      run = [p];
    } else {
      run.push(p);
    }
    runEnd = Math.max(runEnd, p.end);
  }

  const queued = jobs.filter((j) => j.status === 'pending' && !j.started_at);
  const anyActive = jobs.some(isActive);
  // The latest run is current only if it is still going, or if work is queued
  // right after it; an old finished run plus fresh queued jobs = a new run.
  const runIsCurrent = run.length > 0 && (!anyActive || run.some((p) => isActive(p.job)) || now - runEnd <= RUN_GAP_MS);
  const runJobs = [...(runIsCurrent ? run.map((p) => p.job) : []), ...(anyActive ? queued : [])];
  if (runJobs.length === 0) return null;

  const startedAt = runIsCurrent ? run[0].start : null;
  const active = runJobs.some(isActive);
  const completed = runJobs.filter((j) => j.status === 'completed').length;
  const failed = runJobs.filter((j) => j.status === 'failed').length;
  const stopped = runJobs.filter((j) => j.status === 'cancelled').length;
  const remaining = runJobs.filter(isActive).length;
  const finished = completed + failed + stopped;
  const finishedAt = active || !runIsCurrent ? null : runEnd;
  const elapsedMs = startedAt === null ? 0 : (finishedAt ?? now) - startedAt;

  let etaRangeMs: [number, number] | null = null;
  if (active && startedAt !== null && finished >= MIN_FINISHED_FOR_ESTIMATE && elapsedMs > 0) {
    // Throughput so far (wall clock, so parallel workers are already counted).
    const msPerDoc = elapsedMs / finished;
    const eta = msPerDoc * remaining;
    // Documents vary a lot in size: give a rounded range, not false precision.
    etaRangeMs = [eta * 0.8, eta * 1.3];
  }

  return {
    active,
    waitingToStart: active && startedAt === null,
    startedAt,
    finishedAt,
    elapsedMs: Math.max(0, elapsedMs),
    total: runJobs.length,
    completed,
    failed,
    stopped,
    remaining,
    etaRangeMs,
    avgPerDocMs: finished > 0 && elapsedMs > 0 ? elapsedMs / finished : null,
  };
}

/** "1h 12m", "4m 05s", "38s". */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}

/** Rounded estimate: "about 20–30 min", "about 2–3 h", "under a minute". */
export function formatEstimate([low, high]: [number, number]): string {
  const minutes = (ms: number) => ms / 60000;
  if (minutes(high) < 1.5) return 'under a minute';
  if (minutes(high) < 90) {
    const lo = Math.max(1, Math.floor(minutes(low) / 5) * 5 || Math.floor(minutes(low)));
    const hi = Math.max(lo + 1, Math.ceil(minutes(high) / 5) * 5);
    return `about ${lo}–${hi} min`;
  }
  const lo = Math.max(1, Math.floor(minutes(low) / 60));
  const hi = Math.max(lo + 1, Math.ceil(minutes(high) / 60));
  return `about ${lo}–${hi} h`;
}
