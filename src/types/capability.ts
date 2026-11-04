/**
 * Evidence-based capability assessment (A1 backend: apps/scoring/capability, /sprints/{id}/capability-runs).
 * Trimmed to the fields this frontend reads; source of truth is frontend/src/api/capability.ts.
 */
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ConditionState = 'met' | 'not_met' | 'unknown' | 'conflicting';

export interface Job {
  id: string;
  status: JobStatus;
  created_at: string;
  stalled: boolean;
  reference_period?: string;
  rubric_version?: string;
}

export interface CapabilityPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
  count: number;
  /** Whether the deployment allows starting assessments (settings.CAPABILITY_ASSESSMENT_ENABLED). */
  enabled: boolean;
}

export interface Citation { source_id: string; quote: string }

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
  lower: number;
  upper: number;
  conditions: Condition[];
}

export interface Tier {
  name: string;
  /** demonstrated | requirements_unmet | unresolved */
  eligibility: string;
  threshold: number | null;
  pillar_floor: string | null;
  gates: Record<string, number>;
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
  indicators: Indicator[];
  pillars: { code: string; lower: number; upper: number }[];
  tiers: Tier[];
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

export interface CapabilityAction {
  id: string;
  indicator: string;
  type: string;
  requirement: string;
  suggestion: string;
  completion_evidence: string;
  state?: ConditionState;
}

export interface CapabilityAssessment {
  result: Result;
  records: { condition_id: string; state: ConditionState; reason: string; citations: Citation[] }[];
  actions: CapabilityAction[];
  pathways: Pathway[];
  inputs_hash: string;
}

export interface FoundationPlan {
  version: string;
  destination: string;
  current_level: string;
  baseline: { status: string; message: string };
  goals: {
    id: string; title: string; target_condition_ids: string[]; depends_on: string[]; suggested_role: string;
    status: string; evidence_steps: string[]; improvement_steps: string[]; improvement_condition: string;
  }[];
  routes: { name: string; indicative_duration: string; batches: string[][]; assumptions: string[]; outcomes: string[] }[];
  other_unresolved_requirements: number;
  limitations: string[];
}

export interface RecommendationPlan {
  foundation_plan?: FoundationPlan | null;
  actions: CapabilityAction[];
  next_improvements: string[];
  next_overall: { target: number | null; requirement_ids: string[]; note?: string };
  note: string;
}

export interface Run extends Job {
  error: { error_code: string; next_action: string } | null;
  profile: { name: string; institution_type: string };
  source_manifest: { document_id: string; filename: string; version: number; pages: { page_id: string; status: string }[] }[];
  diagnostics?: { explanation: string; state_counts: Partial<Record<ConditionState, number>>; limitations: string } | null;
  deterministic_plan?: RecommendationPlan;
  assessment: CapabilityAssessment | null;
}

export interface CapabilityRecommendation extends Job {
  plan: RecommendationPlan;
  error: { error_code: string; next_action: string } | null;
}
