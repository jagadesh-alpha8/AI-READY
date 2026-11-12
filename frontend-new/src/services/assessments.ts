import { http, saveBlob } from './http';
import type {
  CollegeProfile, Cycle, CycleDetail, ImprovementPlan, PlanGap, PlanInitiative, PlanStatus, PlanTask,
} from '../types/api';
import type {
  AssessmentReference, CycleBenchmarkDetail, CycleEvidenceItem, CycleScorecard, ScoreRules, SprintDocumentOption,
  TransformationTemplate,
} from '../types/workflow';

/** Benchmark assessments of a college against the published release (backend apps/assessments). */
const base = '/assessments';

export const getAssessmentReference = () => http.get<AssessmentReference>(`${base}/reference`);
export const listAssessmentColleges = () => http.get<{ id: string; name: string; city: string; has_profile: boolean }[]>(`${base}/institutions`);
export const getCollegeProfile = (institutionId: string) =>
  http.get<CollegeProfile>(`${base}/institutions/${institutionId}/profile`);
/** InGage staff save the benchmark profile that decides which benchmarks apply. */
export const saveCollegeProfile = (institutionId: string, body: {
  institution_type: string; autonomous_status: string; approval_bodies: string[]; jurisdiction?: string;
  programmes: { name: string; programme_type: string; approval_body: string }[];
}) => http.put<CollegeProfile>(`${base}/institutions/${institutionId}/profile`, body);

// --- cycles ---
export const listCycles = (institution?: string) =>
  http.get<Cycle[]>(`${base}/cycles`, { params: institution ? { institution } : {} });
export const getCycle = (id: string) => http.get<CycleDetail>(`${base}/cycles/${id}`);
/** A new cycle freezes the current published release and the college profile (InGage staff). */
export const createCycle = (body: { institution: string; name: string; opens_on?: string; closes_on?: string }) =>
  http.post<CycleDetail>(`${base}/cycles`, body);
/** Move the cycle along its lifecycle: open → submit → (return) → score → finalize. */
export const cycleAction = (id: string, action: 'open' | 'submit' | 'return' | 'score' | 'finalize', note = '') =>
  http.post<CycleDetail>(`${base}/cycles/${id}/${action}`, { note });
export const getScorecard = (id: string) => http.get<CycleScorecard>(`${base}/cycles/${id}/scorecard`);

// --- one benchmark inside a cycle ---
export const getCycleBenchmark = (id: string, code: string) =>
  http.get<CycleBenchmarkDetail>(`${base}/cycles/${id}/benchmarks/${code}`);
/** Include or exclude a benchmark, or change its target level (with a note). */
export const decideCycleBenchmark = (id: string, code: string, body: { included?: boolean; target_level?: string; note?: string }) =>
  http.patch<CycleBenchmarkDetail>(`${base}/cycles/${id}/benchmarks/${code}`, body);
/** Submit evidence for an evidence request: a file, a link, or an audit document reused from a sprint. */
export function uploadCycleEvidence(id: string, code: string, body: {
  rule_key: string; title: string; description?: string; source_url?: string; issued_on?: string; valid_until?: string;
  file?: File | null; sprint_document?: string;
}) {
  const form = new FormData();
  Object.entries(body).forEach(([k, v]) => { if (v) form.append(k, v as string | Blob); });
  return http.post<CycleEvidenceItem>(`${base}/cycles/${id}/benchmarks/${code}/evidence`, form);
}
export async function downloadCycleEvidence(itemId: string, filename: string) {
  const res = await http.get<Blob>(`${base}/evidence/${itemId}/file`, { responseType: 'blob' });
  saveBlob(res.data, filename || `evidence-${itemId.slice(0, 8)}`);
}
/** InGage reviewer decision with the five quality scores (1–5). */
export const reviewCycleEvidence = (itemId: string, body: {
  decision: 'accepted' | 'rejected' | 'needs_information'; relevance_score: number; completeness_score: number;
  currency_score: number; authenticity_score: number; scope_score: number; notes: string;
}) => http.post<CycleEvidenceItem>(`${base}/evidence/${itemId}/review`, body);
export const saveAssessorInput = (id: string, code: string, body: {
  outcome_score?: number | null; outcome_note?: string; level_override?: string; override_note?: string; assessor_notes?: string;
}) => http.post(`${base}/cycles/${id}/benchmarks/${code}/assessment`, body);
/** Audit documents of the college's sprints that can be reused as evidence. */
export const listCycleSprintDocuments = (id: string) => http.get<SprintDocumentOption[]>(`${base}/cycles/${id}/sprint-documents`);

// --- improvement plan ---
export const getPlan = (cycleId: string) => http.get<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
/** Staff, finalized cycles only: gaps -> initiatives -> tasks. */
export const generatePlan = (cycleId: string) => http.post<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
export const updatePlanGap = (id: string, body: { status?: string; root_cause?: string }) =>
  http.patch<PlanGap>(`${base}/gaps/${id}`, body);
/** Close a plan gap with accepted evidence of the same college and benchmark. */
export const validatePlanGap = (id: string, body: { evidence_item: string; note: string }) =>
  http.post<PlanGap>(`${base}/gaps/${id}/validate`, body);
export const updateInitiative = (id: string, body: Partial<Pick<PlanInitiative, 'title' | 'owner' | 'status' | 'target_date'>>) =>
  http.patch<PlanInitiative>(`${base}/initiatives/${id}`, body);
export const addTask = (initiativeId: string, body: { title: string; owner?: string; due_date?: string }) =>
  http.post<PlanInitiative>(`${base}/initiatives/${initiativeId}/tasks`, body);
export const updateTask = (id: string, body: { title?: string; owner?: string; status?: PlanStatus; due_date?: string | null }) =>
  http.patch<PlanTask>(`${base}/tasks/${id}`, body);

// --- staff configuration: plan templates and score rules ---
export const listTemplates = (benchmark?: string) =>
  http.get<TransformationTemplate[]>(`${base}/templates`, { params: benchmark ? { benchmark } : {} });
export const createTemplate = (body: Omit<TransformationTemplate, 'id' | 'updated_at'>) =>
  http.post<TransformationTemplate>(`${base}/templates`, body);
export const updateTemplate = (id: string, body: Partial<TransformationTemplate>) =>
  http.patch<TransformationTemplate>(`${base}/templates/${id}`, body);
export const deleteTemplate = (id: string) => http.delete(`${base}/templates/${id}`);
export const listScoreRules = () => http.get<ScoreRules>(`${base}/score-rules`);
export const saveScoreRule = (code: string, body: { compliance_weight: string; maturity_weight: string; evidence_weight: string; outcome_weight: string; note: string }) =>
  http.put<ScoreRules>(`${base}/score-rules/${code}`, body);
