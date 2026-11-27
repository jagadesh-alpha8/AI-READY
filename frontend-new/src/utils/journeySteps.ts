import type { Sprint } from '../types/api';
import type { PageKey } from './access';
import type { ShownRun } from './capability';

/**
 * The progress bar of the merged design (27 Nov 2026), on every page: where the assessment is, not a list of menu
 * sections (workspace/journey.ts loads the state).
 */
export const JOURNEY: { label: string; page: PageKey }[] = [
  { label: 'Set up', page: 'profile' },
  { label: 'Documents', page: 'uploads' },
  { label: 'Stage 1 result', page: 'overview' },
  { label: 'Follow-up questions', page: 'questionnaire' },
  { label: 'Final result', page: 'areas' },
];

export interface Journey {
  /** Index of the current step; JOURNEY.length once the final result is out (every step done). */
  current: number;
  /** "Step 4 of 5": the current step, counted from one (5 once everything is done). */
  stepNumber: number;
  stage1: boolean; final: boolean; closed: boolean;
  /** Open follow-up questions at Stage 1 (null until known). */
  open: number | null;
  loading: boolean;
  /** The result the screens show (utils/capability.shownRun), and whether results publish themselves. */
  shown: ShownRun;
  autoPublish: boolean;
}

/** run.draft: InGage staff are looking at a result the college can't see yet, so its step is current, not done. */
export function journeyOf(sprint: Pick<Sprint, 'id'> | null,
  run: { shown: boolean; final: boolean; making: boolean; draft?: boolean }, closed: boolean): number {
  if (run.draft) return run.final ? 4 : 2;
  if (run.final) return JOURNEY.length;
  if (run.shown) return closed ? 4 : 3;
  if (run.making) return 2;
  return sprint ? 1 : 0;
}

