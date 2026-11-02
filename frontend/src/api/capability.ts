import api from './client';

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';
export interface AssessmentScope {
  institution?: { assessed_name?: string; identity_status?: string };
  mode: 'default' | 'custom';
  version: string;
  questions: { code: string; message: string }[];
  source_declarations: { kind: string; value: string; source_id: string }[];
  limitations: string;
}
export interface Job {
  scope?: AssessmentScope;
  refines_run_id?: string | null;
  id: string;
  status: JobStatus;
  created_at: string;
  heartbeat_at: string;
  stalled: boolean;
  requests_reserved: number;
  reserved_cost_usd: string;
  completed_indicators?: number;
  rubric_version?: string;
  current_rubric_version?: string;
  assessment_protocol_current?: boolean;
  current_assessment_protocol?: { engine_version: string; prompt_version: string; retrieval_version: string };
  reference_period?: string;
}
export interface Page<T> {
  results: T[];
  next: string | null;
  previous: string | null;
  count: number;
  enabled: boolean;
}
export interface Citation {
  source_id: string;
  quote: string;
}
export type ConditionState = 'met' | 'not_met' | 'unknown' | 'conflicting';
export interface Decision {
  condition_id: string;
  state: ConditionState;
  reason: string;
  citations: Citation[];
}
export interface Condition {
  id: string;
  text: string;
  level: string;
  state: ConditionState;
  completion_evidence: string;
}
export interface Indicator {
  code: string;
  name: string;
  pillar: string;
  lower_level: number;
  upper_level: number;
  lower: number;
  upper: number;
  conditions: Condition[];
}
export interface Result {
  aggregation?: string;
  badge_policy?: string;
  scoring_note?: string;
  lower: number;
  upper: number;
  exact_score: number | null;
  assessment_coverage: number;
  condition_decision_coverage: number;
  methodology: string;
  methodology_status: string;
  indicators: Indicator[];
  pillars: { code: string; lower: number; upper: number }[];
  tiers: {
    name: string;
    eligibility: string;
    threshold: number | null;
    pillar_floor: string | null;
    gates: Record<string, number>;
  }[];
}
export interface Action {
  id: string;
  indicator: string;
  type: string;
  requirement: string;
  suggestion: string;
  completion_evidence: string;
  state?: ConditionState;
  citations?: Citation[];
  automatic_points: false;
}
export interface Pathway {
  target: string;
  requirement_ids: string[];
  scenario_sufficient: boolean;
  already_demonstrated: boolean;
  note: string;
  projected_minimum: number;
  conditional_uplift: number | null;
}
export interface Assessment {
  result: Result;
  records: Decision[];
  actions: Action[];
  pathways: Pathway[];
  inputs_hash: string;
}
export interface Run extends Job {
  diagnostics?: {
    cause_audit?: {
      validator_affected_conditions: number;
      evaluation_unavailable_conditions: number;
      unknown_without_validator_issue: number;
      foundation_blockers: { indicator: string; blockers: { condition_id: string; requirement: string; state: ConditionState; reason: string; kind: string }[] }[];
    };
    explanation: string;
    source_documents: number;
    readable_pages: number;
    unreadable_or_unavailable_pages: number;
    state_counts: Record<ConditionState, number>;
    foundation_blockers: { indicator: string; requirements: string[] }[];
    validation_issues: { reason: string; count: number }[];
    indicators_with_bounded_context: number;
    limitations: string;
  } | null;
  inputs_hash: string;
  population: string;
  profile: {
    name: string;
    institution_type: string;
    faculty_count: number | null;
    student_count: number | null;
  };
  source_manifest: {
    document_id: string;
    filename: string;
    version: number;
    pages: { page_id: string; status: string }[];
  }[];
  deterministic_plan?: Recommendation['plan'];
  assessment: Assessment | null;
  partial_decisions: Decision[];
  error: { error_code: string; next_action: string } | null;
}
export interface Advice {
  condition_id: string;
  operation: string;
  steps: string[];
  suggested_role: string;
  effort: string;
  dependencies: string[];
  completion_evidence: string;
  basis: Citation[];
}
export interface ActionState {
  condition_id: string;
  owner: string;
  feasibility: 'unreviewed' | 'feasible' | 'blocked';
  status: 'proposed' | 'in_progress' | 'completed' | 'dismissed';
}
export interface FoundationPlan {
  version: string; destination: string; current_level: string;
  baseline: { status: string; message: string };
  goals: { id: string; title: string; target_condition_ids: string[]; depends_on: string[]; suggested_role: string; status: string; steps: string[]; existing_strengths: { condition_id: string; requirement: string; reason: string; basis: Citation[] }[] }[];
  routes: { name: string; indicative_duration: string; batches: string[][]; assumptions: string[]; outcomes: string[] }[];
  review_questions: { id: string; title: string; question: string; requirements: string[]; condition_ids: string[]; answer_policy: string }[];
  other_unresolved_requirements: number; limitations: string[];
}
export interface Recommendation extends Job {
  plan: {
    foundation_plan?: FoundationPlan | null;
    version: string;
    actions: Action[];
    next_improvements: string[];
    next_overall: {
      target: number | null;
      requirement_ids: string[];
      note?: string;
      policy: { version: string; basis: string };
    };
    note: string;
  };
  tailoring: { advice: Advice[]; mode: string } | null;
  fallback: boolean;
  action_states: ActionState[];
  error: { error_code: string; next_action: string } | null;
}
const root = (sprint: string) => `/sprints/${sprint}/capability-runs`;
const path = (sprint: string, run: string) => `${root(sprint)}/${run}`;
export const listRuns = (sprint: string, page = 1) =>
  api.get<Page<Job>>(root(sprint), { params: { page } });
export const getRun = (sprint: string, run: string) =>
  api.get<Run>(path(sprint, run));
export const startRun = (
  sprint: string,
  body: { confirmed_source_institution?: string; scope_mode?: 'default' | 'custom'; population?: string; reference_period?: string; refines_run_id?: string },
  key: string,
) => api.post<Job>(root(sprint), body, { headers: { 'Idempotency-Key': key } });
export const cancelRun = (sprint: string, run: string) =>
  api.post<Job>(`${path(sprint, run)}/cancel`);
export const listAdvice = (sprint: string, run: string, page = 1) =>
  api.get<Page<Job>>(`${path(sprint, run)}/recommendations`, {
    params: { page },
  });
export const getAdvice = (sprint: string, run: string, advice: string) =>
  api.get<Recommendation>(`${path(sprint, run)}/recommendations/${advice}`);
export const startAdvice = (sprint: string, run: string, key: string) =>
  api.post<Job>(
    `${path(sprint, run)}/recommendations`,
    {},
    { headers: { 'Idempotency-Key': key } },
  );
export const cancelAdvice = (sprint: string, run: string, advice: string) =>
  api.post<Job>(`${path(sprint, run)}/recommendations/${advice}/cancel`);
export const updateAction = (
  sprint: string,
  run: string,
  advice: string,
  condition: string,
  state: Partial<Omit<ActionState, 'condition_id'>>,
) =>
  api.patch(
    `${path(sprint, run)}/recommendations/${advice}/actions/${condition}`,
    state,
  );
export async function downloadCapabilityReport(
  sprint: string,
  run: string,
  format: 'html' | 'json' | 'pdf',
  advice?: string,
  audience: 'leadership' | 'evidence' = 'leadership',
) {
  const response = await api.get(`${path(sprint, run)}/report`, {
    params: { file: format, recommendation_id: advice, audience },
    responseType: 'blob',
  });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `capability-${run}-${audience}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export interface PlanMapping {
  condition_id: string;
  phase: 'implementation' | 'results';
  rationale: string;
  assumptions: string[];
}
export interface PlanEvaluation {
  text: string;
  evaluation: {
    baseline: Result;
    accepted: PlanMapping[];
    rejected: { mapping: PlanMapping; reason: string }[];
    scenarios: Record<'implementation' | 'results', { result: Result; paired_change: { lower: number; upper: number; basis: string } }>;
    note: string;
  };
}
export interface PlanComparison extends Job {
  original_text: string;
  inputs_hash: string;
  completed_stages: string[];
  actual_assessment_changed: false;
  original_review?: PlanEvaluation | null;
  error: { error_code: string; next_action: string } | null;
  comparison: {
    original: PlanEvaluation;
    improved: PlanEvaluation;
    comparison_basis: string;
    limitations: string[];
    improvement: {
      constraint_note: string;
      changes: { operation: string; original_action_ids: string[]; action: string; why: string; suggested_owner: string; dependencies: string[]; completion_evidence: string; resource_note: string }[];
    };
  } | null;
}
export const listPlanEvaluations = (sprint: string, run: string, page = 1) =>
  api.get<Page<Job>>(`${path(sprint, run)}/plan-evaluations`, { params: { page } });
export const getPlanEvaluation = (sprint: string, run: string, scenario: string) =>
  api.get<PlanComparison>(`${path(sprint, run)}/plan-evaluations/${scenario}`);
export const startPlanEvaluation = (sprint: string, run: string, plan_text: string, key: string) =>
  api.post<Job>(`${path(sprint, run)}/plan-evaluations`, { plan_text }, { headers: { 'Idempotency-Key': key } });
export const cancelPlanEvaluation = (sprint: string, run: string, scenario: string) =>
  api.post<Job>(`${path(sprint, run)}/plan-evaluations/${scenario}/cancel`);
export async function downloadPlanReport(sprint: string, run: string, scenario: string, format: 'html' | 'json') {
  const response = await api.get(`${path(sprint, run)}/plan-evaluations/${scenario}/report`, { params: { file: format }, responseType: 'blob' });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url; a.download = `plan-comparison-${scenario}.${format}`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
