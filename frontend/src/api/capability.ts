import api from './client';

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';
export interface Job {
  id: string;
  status: JobStatus;
  created_at: string;
  heartbeat_at: string;
  stalled: boolean;
  requests_reserved: number;
  reserved_cost_usd: string;
  completed_indicators?: number;
  rubric_version?: string;
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
    threshold: number;
    pillar_floor: string;
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
export interface Recommendation extends Job {
  plan: {
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
  body: { population: string; reference_period: string },
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
  format: 'html' | 'json',
  advice?: string,
) {
  const response = await api.get(`${path(sprint, run)}/report`, {
    params: { file: format, recommendation_id: advice },
    responseType: 'blob',
  });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `capability-${run}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
