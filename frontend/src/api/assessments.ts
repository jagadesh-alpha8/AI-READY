import api from './client';

/** Stage 5: benchmark assessments of a college against the current published release. */

export type CycleStatus = 'not_started' | 'in_progress' | 'submitted' | 'reviewed' | 'finalized';
export type Level = 'L3' | 'L2' | 'L1';
export type EvidenceStatus = 'submitted' | 'accepted' | 'rejected' | 'needs_information';
export type ReviewDecision = 'accepted' | 'rejected' | 'needs_information';

export interface Choice { code: string; name: string }

export interface AssessmentReference {
  institution_types: Choice[];
  programme_types: Choice[];
  autonomous_statuses: Choice[];
  approval_bodies: string[];
  current_release: string | null;
  scoring_model: { code: string; name: string; description: string } | null;
  is_staff: boolean;
  can_upload: boolean;
}

export interface CollegeRow { id: string; name: string; city: string; has_profile: boolean }

export interface ProgrammeRow { id?: string; name: string; programme_type: string; programme_type_name?: string; approval_body: string }

export interface CollegeProfile {
  institution: string;
  institution_name: string;
  profile: null | {
    institution_type: string;
    institution_type_name: string;
    autonomous_status: string;
    approval_bodies: string[];
    jurisdiction: string;
    updated_by: string | null;
    updated_at: string;
  };
  programmes: ProgrammeRow[];
}

export interface Assessment {
  computed_level: string;
  level_override: string;
  override_note: string;
  current_level: string;
  compliance_score: string | null;
  maturity_score: string | null;
  evidence_confidence_score: string | null;
  outcome_score: string | null;
  outcome_note: string;
  composite_score: string | null;
  scoring_model: string | null;
  weights: Record<string, string>;
  detail: ScoreDetail;
  assessor_notes: string;
  scored_at: string | null;
  scored_by: string | null;
}

export interface ScoreDetail {
  method?: string;
  reference_date?: string;
  requests?: { key: string; level: string; title: string; mandatory: boolean; minimum_count: number; counted: number; met: boolean; notes: string[] }[];
  level_notes?: string[];
  needs_assessor_confirmation?: boolean;
  compliance?: string;
  maturity?: string;
  evidence_confidence?: string;
  outcome?: string;
  composite?: string;
}

export interface CycleBenchmarkRow {
  benchmark_code: string;
  title: string;
  pillar: string;
  kind: string;
  applicability_result: string;
  applicability_reason: string;
  included: boolean | null;
  selected_by: string;
  decision_note: string;
  target_level: Level;
  requests: number;
  evidence: number;
  accepted: number;
  waiting: number;
  assessment: Assessment | null;
}

export interface Cycle {
  id: string;
  institution: string;
  institution_name: string;
  name: string;
  opens_on: string;
  closes_on: string | null;
  status: CycleStatus;
  status_label: string;
  release_label: string;
  release_hash: string;
  profile_snapshot: Record<string, unknown>;
  created_by: string;
  created_at: string;
  finalized_by: string | null;
  finalized_at: string | null;
}

export interface CycleDetail extends Cycle {
  scores_visible: boolean;
  benchmarks: CycleBenchmarkRow[];
}

export interface EvidenceReviewInfo {
  id: string;
  reviewer: string;
  decision: ReviewDecision;
  decision_label: string;
  relevance_score: string;
  completeness_score: string;
  currency_score: string;
  authenticity_score: string;
  scope_score: string;
  notes: string;
  reviewed_at: string;
}

export interface EvidenceItemInfo {
  id: string;
  rule_key: string;
  evidence_type: string;
  title: string;
  description: string;
  has_file: boolean;
  from_audit: boolean;
  original_filename: string;
  file_sha256: string;
  source_url: string;
  issued_on: string | null;
  valid_until: string | null;
  status: EvidenceStatus;
  status_label: string;
  submitted_by: string;
  created_at: string;
  reviews: EvidenceReviewInfo[];
}

export interface EvidenceRequest {
  key: string;
  level: string;
  evidence_type: string;
  evidence_type_name: string;
  title: string;
  mandatory: boolean;
  minimum_count: number;
  minimum_currency_months: number | null;
  scope_rule: string;
  validation_method: string;
  items: EvidenceItemInfo[];
}

export interface LevelSnapshot {
  definition: string;
  measurement_rule: string;
  observable_requirements: string[];
  minimum_evidence: string[];
  outcome_expectations: string[];
  non_examples: string[];
  requires_manual_review: boolean;
}

export interface CycleBenchmarkDetail extends Omit<CycleBenchmarkRow, 'requests'> {
  cycle_status: CycleStatus;
  release_label: string;
  snapshot_hash: string;
  levels: Partial<Record<Level, LevelSnapshot>>;
  requirements: { code: string; statement: string; source_code: string; page: number | null }[];
  requests: EvidenceRequest[];
  preview: null | { current_level: string; composite: string | null; scores: Record<string, string | null>; detail: ScoreDetail };
}

export interface Scorecard extends Cycle {
  benchmarks: { benchmark_code: string; title: string; pillar: string; kind: string; target_level: Level; snapshot_hash: string; assessment: Assessment | null }[];
  scoring_model: { code: string; name: string; formula_version: string; description: string } | null;
  method: string;
}

export interface ScoreRuleRow {
  benchmark_code: string;
  title: string;
  status: string;
  weights: null | { compliance: string; maturity: string; evidence_confidence: string; outcome: string };
  approved_by: string | null;
  approved_at: string | null;
  note: string;
}

const base = '/assessments';

export const getAssessmentReference = () => api.get<AssessmentReference>(`${base}/reference`);
export const listColleges = () => api.get<CollegeRow[]>(`${base}/institutions`);
export const getCollegeProfile = (id: string) => api.get<CollegeProfile>(`${base}/institutions/${id}/profile`);
export const saveCollegeProfile = (id: string, body: {
  institution_type: string; autonomous_status: string; approval_bodies: string[]; jurisdiction?: string; programmes: ProgrammeRow[];
}) => api.put<CollegeProfile>(`${base}/institutions/${id}/profile`, body);

export const listCycles = (institution?: string) => api.get<Cycle[]>(`${base}/cycles`, { params: institution ? { institution } : {} });
export const createCycle = (body: { institution: string; name: string; opens_on?: string; closes_on?: string }) =>
  api.post<CycleDetail>(`${base}/cycles`, body);
export const getCycle = (id: string) => api.get<CycleDetail>(`${base}/cycles/${id}`);
export const cycleAction = (id: string, action: 'open' | 'submit' | 'return' | 'score' | 'finalize', note = '') =>
  api.post<CycleDetail>(`${base}/cycles/${id}/${action}`, { note });

export const getCycleBenchmark = (id: string, code: string) =>
  api.get<CycleBenchmarkDetail>(`${base}/cycles/${id}/benchmarks/${code}`);
export const decideCycleBenchmark = (id: string, code: string, body: { included?: boolean; target_level?: Level; note?: string }) =>
  api.patch<CycleBenchmarkDetail>(`${base}/cycles/${id}/benchmarks/${code}`, body);

export function uploadEvidence(id: string, code: string, body: {
  rule_key: string; title: string; description?: string; source_url?: string; issued_on?: string; valid_until?: string;
  file?: File | null; sprint_document?: string;
}) {
  const form = new FormData();
  Object.entries(body).forEach(([k, v]) => {
    if (v) form.append(k, v as string | Blob);
  });
  return api.post<EvidenceItemInfo>(`${base}/cycles/${id}/benchmarks/${code}/evidence`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export const evidenceFileUrl = (itemId: string) => `${base}/evidence/${itemId}/file`;
export const downloadEvidence = (itemId: string) => api.get<Blob>(evidenceFileUrl(itemId), { responseType: 'blob' });

export const reviewEvidence = (itemId: string, body: {
  decision: ReviewDecision; relevance_score: number; completeness_score: number; currency_score: number;
  authenticity_score: number; scope_score: number; notes: string;
}) => api.post<EvidenceItemInfo>(`${base}/evidence/${itemId}/review`, body);

export const saveAssessorInput = (id: string, code: string, body: {
  outcome_score?: number | null; outcome_note?: string; level_override?: string; override_note?: string; assessor_notes?: string;
}) => api.post<Assessment>(`${base}/cycles/${id}/benchmarks/${code}/assessment`, body);

export const getScorecard = (id: string) => api.get<Scorecard>(`${base}/cycles/${id}/scorecard`);
export const listScoreRules = () => api.get<{ scoring_model: string | null; rules: ScoreRuleRow[] }>(`${base}/score-rules`);
export const saveScoreRule = (code: string, body: {
  compliance_weight: string; maturity_weight: string; evidence_weight: string; outcome_weight: string; note: string;
}) => api.put<{ scoring_model: string | null; rules: ScoreRuleRow[] }>(`${base}/score-rules/${code}`, body);

/** Stage 6: improvement plan, templates, audit documents as evidence. */

export type PlanStatus = 'planned' | 'active' | 'blocked' | 'complete';
export type GapStatus = 'open' | 'planned' | 'in_progress' | 'validated' | 'closed';

export interface PlanTask {
  id: string;
  title: string;
  owner: string;
  due_date: string | null;
  status: PlanStatus;
  status_label: string;
  evidence_due: string;
  order: number;
}

export interface PlanInitiative {
  id: string;
  title: string;
  description: string;
  expected_evidence: string;
  expected_outcome: string;
  owner: string;
  status: PlanStatus;
  status_label: string;
  target_date: string | null;
  from_template: boolean;
  tasks: PlanTask[];
}

export interface PlanGap {
  id: string;
  benchmark_code: string;
  benchmark_title: string;
  gap_type: string;
  type_label: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  severity_label: string;
  description: string;
  root_cause: string;
  status: GapStatus;
  status_label: string;
  closing_evidence: string | null;
  closing_evidence_title: string | null;
  validated_by: string | null;
  validated_at: string | null;
  validation_note: string;
  initiatives: PlanInitiative[];
}

export interface ImprovementPlan {
  cycle: string;
  has_plan: boolean;
  gaps: PlanGap[];
  summary: { gaps: number; open: number; critical_open: number; tasks: number; tasks_done: number };
}

export interface TransformationTemplateInfo {
  id: string;
  benchmark_code: string;
  gap_type: string;
  title: string;
  intervention: string;
  expected_evidence: string;
  expected_outcome: string;
  tasks: string[];
  updated_at: string;
}

export interface SprintDocumentOption {
  id: string;
  title: string;
  filename: string;
  document_type: string;
  sprint: string;
  uploaded_at: string;
}

export const getPlan = (cycleId: string) => api.get<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
export const generatePlan = (cycleId: string) => api.post<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
export const updateGap = (id: string, body: { status?: GapStatus; root_cause?: string }) =>
  api.patch<PlanGap>(`${base}/gaps/${id}`, body);
export const validateGap = (id: string, body: { evidence_item: string; note: string }) =>
  api.post<PlanGap>(`${base}/gaps/${id}/validate`, body);
export const updateInitiative = (id: string, body: Partial<Pick<PlanInitiative, 'title' | 'owner' | 'status' | 'target_date'>>) =>
  api.patch<PlanInitiative>(`${base}/initiatives/${id}`, body);
export const addTask = (initiativeId: string, body: { title: string; owner?: string; due_date?: string }) =>
  api.post<PlanInitiative>(`${base}/initiatives/${initiativeId}/tasks`, body);
export const updateTask = (id: string, body: Partial<Pick<PlanTask, 'title' | 'owner' | 'status' | 'due_date'>>) =>
  api.patch<PlanTask>(`${base}/tasks/${id}`, body);
export const listTemplates = (benchmark?: string) =>
  api.get<TransformationTemplateInfo[]>(`${base}/templates`, { params: benchmark ? { benchmark } : {} });
export const createTemplate = (body: Omit<TransformationTemplateInfo, 'id' | 'updated_at'>) =>
  api.post<TransformationTemplateInfo>(`${base}/templates`, body);
export const updateTemplate = (id: string, body: Partial<TransformationTemplateInfo>) =>
  api.patch<TransformationTemplateInfo>(`${base}/templates/${id}`, body);
export const deleteTemplate = (id: string) => api.delete(`${base}/templates/${id}`);
export const listSprintDocuments = (cycleId: string) =>
  api.get<SprintDocumentOption[]>(`${base}/cycles/${cycleId}/sprint-documents`);
