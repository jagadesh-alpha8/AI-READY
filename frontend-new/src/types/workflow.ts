/**
 * Shapes for the backend endpoints added in the full API integration pass. Trimmed to the fields this frontend
 * reads; the sources of truth are the A1 backend serializers and A1's frontend/src/types + frontend/src/api.
 */
import type { Baseline, Fact, Scorecard, SprintBaseline } from './api';

// --- users ------------------------------------------------------------------------------------------------

export interface UserPayload {
  email?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  role?: string;
  institution_id?: string | null;
  department_name?: string;
  is_active?: boolean;
  password?: string;
}

export interface UserDeletionPreview {
  can_delete: boolean;
  dependencies: { model: string; field: string; count: number }[];
  detail: string;
}

// --- institutions -----------------------------------------------------------------------------------------

export interface InstitutionDeletionPreview {
  institution_id: string;
  institution_name: string;
  can_delete: boolean;
  is_blocked: boolean;
  block_reason: string | null;
  recommended_action: 'delete' | 'archive';
  dependencies: Record<string, number>;
  protected_counts: Record<string, number>;
}

export interface DepartmentPayload { name?: string; head_name?: string; faculty_count?: number; student_count?: number; program_count?: number }
export interface SystemPayload { name?: string; tag?: '' | 'legacy' | 'manual'; notes?: string }
export interface LeaderPayload { name?: string; role?: string; email?: string }

// --- documents, drive import, AI usage --------------------------------------------------------------------

export type DriveJobStatus = 'pending' | 'scanning' | 'downloading' | 'completed' | 'failed' | 'cancelled';

export interface DriveImportJob {
  id: string;
  drive_url: string;
  status: DriveJobStatus;
  results: Record<string, unknown>;
  files_scanned: number;
  files_imported: number;
  scan_limit_reached?: boolean;
  error_message: string;
  created_at: string;
  completed_at: string | null;
}

export interface AIUsageTotals {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: string;
}

export interface SprintAIUsage extends AIUsageTotals {
  first_call: string | null;
  last_call: string | null;
  unpriced_calls: number;
  documents: number;
  notes: string[];
  by_stage: (AIUsageTotals & { stage: string })[];
  by_model: (AIUsageTotals & { model: string })[];
  top_documents: (AIUsageTotals & { document_id: string; filename: string })[];
}

export interface PlatformAIUsage extends AIUsageTotals {
  unpriced_calls: number;
  notes: string[];
  rows: { institution: string; sprint: string; month: string; documents: number; calls: number; total_tokens?: number; cost_usd: string }[];
}

// --- fact verification, corrections, AI-QIF --------------------------------------------------------------

export interface FactVerificationDetail {
  fact_id: string;
  mode: 'shadow' | 'enforce';
  latest: null | {
    outcome: string;
    reason: string;
    risk_level: string;
    automation_decision: string;
    automation_reason: string;
    grounding: { status: string; quote: string; value_support: string; detail: string[] };
    validation: { status: string; checks: { code: string; label: string; status: string; detail: string }[] };
    cross_source: { status: string; compared: { fact_id: string; value: unknown; document: string | null; page: string; agrees: boolean }[] };
    blockers: string[];
    created_at: string;
  };
  earlier: { id: string; source: string; outcome: string; reason: string; created_at: string }[];
}

export interface CorrectionProposal {
  id: string;
  fact: string;
  field_name: string;
  value_before: unknown;
  proposed_value: unknown;
  reason: string;
  source_document_name: string | null;
  source_page: string;
  source_snippet: string;
  verification: { outcome?: string; reason?: string };
  status: 'pending' | 'approved' | 'rejected' | 'withdrawn' | 'stale';
  submitted_by_name: string;
  reviewed_by_name: string;
  created_at: string;
}

export interface VerificationSummary {
  mode: 'shadow' | 'enforce';
  policy_version: string;
  workload: { facts: number; verified_once: number; outcomes: Record<string, number>; auto_verified: number; sent_to_review: number; reviewer_overrides: number };
  groups: { code: string; label: string; count: number; high_risk: number }[];
}

export interface AIQIFSummary {
  facts: number;
  ai_evidence: number;
  context: number;
  profile: number;
  not_classified: number;
  expert_queue: { tags: number; facts: number; total: number };
  coverage_provisional: boolean;
}

export interface AIQIFExpertQueue {
  count: number;
  facts: Fact[];
  indicators: { code: string; criterion: string; name: string }[];
}

export interface BulkConfirmResult {
  requested_count: number;
  confirmed_count: number;
  skipped: { id: string; reason: string }[];
  skipped_count: number;
}

export interface ProfileValues {
  institution_type: string;
  autonomous_status: string;
  approval_bodies: string[];
  programmes: { name: string; programme_type: string; approval_body: string }[];
}

export interface ProfileSuggestion {
  institution_name: string;
  current: ProfileValues | null;
  suggested: {
    institution_type: { value: string; conflict: boolean };
    autonomous_status: { value: string; conflict: boolean };
    approval_bodies: string[];
    programmes: { name: string; programme_type: string; approval_body: string }[];
  };
  options: {
    institution_types: { code: string; name: string }[];
    autonomous_statuses: { code: string; name: string }[];
    approval_bodies: string[];
    programme_types: { code: string; name: string }[];
  };
}

/** GET /sprints/{id}/review-batch: the guided review (at most 25 initial questions). */
export interface ReviewBatch {
  started: boolean;
  id?: string;
  initial_limit: number;
  mode: string;
  cases: ReviewCase[];
  overflow: ReviewCase[];
  decisions: Record<string, { action: string; rationale: string; timestamp: string }>;
  new_unbatched_fact_count?: number;
  new_material_case_count?: number;
  note?: string;
}

export interface ReviewCase {
  id: string;
  kind?: 'identity';
  question: string;
  reason: string;
  suggestion: string;
  conflict: boolean;
  essential_scope: boolean;
  affected_requirements: string[];
  alternatives: {
    value: unknown;
    fact_ids: string[];
    excerpts: { fact_id: string; filename: string; page: string; quote: string; verification: string | null }[];
  }[];
  fact_ids: string[];
  initial: boolean;
  state: string;
  changed: boolean;
}

export type ReviewAction = 'identity' | 'confirm' | 'choose' | 'correct' | 'defer' | 'cannot_establish';

// --- evidence requests ------------------------------------------------------------------------------------

export interface EvidenceAssignee { id: string; name: string; email: string; role: string }

export interface EvidenceRequestDetail {
  id: string;
  fact_field_name: string;
  fact_value: unknown;
  evidence_needed: string;
  reason: string;
  status: string;
  status_label: string;
  assigned_to: string | null;
  assigned_to_name: string;
  responsible_role: string;
  due_date: string | null;
  overdue: boolean;
  fact_source_page: string;
  fact_source_snippet: string;
  resolution_note: string;
  evidence: {
    id: string;
    document_filename: string;
    submitted_text: string;
    note: string;
    submitted_by_name: string;
    status: string;
    analysis_status: 'pending' | 'processing' | 'ready' | 'failed';
    analysis_outcome: string;
    analysis_summary: string;
    analysis_quote: string;
    analysis_error: string;
    review_reason: string;
    created_at: string;
  }[];
  events: { id: string; action_label: string; user_name: string; note: string; created_at: string }[];
}

export type EvidenceDecision = 'accept' | 'accept_corrected' | 'return' | 'reject' | 'withdraw';

// --- baseline ---------------------------------------------------------------------------------------------

export type { Baseline, SprintBaseline, Scorecard };

// --- vector index -----------------------------------------------------------------------------------------

export interface VectorIndexRow {
  document: string;
  document_name?: string;
  status: string;
  chunk_count?: number;
  vector_count?: number;
  error_message?: string;
  indexed_at?: string | null;
}

// --- capability recommendation actions and plan evaluations ----------------------------------------------

export interface ActionState {
  condition_id: string;
  owner: string;
  feasibility: 'unreviewed' | 'feasible' | 'blocked';
  status: 'proposed' | 'in_progress' | 'completed' | 'dismissed';
}

export interface PlanEvaluationJob {
  id: string;
  status: string;
  created_at: string;
}

export interface PlanComparison extends PlanEvaluationJob {
  original_text: string;
  error: { error_code: string; next_action: string } | null;
  comparison: null | {
    comparison_basis: string;
    limitations: string[];
    improvement: {
      constraint_note: string;
      changes: { operation: string; action: string; why: string; suggested_owner: string; completion_evidence: string }[];
    };
  };
}

// --- benchmark assessment (cycles) ------------------------------------------------------------------------

export interface AssessmentReference {
  institution_types: { code: string; name: string }[];
  programme_types: { code: string; name: string }[];
  autonomous_statuses: { code: string; name: string }[];
  approval_bodies: string[];
  current_release: string | null;
  is_staff: boolean;
  can_upload: boolean;
}

export interface CycleEvidenceItem {
  id: string;
  rule_key: string;
  title: string;
  has_file: boolean;
  from_audit: boolean;
  original_filename: string;
  source_url: string;
  status: 'submitted' | 'accepted' | 'rejected' | 'needs_information';
  status_label: string;
  submitted_by: string;
  created_at: string;
  reviews: { id: string; reviewer: string; decision_label: string; notes: string; reviewed_at: string }[];
}

export interface CycleBenchmarkDetail {
  benchmark_code: string;
  title: string;
  kind: string;
  cycle_status: string;
  included: boolean | null;
  target_level: 'L3' | 'L2' | 'L1';
  applicability_result: string;
  applicability_reason: string;
  requirements: { code: string; statement: string; source_code: string; page: number | null }[];
  requests: {
    key: string;
    level: string;
    title: string;
    evidence_type_name: string;
    mandatory: boolean;
    minimum_count: number;
    validation_method: string;
    items: CycleEvidenceItem[];
  }[];
  assessment: null | { current_level: string; composite_score: string | null; assessor_notes: string; outcome_score: string | null };
}

export interface CycleScorecard {
  id: string;
  name: string;
  release_label: string;
  status: string;
  method: string;
  scoring_model: { name: string; formula_version: string; description: string } | null;
  benchmarks: { benchmark_code: string; title: string; target_level: string; assessment: { current_level: string; composite_score: string | null } | null }[];
}

export interface SprintDocumentOption { id: string; title: string; filename: string; document_type: string; uploaded_at: string }

export interface TransformationTemplate {
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

export interface ScoreRules {
  scoring_model: string | null;
  rules: {
    benchmark_code: string;
    title: string;
    status: string;
    weights: null | { compliance: string; maturity: string; evidence_confidence: string; outcome: string };
    approved_by: string | null;
    note: string;
  }[];
}

// --- benchmark library (read-only in the portal) ----------------------------------------------------------

export interface CatalogueBenchmark {
  id: string;
  benchmark_code: string;
  title: string;
  pillar_code: string;
  pillar_name: string;
  capability: string;
  benchmark_kind: string;
  kind_label: string;
  status: string;
  version_label: string;
  applicability: string;
  source_basis: string;
  evidence_types: string[];
  requirement_count: number;
  levels_defined: boolean;
  maturity_levels: { level: string; level_label: string; definition: string; measurement_rule: string }[];
}

export interface BenchmarkRelease {
  id: string;
  release_label: string;
  status: string;
  release_notes: string;
  based_on: string | null;
  created_at: string;
  published_at: string | null;
  item_count: number;
  kind?: string;
  content_hash: string;
}

export interface RequirementRow {
  id: string;
  code: string;
  source_code: string;
  source_title?: string;
  version_label: string;
  statement: string;
  kind: string;
  page: number | null;
}

export interface WatcherEvent {
  id: string;
  title?: string;
  summary?: string;
  status?: string;
  source_code?: string;
  detected_at?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface BenchmarkCandidate {
  id: string;
  candidate_type: string;
  type_label: string;
  title: string;
  status: string;
  status_label: string;
  benchmark_code: string | null;
  source_code: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface EvidenceTypeInfo { code: string; name: string; validation_method: string; examples: string }
