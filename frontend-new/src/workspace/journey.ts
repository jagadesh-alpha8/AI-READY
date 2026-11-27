import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getNextQuestion, listRuns } from '../services/capability';
import type { Sprint } from '../types/api';
import { JOURNEY, journeyOf, type Journey } from '../utils/journeySteps';
import { isActive, shownRun } from '../utils/capability';

export { JOURNEY };

/** Where the assessment is, from what the shell can load cheaply: the run list (which result is shown, whether one
 * is being made) and, at Stage 1, the follow-up questions' progress (whether the stage is closed). */
export function useJourney(sprint: Sprint | null): Journey {
  const { staff } = useAccess();
  const runs = useResource(() => listRuns(sprint!.id), `journey-runs:${sprint?.id}`, !!sprint);
  const list = runs.data?.results || [];
  const shown = shownRun(list, runs.data?.published, staff);
  const final = shown.stage === 'final';
  const stage1 = !!shown.id && !final;
  const questions = useResource(() => getNextQuestion(sprint!.id, shown.provisionalId), `journey-q:${shown.provisionalId}`,
    !!sprint && stage1 && !!shown.provisionalId);
  const progress = questions.data?.progress;
  const closed = !!progress?.closed || !!progress?.final_run_id;
  const current = journeyOf(sprint, { shown: !!shown.id, final, making: isActive(list[0] || null) || shown.preparing,
    draft: shown.preview }, closed);
  return {
    current, stepNumber: Math.min(current + 1, JOURNEY.length), stage1, final, closed,
    open: progress ? progress.open : null, loading: runs.loading, shown, autoPublish: !!runs.data?.auto_publish,
  };
}
