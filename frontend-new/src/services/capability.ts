import { http, saveBlob } from './http';
import type { CapabilityPage, CapabilityRecommendation, Job, Run } from '../types/capability';
import type { ActionState, PlanComparison, PlanEvaluationJob } from '../types/workflow';

/** Evidence-based capability assessment runs (A1 backend). Reads are free; starting a run uses model credits. */
const root = (sprint: string) => `/sprints/${sprint}/capability-runs`;

export const listRuns = (sprint: string, page = 1) => http.get<CapabilityPage<Job>>(root(sprint), { params: { page } });
export const getRun = (sprint: string, run: string) => http.get<Run>(`${root(sprint)}/${run}`);
/** `key` is an Idempotency-Key: retrying with the same key never starts a second run. */
export const startRun = (sprint: string, key: string) =>
  http.post<Job>(root(sprint), { scope_mode: 'default' }, { headers: { 'Idempotency-Key': key } });
export const cancelRun = (sprint: string, run: string) => http.post<Job>(`${root(sprint)}/${run}/cancel`);
/** The frozen source excerpts a run cited, optionally for one condition. */
export const getRunEvidence = (sprint: string, run: string, conditionId?: string) =>
  http.get<{ run_id: string; records: { condition_id: string; state: string; reason: string; citations: { source_id: string; quote: string }[] }[]; sources: { id: string; [k: string]: unknown }[]; note: string }>(
    `${root(sprint)}/${run}/evidence`, { params: conditionId ? { condition_id: conditionId } : {} });

// --- grounded advice (recommendations) for a completed run; starting one uses model credits ---
export const listAdvice = (sprint: string, run: string) =>
  http.get<CapabilityPage<Job>>(`${root(sprint)}/${run}/recommendations`);
export const getAdvice = (sprint: string, run: string, advice: string) =>
  http.get<CapabilityRecommendation>(`${root(sprint)}/${run}/recommendations/${advice}`);
export const startAdvice = (sprint: string, run: string, key: string) =>
  http.post<Job>(`${root(sprint)}/${run}/recommendations`, {}, { headers: { 'Idempotency-Key': key } });
export const cancelAdvice = (sprint: string, run: string, advice: string) =>
  http.post<Job>(`${root(sprint)}/${run}/recommendations/${advice}/cancel`);
/** Track one recommended action: owner, feasibility and status. */
export const updateActionState = (sprint: string, run: string, advice: string, conditionId: string, state: Partial<Omit<ActionState, 'condition_id'>>) =>
  http.patch<ActionState>(`${root(sprint)}/${run}/recommendations/${advice}/actions/${conditionId}`, state);

// --- plan evaluations: compare a written plan against the run (uses model credits) ---
export const listPlanEvaluations = (sprint: string, run: string) =>
  http.get<CapabilityPage<PlanEvaluationJob>>(`${root(sprint)}/${run}/plan-evaluations`);
export const getPlanEvaluation = (sprint: string, run: string, scenario: string) =>
  http.get<PlanComparison>(`${root(sprint)}/${run}/plan-evaluations/${scenario}`);
export const startPlanEvaluation = (sprint: string, run: string, planText: string, key: string) =>
  http.post<PlanEvaluationJob>(`${root(sprint)}/${run}/plan-evaluations`, { plan_text: planText }, { headers: { 'Idempotency-Key': key } });
export const cancelPlanEvaluation = (sprint: string, run: string, scenario: string) =>
  http.post<PlanEvaluationJob>(`${root(sprint)}/${run}/plan-evaluations/${scenario}/cancel`);
export async function downloadPlanEvaluation(sprint: string, run: string, scenario: string, format: 'html' | 'json') {
  const res = await http.get<Blob>(`${root(sprint)}/${run}/plan-evaluations/${scenario}/report`, { params: { file: format }, responseType: 'blob' });
  saveBlob(res.data, `plan-comparison-${scenario.slice(0, 8)}.${format}`);
}

export async function downloadCapabilityReport(sprint: string, run: string, format: 'html' | 'json' | 'pdf',
  audience: 'leadership' | 'evidence', advice?: string) {
  const res = await http.get<Blob>(`${root(sprint)}/${run}/report`, {
    params: { file: format, audience, recommendation_id: advice }, responseType: 'blob',
  });
  saveBlob(res.data, `capability-${run.slice(0, 8)}-${audience}.${format}`);
}
