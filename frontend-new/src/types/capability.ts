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
  /** A2 second layer: 'final' runs are published after the follow-up questions; they name their provisional run. */
  stage?: 'provisional' | 'final';
  provisional_run_id?: string | null;
}

export interface CapabilityPage<T> {
  results: T[];
  next: string | null;
  previous: string | null;
  count: number;
  /** Whether the deployment allows starting assessments (settings.CAPABILITY_ASSESSMENT_ENABLED). */
  enabled: boolean;
  /** Run list only: line-1 review questions still awaiting an answer (finish them before starting a run). */
  review_questions_awaiting?: number;
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
  /** Share of the overall score (all key indicators sum to 1000). */
  weight_units?: number;
  lower: number;
  upper: number;
  conditions: Condition[];
  explanation?: ScoreExplanation;
}

export interface Tier {
  name: string;
  /** demonstrated | requirements_unmet | unresolved */
  eligibility: string;
  threshold: number | null;
  pillar_floor: string | null;
  gates: Record<string, number>;
}

/**
 * How a score was reached (report step, announced 12 Nov 2026; not yet sent by the backend): what was found and
 * credited, where the assessment looked for what it did not find, and the next step.
 */
export interface ScoreExplanation {
  found?: string; looked?: string; next_step?: string; text?: string;
  /** One sentence about the credit held for follow-up answers (reserve.follow_up_note), when any is held. */
  follow_up?: string | null;
}

/**
 * Credit held until the follow-up answers show how deep the evidence goes (reserve.py, depth-reserve-v2).
 * evidence_score is the documents' score before anything is held; the headline `score` already counts the hold.
 */
export interface DepthReserve {
  version?: string;
  share: number;
  evidence_score: number;
  score?: number;
  held_points: number;
  earned_back_points: number;
  still_held_points: number;
  credited_requirements_by_level?: Partial<Record<'evidenced' | 'substantiated' | 'strong', number>>;
  held_for_review?: string[];
}

export interface Documented {
  method?: string;
  overall: number;
  pillars: { code: string; score: number; explanation?: ScoreExplanation }[];
  indicators: { code: string; level: number; score: number; explanation?: ScoreExplanation }[];
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
  /** Set when part of each credited requirement's credit is held for the follow-up answers; null/absent otherwise. */
  depth_reserve?: DepthReserve | null;
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
  /** Priority plan fields: establish (nothing shown), complete (partly shown) or rerun (not evaluated). */
  gap?: 'establish' | 'complete' | 'rerun' | string | null;
  credit?: number;
  missing_parts?: string[];
  /** The key indicator of the priority-plan action this requirement belongs to, if any. */
  priority_action?: string | null;
}

/** Provisional readiness levels, one star for every 20 points, until calibration (D-01). */
export interface PriorityTier {
  current: string | null;
  next: string | null;
  next_threshold: number | null;
  points_to_next: number;
  thresholds: { name: string; score: number }[];
  provisional: boolean;
  note: string;
}

/** The recommendation's priority plan on the part-credit score (action_plan.py). */
export interface PriorityPlan {
  score: number;
  tier: PriorityTier;
  target: number | null;
  projected_score: number;
  projected_tier: string | null;
  reaches_target: boolean;
  condition_ids: string[];
  actions: {
    indicator: string; name: string; pillar?: string; condition_ids: string[]; score_gain: number;
    conditions: { condition_id: string; requirement: string; level: string; gap: string; credit: number; missing_parts: string[] }[];
    builds_on?: string[];
  }[];
  strengths: { condition_id: string; indicator: string; requirement: string }[];
  remaining: { pillar: string; establish: number; complete: number; reconcile: number; rerun: number }[];
  note: string;
  /** Points the follow-up answers can earn back (priority-plan-0.2); null when nothing is held. */
  follow_up?: PriorityFollowUp | null;
}

export interface PriorityFollowUp {
  points: number;
  indicators: { indicator: string; name: string; points: number; requirements: number }[];
  note: string;
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
  /** Per-requirement explanation (report step). */
  explanation?: ScoreExplanation;
  /** Depth reserve: the held share as a fraction string ("1/4"), the depth shown so far, and the credit below which
   * nothing is held (v2; absent on v1 records). */
  depth_share?: string | number | null;
  depth_level?: 'evidenced' | 'substantiated' | 'strong' | string;
  depth_min_credit?: string | number | null;
  depth_review?: string | null;
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
  next_overall: { target: number | null; requirement_ids: string[]; note?: string; projected_score?: number };
  priority_plan?: PriorityPlan | null;
  pathways_note?: string;
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
