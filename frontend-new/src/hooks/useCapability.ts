import { useMemo } from 'react';
import { getAdvice, getRun, listAdvice, listRuns } from '../services/capability';
import type { CapabilityPage, CapabilityRecommendation, Job, Run } from '../types/capability';
import { isActive, shownRun } from '../utils/capability';
import { useAccess } from './useAccess';
import { usePolling, useResource } from './useResource';

/**
 * The sprint's capability assessment: run history, the result shown in detail (the published run; for staff, the
 * newest completed run while nothing is published), the newest run's progress, and the latest completed
 * recommendation for the shown run. Polls while a job runs.
 */
export function useCapability(sprintId: string) {
  const { staff } = useAccess();
  const runs = useResource<CapabilityPage<Job>>(() => listRuns(sprintId), `cap-runs:${sprintId}`);
  const list = useMemo(() => runs.data?.results || [], [runs.data]);
  const newest = list[0] || null;
  const shown = useMemo(() => shownRun(list, runs.data?.published, staff), [list, runs.data?.published, staff]);
  const runId = shown.id;
  // Questions, responses and second-layer jobs always belong to the provisional run; a final run names it.
  const provisionalId = shown.provisionalId;

  const run = useResource<Run>(() => getRun(sprintId, runId), `cap-run:${runId}`, !!runId);
  const adviceList = useResource<CapabilityPage<Job>>(() => listAdvice(sprintId, runId), `cap-advice:${runId}`, !!runId);
  const adviceId = adviceList.data?.results.find((a) => a.status === 'completed')?.id || '';
  const advice = useResource<CapabilityRecommendation>(() => getAdvice(sprintId, runId, adviceId), `cap-adv:${adviceId}`, !!adviceId);

  usePolling(() => void runs.refetch(), isActive(newest), 4000);

  const assessment = run.data?.assessment || null;
  const plan = advice.data?.plan || run.data?.deterministic_plan || null;
  return {
    runs,
    enabled: !!runs.data?.enabled,
    newest,
    running: isActive(newest),
    run,
    provisionalId,
    stage: shown.stage,
    /** Which run is shown and why (utils/capability.shownRun); `published` is the run list's publication. */
    shown,
    published: runs.data?.published || null,
    assessment,
    advice: advice.data,
    plan,
    foundation: plan?.foundation_plan || null,
    loading: runs.loading || (!!runId && run.loading),
    error: runs.error || run.error,
  };
}
