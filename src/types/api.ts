/**
 * Backend response shapes this frontend reads, trimmed to the fields it uses.
 * Source of truth: backend/docs/API_CONTRACT.md and the backend serializers.
 */

export type UserRole = 'super_admin' | 'consultant' | 'iqac_coordinator';

export interface User {
  id: string;
  institution_id: string | null;
  name: string;
  first_name: string;
  last_name: string;
  email: string;
  role: UserRole;
  department_name: string;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: User;
}

/** A server-paginated list (`?page` / `?page_size`). */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// --- institutions --------------------------------------------------------------------------------------

export interface CoordinatorStatus {
  configured: boolean;
  name: string;
  email: string;
  state: string;
  state_label: string;
  can_resend: boolean;
}

export interface Institution {
  id: string;
  name: string;
  short_name: string;
  institution_type: string;
  university_affiliation: string;
  affiliation: string;
  website_url: string;
  location: string;
  city: string;
  state: string;
  country: string;
  accreditation_details: string;
  contact_email: string;
  is_active: boolean;
  sprint_count: number;
  student_count: number | null;
  faculty_count: number | null;
  priorities: string[];
  digital_maturity_level: number | null;
  current_ai_usage: string;
  coordinator?: CoordinatorStatus;
  created_at: string;
  updated_at: string;
}

export interface InstitutionLeader {
  id: string;
  name: string;
  role: string;
  email: string;
  initials: string;
}

export interface InstitutionDetail extends Institution {
  leaders: InstitutionLeader[];
  department_count: number;
  program_count: number;
  digital_maturity_label: string;
}

export interface Department {
  id: string;
  name: string;
  head_name: string;
  faculty_count: number;
  student_count: number;
  program_count: number;
}

export interface InstitutionSystem {
  id: string;
  name: string;
  tag: '' | 'legacy' | 'manual';
  tag_label: string;
  notes: string;
}

export interface CreateInstitutionPayload {
  name: string;
  coordinator_name: string;
  coordinator_email: string;
  institution_type?: string;
  city?: string;
  state?: string;
  affiliation?: string;
  accreditation_status?: string;
  website_url?: string;
}

// --- sprints -------------------------------------------------------------------------------------------

export type SprintStatus =
  | 'draft' | 'collecting' | 'processing' | 'reviewing' | 'scoring'
  | 'baseline_pending' | 'baseline_approved' | 'report_ready' | 'completed' | 'archived';

export interface Sprint {
  id: string;
  institution_id: string;
  institution_name: string;
  name: string;
  sprint_code: string;
  mode: string;
  status: SprintStatus;
  academic_year: string;
  description: string;
  start_date: string | null;
  target_completion_date: string | null;
  completion_percentage: number;
  overall_cri: number | null;
  confidence_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface SprintOverview {
  sprint: Sprint;
  documents: { total: number; pending: number; uploaded: number; processing: number; processed: number; failed: number; rejected: number };
  facts: { total: number; extracted: number; confirmed: number; corrected: number; rejected: number; evidence_requested: number };
  gaps: { total: number; open: number; in_progress: number; resolved: number; blocking_open: number };
  recommendations: { total: number; accepted: number; draft: number };
  reports: { total: number; latest: Report | null };
  /** Null until the sprint is first scored (this endpoint never bootstraps a score). */
  scorecard: Scorecard | null;
}

export interface ProcessingSummary {
  complete: boolean;
  description: string;
  counts: Record<string, number>;
}

export interface WorkSummary {
  ready_for_baseline_review: boolean;
  blockers: string[];
  totals: { pending_facts: number; open_gaps: number; fact_gaps: number; blocking_gaps: number; unassigned: number; overdue: number };
  by_role: { role?: string; label?: string; total: number; overdue: number }[];
}

export interface DashboardSprint {
  id: string;
  institution: string;
  name: string;
  status: string;
  completion: number;
  cri: number | null;
  confidence: number | null;
  pending_gaps: number;
  report_status: string | null;
  updated_at: string;
}

export interface DashboardData {
  active_sprints: number;
  completion_percentage: number;
  reports_ready: number;
  pending_confirmations: number;
  high_priority_gaps: number;
  sprint_count: number;
  institution_count: number;
  sprints: DashboardSprint[] | Page<DashboardSprint>;
}

// --- documents and extraction ------------------------------------------------------------------------

export interface SprintDocument {
  id: string;
  sprint_id: string;
  document_type: string;
  document_type_label: string;
  title: string;
  original_filename: string;
  file_size_display: string | null;
  checksum: string;
  status: 'pending' | 'uploaded' | 'processing' | 'processed' | 'failed' | 'rejected';
  processing_status: string;
  page_count: number | null;
  classification_status: string;
  ai_document_type_label: string | null;
  ocr_warnings: string[];
  uploaded_at: string | null;
  processed_at: string | null;
}

export interface ExtractionJob {
  id: string;
  document_id: string;
  document_filename: string;
  status: 'pending' | 'running' | 'retrying' | 'completed' | 'failed' | 'cancelled';
  current_step_label: string;
  progress_percentage: number;
  error_message: string;
  created_at: string;
}

// --- facts, evidence requests, gaps ---------------------------------------------------------------------

export type FactStatus = 'extracted' | 'confirmed' | 'corrected' | 'rejected' | 'evidence_requested';

export interface AIQIFMapping {
  criterion_code: string;
  indicator_code: string;
  indicator_name: string;
  confidence: number;
  status: string;
}

export interface Fact {
  id: string;
  sprint_id: string;
  field_name: string;
  field_key: string;
  value: unknown;
  data_type: string;
  pillar: string;
  pillar_label: string;
  owner_role: string;
  source_document_id: string | null;
  source_document_filename?: string;
  source_page: string;
  source_snippet: string;
  confidence_score: number;
  status: FactStatus;
  aiqif_mappings: AIQIFMapping[];
  verification?: { status: string; status_label: string } | null;
  can_act?: boolean | null;
  act_blocked_reason?: string;
  reviewed_at: string | null;
}

/** GET /facts/{id}: the fact plus its full review audit trail (backend ExtractedFactDetailSerializer). */
export interface FactDetail extends Fact {
  confidence_reason?: string;
  extraction_method?: string;
  review_history: {
    id: string;
    action: string;
    original_value: unknown;
    new_value: unknown;
    user_name: string;
    reason: string;
    created_at: string;
  }[];
}

export interface FactFacets {
  total: number;
  status: Record<string, number>;
  pillar: Record<string, number>;
}

export type EvidenceRequestStatus =
  | 'open' | 'submitted' | 'processing' | 'ready_for_review' | 'returned' | 'accepted' | 'accepted_corrected' | 'withdrawn';

export interface EvidenceRequest {
  id: string;
  sprint: string;
  sprint_code: string;
  fact: string;
  fact_field_name: string;
  evidence_needed: string;
  reason: string;
  responsible_role: string;
  assigned_to: string | null;
  assigned_to_name: string;
  requested_by_name: string;
  due_date: string | null;
  overdue: boolean;
  status: EvidenceRequestStatus;
  status_label: string;
  evidence_count: number;
  created_at: string;
}

export interface EvidenceRequestSummary {
  assigned_to_me: number;
  assigned_to_me_overdue: number;
  awaiting_my_review: number;
}

export type GapPriority = 'blocking' | 'high' | 'medium' | 'optional';

export interface Gap {
  id: string;
  sprint_id: string;
  gap_type: 'missing_document' | 'unconfirmed_fact' | 'conflict' | 'stale_data' | 'low_confidence';
  title: string;
  description: string;
  pillar: string;
  pillar_label: string;
  priority: GapPriority;
  score_impact: number;
  owner_role_label?: string;
  owner_role: string;
  status: string;
  resolution: string;
  assigned_to_name?: string;
  due_date?: string | null;
  can_act?: boolean | null;
  act_blocked_reason?: string;
  resolve_blocked_reason?: string;
  close_blocked_reason?: string;
}

/** GET /gaps/{id}: the gap with its source, competing values, evidence state and history (GapItemDetailSerializer). */
export interface GapDetail extends Gap {
  source_document_filename?: string;
  source_page: string | null;
  source_snippet: string | null;
  resolved_at: string | null;
  evidence_state?: { state: string; label: string; reason: string; next_action: string } | null;
  conflict_candidates?: {
    side: string;
    field_name: string;
    current_value: unknown;
    value_at_detection: unknown;
    fact_status: string;
    document_name: string | null;
    page: string | null;
    snippet: string | null;
    confidence_score: number | null;
  }[] | null;
  events?: { id: string; action: string; action_label: string; user_name: string; note: string; created_at: string }[];
}

export interface GapFacets {
  total: number;
  open: number;
  gap_type: Record<string, number>;
  priority: Record<string, number>;
  status: Record<string, number>;
}

// --- scoring, baseline ----------------------------------------------------------------------------------

export interface PillarScore {
  pillar: string;
  label: string;
  weight: number;
  raw_score: number;
  confidence_score: number;
  status: 'not_started' | 'at_risk' | 'developing' | 'strong';
  evidence_count: number;
  gap_count: number;
}

export interface EvidenceCoverage {
  status?: string;
  ratio?: number | null;
  covered_count?: number;
  applicable_count?: number;
  excluded_count?: number;
  unresolved_applicability_count?: number;
  release_label?: string | null;
  mappings_awaiting_review?: number;
  provisional?: boolean;
}

export interface Scorecard {
  sprint_id: string;
  overall_cri: number;
  raw_cri: number;
  coverage_adjusted_cri: number | null;
  evidence_coverage: EvidenceCoverage;
  overall_confidence: number;
  calculation_version: string;
  calculated_at: string | null;
  pillar_scores: PillarScore[];
  strengths: { pillar: string; label: string; raw_score: number; status: string }[];
  weaknesses: { pillar: string; label: string; raw_score: number; status: string }[];
  evidence_metrics: {
    confirmed_facts: number;
    corrected_facts: number;
    total_extracted_facts: number;
    documents_processed: number;
    unresolved_gaps: number;
  };
  unresolved_blocking_gaps: Gap[];
}

export interface ScoreHistoryRow {
  id?: string;
  overall_cri: number;
  overall_confidence?: number;
  coverage_adjusted_cri?: number | null;
  calculation_version?: string;
  calculated_at?: string;
  created_at?: string;
  trigger?: string;
}

export interface PillarConfig {
  key: string;
  name: string;
  description: string;
  weight: number;
  is_active: boolean;
  criteria: { key: string; name: string; weight: number; is_active: boolean }[];
}

export interface Baseline {
  id: string;
  status: 'pending' | 'approved' | 'provisional' | 'returned';
  overall_cri: number;
  overall_confidence: number;
  approved_by_name: string;
  approved_at: string | null;
  comments: string;
  history: { id: string; action: string; user_name: string; comments: string; created_at: string }[];
}

export interface SprintBaseline {
  baseline: Baseline;
  can_approve: boolean;
  baseline_is_current?: boolean;
}

// --- recommendations, reports ---------------------------------------------------------------------------

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  trigger_gap: string;
  pillar_label: string;
  owner_role: string;
  priority: GapPriority;
  timeline: string;
  expected_cri_lift: number;
  status: 'draft' | 'accepted' | 'edited' | 'hidden' | 'completed';
}

export interface Report {
  id: string;
  sprint_id: string;
  version: number;
  status: 'draft' | 'generating' | 'ready' | 'failed';
  overall_cri: number;
  confidence_score: number;
  generated_at: string | null;
  pdf_available: boolean;
  docx_available: boolean;
  created_at: string;
}

// --- benchmark assessments (apps/assessments) ----------------------------------------------------------

export type Level = 'L3' | 'L2' | 'L1';

export interface Assessment {
  current_level: string;
  compliance_score: string | null;
  maturity_score: string | null;
  evidence_confidence_score: string | null;
  outcome_score: string | null;
  composite_score: string | null;
  detail: { level_notes?: string[]; needs_assessor_confirmation?: boolean };
  scored_at: string | null;
}

export interface Cycle {
  id: string;
  institution: string;
  institution_name: string;
  name: string;
  opens_on: string;
  closes_on: string | null;
  status: 'not_started' | 'in_progress' | 'submitted' | 'reviewed' | 'finalized';
  status_label: string;
  release_label: string;
  release_hash: string;
  created_at: string;
  finalized_at: string | null;
}

export interface CycleBenchmarkRow {
  benchmark_code: string;
  title: string;
  pillar: string;
  kind: string;
  applicability_result: string;
  applicability_reason: string;
  included: boolean | null;
  target_level: Level;
  requests: number;
  evidence: number;
  accepted: number;
  waiting: number;
  assessment: Assessment | null;
}

export interface CycleDetail extends Cycle {
  scores_visible: boolean;
  benchmarks: CycleBenchmarkRow[];
}

export interface CollegeProfile {
  institution: string;
  institution_name: string;
  profile: null | {
    institution_type: string;
    institution_type_name: string;
    autonomous_status: string;
    approval_bodies: string[];
    jurisdiction: string;
    updated_at: string;
  };
  programmes: { name: string; programme_type: string; programme_type_name?: string; approval_body: string }[];
}

export type PlanStatus = 'planned' | 'active' | 'blocked' | 'complete';

export interface PlanTask {
  id: string;
  title: string;
  owner: string;
  due_date: string | null;
  status: PlanStatus;
  status_label: string;
  evidence_due: string;
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
  status: string;
  status_label: string;
  closing_evidence_title: string | null;
  initiatives: PlanInitiative[];
}

export interface ImprovementPlan {
  cycle: string;
  has_plan: boolean;
  gaps: PlanGap[];
  summary: { gaps: number; open: number; critical_open: number; tasks: number; tasks_done: number };
}

// --- benchmark library (apps/benchmarks, InGage staff only) --------------------------------------------

export interface SourceDocument {
  id: string;
  source_code: string;
  title: string;
  authority_name: string;
  category: string;
  source_role_label: string;
  version_count: number;
  latest_version: { version_label: string; status: string; requirement_count: number } | null;
}

export interface SourceLibrarySummary {
  documents: number;
  versions: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  flagged_versions: number;
}

export interface CataloguePillar {
  code: string;
  name: string;
  benchmark_count: number;
  mandatory_count: number;
  guidance_count: number;
  proposed_count: number;
}

export interface ApplicabilityPreview {
  institution: string;
  profile: Record<string, unknown> | null;
  detail?: string;
  counts: Partial<Record<'applies' | 'does_not_apply' | 'optional' | 'requires_review', number>>;
  benchmarks: { benchmark_code: string; title: string; pillar_code: string; result: string; reason: string }[];
}

// --- users, access, evidence search ----------------------------------------------------------------------

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  institution_name: string;
  department_name: string;
  is_active: boolean;
}

export interface RoleAccessDefinition {
  role: string;
  name: string;
  institution_scope: string;
  description: string;
  modules: { name: string; access: string; description: string }[];
}

export interface EvidenceResult {
  score: number;
  text: string;
  document_id: string;
  document_name: string;
  page_number: number | null;
}
