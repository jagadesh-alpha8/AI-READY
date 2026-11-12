import { useMemo } from 'react';
import { getAdvice, getRun, listAdvice, listRuns } from '../services/capability';
import type { CapabilityPage, CapabilityRecommendation, Job, Run } from '../types/capability';
import { isActive } from '../utils/capability';
import { usePolling, useResource } from './useResource';

/**
 * The sprint's capability assessment: run history, the latest completed run in detail (the one a score comes
 * from), the newest run's progress, and the latest completed recommendation for that run. Polls while a job runs.
 */
export function useCapability(sprintId: string) {
  const runs = useResource<CapabilityPage<Job>>(() => listRuns(sprintId), `cap-runs:${sprintId}`);
  const list = useMemo(() => runs.data?.results || [], [runs.data]);
  const newest = list[0] || null;
  const completed = list.find((r) => r.status === 'completed') || null;
  const runId = completed?.id || '';

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
    assessment,
    advice: advice.data,
    plan,
    foundation: plan?.foundation_plan || null,
    loading: runs.loading || (!!runId && run.loading),
    error: runs.error || run.error,
  };
}
