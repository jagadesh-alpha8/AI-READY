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

export interface Documented {
  method?: string;
  overall: number;
  pillars: { code: string; score: number }[];
  indicators: { code: string; level: number; score: number }[];
}

export interface Result {
  aggregation?: string;
  badge_policy?: string;
  scoring_note?: string;
  lower: number;
  upper: number;
  exact_score: number | null;
  /** A2 part-credit runs: the one headline score (what the documents show, with partial credit). */
  score?: number | null;
  score_method?: string;
  /** A2 part-credit runs: score per readiness area and per indicator. `lower`/`upper` stay for audit only. */
  documented?: Documented;
  documented_with_digital?: Documented;
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

/** A2 part judgment: how each part of a condition was evidenced (part_judgment.py `credited_as`). */
export type PartCredit = 'full' | 'related' | 'not_found' | string;

export interface ConditionRecord {
  condition_id: string;
  state: ConditionState;
  reason: string;
  citations: Citation[];
  /** A2 part-credit runs: credit fraction 0–1 for this condition (0 when the documents do not show it). */
  credit?: number;
  digital_credit?: number;
  pass_credits?: number[];
  parts?: { id: string; finding: string; credited_as: PartCredit; citations: Citation[] }[];
  /** Why an unknown is unknown: evidence, review guard, or processing (decision_causes.py). */
  cause?: string;
}

/** decision_causes.summary(): reads "unknown" as missing evidence, a review hold, or a processing problem. */
export interface DecisionCauses {
  version: string;
  by_state_and_cause: { state: ConditionState; cause: string; count: number }[];
  unknown_evidentiary: number;
  unknown_review: number;
  unknown_processing: number;
}

export interface CapabilityAssessment {
  result: Result;
  records: ConditionRecord[];
  actions: CapabilityAction[];
  pathways: Pathway[];
  inputs_hash: string;
  decision_causes?: DecisionCauses;
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
  /** Per-action workflow (owner, feasibility, status); never changes a score. */
  action_states?: { condition_id: string; owner: string; feasibility: string; status: string; updated_at: string }[];
  /** True when no model-tailored advice was produced and the deterministic plan is shown. */
  fallback?: boolean;
  tailoring?: { advice?: { condition_id?: string; id?: string; origin?: string; advice?: string; text?: string; [k: string]: unknown }[] } | null;
}
