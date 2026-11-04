/** The six-step journey strip (Set up -> Improve) and where a sprint stands on it. */

export const JOURNEY = ['Set up', 'Collect', 'Verify', 'Assess', 'Transform', 'Improve'] as const;

/** Sprint pipeline status -> journey step index. */
const STATUS_STEP: Record<string, number> = {
  draft: 0,
  collecting: 1,
  processing: 1,
  reviewing: 2,
  scoring: 3,
  baseline_pending: 3,
  baseline_approved: 4,
  report_ready: 4,
  completed: 5,
  archived: 5,
};

export function journeyStep(status: string | null | undefined): number {
  return status && status in STATUS_STEP ? STATUS_STEP[status] : 0;
}
