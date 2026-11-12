/** The journey strip of the agreed flow (set up, initial evidence, assessment, report) and where a sprint stands on it. */

export const JOURNEY = ['Set up', 'Initial evidence', 'Assessment', 'Report & recommendations'] as const;

/** Sprint pipeline status -> journey step index. */
const STATUS_STEP: Record<string, number> = {
  draft: 0,
  collecting: 1,
  processing: 1,
  reviewing: 1,
  scoring: 2,
  baseline_pending: 2,
  baseline_approved: 3,
  report_ready: 3,
  completed: 3,
  archived: 3,
};

export function journeyStep(status: string | null | undefined): number {
  return status && status in STATUS_STEP ? STATUS_STEP[status] : 0;
}
