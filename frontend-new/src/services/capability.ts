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

// --- second assessment layer (A2, PR #45): the questionnaire's second line and additional evidence ---------------
// Documents are uploaded first through the document API and referenced by id (they must belong to the sprint).
export interface Layer2Question {
  id: string; rank: number; kind: 'depth' | 'missing'; text: string; indicator_code: string;
  /** For a depth question: its own requirement first, then requirements that need the same fact. */
  condition_ids: string[];
  /** 'linked' questions are answered through their lead (linked_to) and never asked on their own. */
  status: string;
  /** Score points this question can earn (for a lead, its whole linked group); questions come highest first. */
  points_at_stake?: number;
  linked_to?: string | null;
}
export interface Layer2Progress {
  /** Questions the college is asked; linked questions are counted separately. */
  questions: number; open: number; answered: number; checks_waiting: number; follow_ups_open: number;
  linked?: number;
  /** Set once the final result has been published from this (provisional) run. */
  final_run_id?: string | null;
  /** True once the follow-up stage is closed (the final result is published): answers and evidence are refused. */
  closed?: boolean;
}
export interface Layer2Next { type: 'question' | 'follow_up'; text: string; question: Layer2Question; response_id: string | null }
export interface Layer2Response {
  id: string; question_id: string; parent_id: string | null; kind: 'answer' | 'upload' | 'dont_know';
  answer: string; document_ids: string[]; status: 'pending' | 'checked'; supported: boolean | null;
  follow_up: string | null; dimensions: { dimension_id: string; support: string; note: string }[];
  passages_found: number; created_at: string;
  /** 'linked' when recorded through the lead question of a linked group. */
  submitted_via?: string;
  /** already_counted: attached documents the first assessment had already read for this key indicator. */
  search?: { already_counted?: { document_id: string; name: string }[]; [k: string]: unknown };
}
export interface AdditionalEvidenceItem {
  id: string; document_ids: string[]; note: string; picked: string[]; routed_indicators: string[]; unknown_picks: string[];
  over_cap: string[]; status: 'pending' | 'checked'; passages_found: number; created_at: string;
}
type Reply = { answer?: string; document_ids?: string[]; skip?: boolean };

/** The text shown before the follow-up questions; served by the back end so every screen uses one wording. */
export interface QuestionnaireNotice { version: string; title: string; intro: string; rules: string[]; closed: boolean; closed_text?: string }
export interface Layer2Questions { next: Layer2Next | null; progress: Layer2Progress; notice?: QuestionnaireNotice }
export const getNextQuestion = (sprint: string, run: string) =>
  http.get<Layer2Questions>(`${root(sprint)}/${run}/questions`);
export const answerQuestion = (sprint: string, run: string, question: string, body: Reply) =>
  http.post<Layer2Response>(`${root(sprint)}/${run}/questions/${question}/responses`, body);
export const getResponse = (sprint: string, run: string, response: string) =>
  http.get<Layer2Response>(`${root(sprint)}/${run}/responses/${response}`);
/** The one answer to a follow-up; never followed up again. */
export const answerFollowUp = (sprint: string, run: string, response: string, body: Reply) =>
  http.post<Layer2Response>(`${root(sprint)}/${run}/responses/${response}/follow-up`, body);
export const listAdditionalEvidence = (sprint: string, run: string) =>
  http.get<{ results: AdditionalEvidenceItem[] }>(`${root(sprint)}/${run}/additional-evidence`);
/** picked: readiness areas, key indicators or requirements the documents are for (at least one). */
export const addAdditionalEvidence = (sprint: string, run: string, body: { document_ids: string[]; note: string; picked: string[] }) =>
  http.post<AdditionalEvidenceItem>(`${root(sprint)}/${run}/additional-evidence`, body);

// --- second-layer background jobs (PR #52/#54): always on the provisional run ------------------------------------
export type SecondLayerOperation = 'questions' | 'checks' | 'depth' | 'rejudge' | 'explain';
export type SecondLayerJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export interface SecondLayerJob {
  id: string; run_id: string; operation: SecondLayerOperation; options: Record<string, boolean>;
  status: SecondLayerJobStatus; error_code: string | null; detail: string | null;
  result: Record<string, unknown> | null; final_run_id: string | null;
  requests_reserved: number; usd_reserved: string;
  created_at: string; started_at: string | null; finished_at: string | null;
  reused?: boolean; note?: string;
}
export interface SecondLayerBudget { max_http_calls: number; max_cost_usd: string; requests_reserved: number; usd_reserved: string }
export interface SecondLayerJobList { enabled: boolean; budget: SecondLayerBudget | null; results: SecondLayerJob[] }

const jobsRoot = (sprint: string, run: string) => `${root(sprint)}/${run}/second-layer/jobs`;
export const listSecondLayerJobs = (sprint: string, run: string) => http.get<SecondLayerJobList>(jobsRoot(sprint, run));
export const getSecondLayerJob = (sprint: string, run: string, job: string) =>
  http.get<SecondLayerJob>(`${jobsRoot(sprint, run)}/${job}`);
/** 202 new job, 200 same key repeated, 409 another job active, 400 not startable yet, 503 jobs switched off. */
export const startSecondLayerJob = (sprint: string, run: string, operation: SecondLayerOperation, key: string,
  options: Record<string, boolean> = {}) =>
  http.post<SecondLayerJob>(jobsRoot(sprint, run), { operation, options }, { headers: { 'Idempotency-Key': key } });
export const cancelSecondLayerJob = (sprint: string, run: string, job: string) =>
  http.post<SecondLayerJob>(`${jobsRoot(sprint, run)}/${job}/cancel`);

/** The report's assessment_stage (provisional or final, with the note the HTML and PDF reports print). */
export interface AssessmentStage {
  stage: 'provisional' | 'final'; score?: number | null; note: string;
  final_run_id?: string | null; provisional_run_id?: string; provisional_score?: number | null;
  /** "Stage 1 result: Document Review" or "Final AI-READY Score"; the tier is shown only when tier_shown. */
  label?: string; tier_shown?: boolean; closed?: boolean; unchanged?: boolean;
}
export async function getAssessmentStage(sprint: string, run: string): Promise<AssessmentStage | null> {
  const res = await http.get<Blob>(`${root(sprint)}/${run}/report`, { params: { file: 'json' }, responseType: 'blob' });
  const body = JSON.parse(await res.data.text()) as { assessment_stage?: AssessmentStage };
  return body.assessment_stage || null;
}
