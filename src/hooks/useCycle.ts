import { useMemo, useState } from 'react';
import { getCycle, listCycles } from '../services/assessments';
import type { Cycle, CycleDetail } from '../types/api';
import { useResource } from './useResource';

/**
 * The institution's benchmark assessment cycles and the chosen one in detail (newest by default).
 * A cycle is the backend's frozen assessment snapshot: published release + college profile at creation.
 */
export function useCycle(institutionId: string | undefined) {
  const cycles = useResource<Cycle[]>(() => listCycles(institutionId), `cycles:${institutionId}`, !!institutionId);
  const [chosen, setChosen] = useState<string | null>(null);

  const ordered = useMemo(
    () => [...(cycles.data || [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [cycles.data],
  );
  const cycleId = (chosen && ordered.find((c) => c.id === chosen)?.id) || ordered[0]?.id || '';
  const detail = useResource<CycleDetail>(() => getCycle(cycleId), `cycle:${cycleId}`, !!cycleId);

  return { cycles: ordered, cyclesState: cycles, cycleId, choose: setChosen, detail };
}
