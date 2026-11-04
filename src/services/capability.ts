import { http, saveBlob } from './http';
import type { CapabilityPage, CapabilityRecommendation, Job, Run } from '../types/capability';

/** Evidence-based capability assessment runs (A1 backend). Reads are free; starting a run uses model credits. */
const root = (sprint: string) => `/sprints/${sprint}/capability-runs`;

export const listRuns = (sprint: string, page = 1) => http.get<CapabilityPage<Job>>(root(sprint), { params: { page } });
export const getRun = (sprint: string, run: string) => http.get<Run>(`${root(sprint)}/${run}`);
/** `key` is an Idempotency-Key: retrying with the same key never starts a second run. */
export const startRun = (sprint: string, key: string) =>
  http.post<Job>(root(sprint), { scope_mode: 'default' }, { headers: { 'Idempotency-Key': key } });
export const cancelRun = (sprint: string, run: string) => http.post<Job>(`${root(sprint)}/${run}/cancel`);

export const listAdvice = (sprint: string, run: string) =>
  http.get<CapabilityPage<Job>>(`${root(sprint)}/${run}/recommendations`);
export const getAdvice = (sprint: string, run: string, advice: string) =>
  http.get<CapabilityRecommendation>(`${root(sprint)}/${run}/recommendations/${advice}`);

export async function downloadCapabilityReport(sprint: string, run: string, format: 'html' | 'json' | 'pdf',
  audience: 'leadership' | 'evidence', advice?: string) {
  const res = await http.get<Blob>(`${root(sprint)}/${run}/report`, {
    params: { file: format, audience, recommendation_id: advice }, responseType: 'blob',
  });
  saveBlob(res.data, `capability-${run.slice(0, 8)}-${audience}.${format}`);
}
