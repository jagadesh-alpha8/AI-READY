import api from './client';

/** Source Library (stage 1 of the benchmark backend) -- InGage staff only. */

export interface SourceVersion {
  id: string;
  version_label: string;
  status: 'draft' | 'active' | 'superseded' | 'withdrawn';
  issued_on: string | null;
  effective_from: string | null;
  collection_status: string;
  collection_status_label: string;
  reported_status: string;
  direct_url: string;
  drive_url: string;
  file_size_kb: number | null;
  pages: number | null;
  checksum_sha256: string;
  supersedes: string | null;
  register_row_id: string;
  review_flags: string[];
  file_uri: string;
  intake_status: 'not_run' | 'verified' | 'computed' | 'mismatch' | 'failed' | 'skipped';
  intake_note: string;
  extraction_status: 'idle' | 'queued' | 'running' | 'done' | 'failed';
  extraction_note: string;
  approved_by: string | null;
  approved_at: string | null;
  pending_candidates: number;
  requirement_count: number;
}

export interface SourceDocument {
  id: string;
  source_code: string;
  title: string;
  authority: string;
  authority_name: string;
  authority_kind: string;
  category: string;
  source_role: string;
  source_role_label: string;
  document_type: string;
  applies_to: string;
  official_url: string;
  licensed_content: boolean;
  review_cadence_months: number;
  version_count: number;
  latest_version: SourceVersion | null;
  review_flag_count: number;
}

export interface SourceLibrarySummary {
  documents: number;
  versions: number;
  by_collection_status: Record<string, number>;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  flagged_versions: number;
}

export function listSources(params: { q?: string; category?: string } = {}) {
  return api.get<SourceDocument[]>('/benchmarks/sources', { params });
}

export function getSourceSummary() {
  return api.get<SourceLibrarySummary>('/benchmarks/sources/summary');
}

// -- actions (InGage staff) ---------------------------------------------------

export interface RequirementCandidate {
  id: string;
  statement: string;
  kind: 'mandatory' | 'recommended' | 'guidance' | 'proposed';
  page: number | null;
  source_quote: string;
  confidence: number;
  rationale: string;
  model: string;
  status: 'pending' | 'accepted' | 'rejected';
  reviewed_by: string | null;
  review_note: string;
  requirement_code: string | null;
}

export function ingestVersionFile(versionId: string) {
  return api.post<{ result: string; note: string; version: SourceVersion }>(`/benchmarks/versions/${versionId}/intake`);
}

export function approveVersion(versionId: string, body: { note?: string; acknowledge_flags?: boolean }) {
  return api.post<SourceVersion>(`/benchmarks/versions/${versionId}/approve`, body);
}

export function withdrawVersion(versionId: string, note: string) {
  return api.post<SourceVersion>(`/benchmarks/versions/${versionId}/withdraw`, { note });
}

export function draftRequirements(versionId: string) {
  return api.post<SourceVersion>(`/benchmarks/versions/${versionId}/draft-requirements`);
}

export function listCandidates(versionId: string, status = 'pending') {
  return api.get<RequirementCandidate[]>(`/benchmarks/versions/${versionId}/candidates`, { params: { status } });
}

export function reviewCandidate(
  candidateId: string,
  body: { decision: 'accept' | 'reject'; statement?: string; kind?: string; note?: string },
) {
  return api.post<RequirementCandidate>(`/benchmarks/candidates/${candidateId}/review`, body);
}

// -- catalogue (stage 3) ------------------------------------------------------

export interface MaturityLevel {
  level: 'L3' | 'L2' | 'L1';
  level_label: string;
  definition: string;
  measurement_rule: string;
  is_placeholder: boolean;
  /** Model name when AI wrote it (fully automatic drafting); empty = a person. */
  ai_model?: string;
  observable_requirements?: string[];
}

/** A NAAC metric whose evidence can support a benchmark (supporting only, never proof). */
export interface NaacCrosswalkLink {
  metric: string;
  naac_key_indicator: string;
  requirement: string;
  relationship: string;
  shared_with: string[];
}

export interface CatalogueBenchmark {
  id: string;
  benchmark_code: string;
  title: string;
  pillar_code: string;
  pillar_name: string;
  capability: string;
  benchmark_kind: 'mandatory' | 'recommended' | 'guidance' | 'proposed';
  kind_label: string;
  benchmark_class: string;
  version_label: string;
  status: string;
  applicability: string;
  source_basis: string;
  scoring_dimensions: string;
  activation_status: string;
  expert_owner: string;
  evidence_types: string[];
  maturity_levels: MaturityLevel[];
  requirement_count: number;
  levels_defined: boolean;
  framework: string | null;
  /** Provisional weight out of 1000 (decimal string), e.g. "30.00". */
  weight: string | null;
  pillar_weight: string | null;
  naac_crosswalk: NaacCrosswalkLink[];
}

export interface CataloguePillar {
  code: string;
  name: string;
  coverage: string;
  catalogue_status: string;
  weight: string | null;
  benchmark_count: number;
  mandatory_count: number;
  guidance_count: number;
  proposed_count: number;
}

export interface EvidenceTypeInfo {
  code: string;
  name: string;
  validation_method: string;
  examples: string;
  assessment_use: string;
}

export function listCatalogue(params: { pillar?: string; kind?: string; q?: string } = {}) {
  return api.get<CatalogueBenchmark[]>('/benchmarks/catalogue', { params });
}

export function listPillars() {
  return api.get<CataloguePillar[]>('/benchmarks/pillars');
}

export function listEvidenceTypes() {
  return api.get<EvidenceTypeInfo[]>('/benchmarks/evidence-types');
}

// -- requirement <-> benchmark links (stage 3.2) ----------------------------------

export type LinkRelationship = 'primary' | 'supporting' | 'crosswalk';

export interface BenchmarkLink {
  benchmark_code: string;
  requirement_code: string;
  statement: string;
  kind: string;
  page: number | null;
  source_quote: string;
  source_code: string;
  relationship: LinkRelationship;
  note: string;
  linked_by: string | null;
  linked_at: string | null;
}

export interface ApprovedRequirement {
  id: string;
  code: string;
  source_code: string;
  version_label: string;
  statement: string;
  kind: string;
  page: number | null;
  source_quote: string;
  approved_by: string;
  approved_at: string;
  benchmarks: { benchmark_code: string; relationship: LinkRelationship }[];
}

export interface BenchmarkSuggestion {
  benchmark_code: string;
  title: string;
  pillar_code: string;
  score: number;
  reasons: string[];
}

export function listBenchmarkLinks(benchmarkCode: string) {
  return api.get<BenchmarkLink[]>(`/benchmarks/catalogue/${benchmarkCode}/requirements`);
}

export function linkRequirement(benchmarkCode: string, body: { requirement_code: string; relationship: LinkRelationship; note?: string }) {
  return api.post<BenchmarkLink[]>(`/benchmarks/catalogue/${benchmarkCode}/requirements`, body);
}

export function unlinkRequirement(benchmarkCode: string, requirementCode: string) {
  return api.delete(`/benchmarks/catalogue/${benchmarkCode}/requirements/${requirementCode}`);
}

export function listApprovedRequirements(params: { unlinked?: boolean; source_code?: string } = {}) {
  return api.get<ApprovedRequirement[]>('/benchmarks/requirements', {
    params: { unlinked: params.unlinked ? 1 : undefined, source_code: params.source_code },
  });
}

export function suggestBenchmarks(requirementCode: string) {
  return api.get<BenchmarkSuggestion[]>(`/benchmarks/requirements/${requirementCode}/suggestions`);
}

// -- writing levels (stage 3.3) ----------------------------------------------------

export interface LevelInput {
  definition: string;
  measurement_rule?: string;
  observable_requirements?: string[];
  minimum_evidence?: string[];
  outcome_expectations?: string[];
  non_examples?: string[];
  requires_manual_review?: boolean;
  note?: string;
}

export interface EditableLevel extends MaturityLevel {
  observable_requirements: string[];
  minimum_evidence: string[];
  outcome_expectations: string[];
  non_examples: string[];
  requires_manual_review: boolean;
  edited_by: string | null;
  edited_at: string | null;
}

export interface ReadinessCheck {
  key: string;
  label: string;
  severity: 'required' | 'recommended' | 'pending';
  ok: boolean;
  detail: string;
}

export interface Readiness {
  ready_for_review: boolean;
  checks: ReadinessCheck[];
}

export interface HistoryEntry {
  at: string;
  actor: string;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string;
}

export function getBenchmark(code: string) {
  return api.get<CatalogueBenchmark & { target_guidance: string; maturity_levels: EditableLevel[] }>(
    `/benchmarks/catalogue/${code}`,
  );
}

export function updateBenchmark(code: string, body: { expert_owner?: string; target_guidance?: string }) {
  return api.patch(`/benchmarks/catalogue/${code}`, body);
}

export function saveLevel(code: string, level: 'L3' | 'L2' | 'L1', body: LevelInput) {
  return api.put<EditableLevel>(`/benchmarks/catalogue/${code}/levels/${level}`, body);
}

export function getReadiness(code: string) {
  return api.get<Readiness>(`/benchmarks/catalogue/${code}/readiness`);
}

export function getHistory(code: string) {
  return api.get<HistoryEntry[]>(`/benchmarks/catalogue/${code}/history`);
}

// -- evidence rules (stage 3.4) ------------------------------------------------------

export interface EvidenceRule {
  /** Model name when AI wrote it; empty = a person. */
  ai_model?: string;
  id: string;
  benchmark_code: string | null;
  requirement_code: string | null;
  level: '' | 'L3' | 'L2' | 'L1';
  evidence_type: string;
  evidence_type_name: string;
  title: string;
  description: string;
  mandatory: boolean;
  minimum_count: number;
  minimum_currency_months: number | null;
  scope_rule: string;
  validation_method: 'auto_extract' | 'manual_review' | 'system_integration' | 'ai_assisted_review';
  validation_method_label: string;
  privacy_classification: 'public' | 'internal' | 'confidential' | 'restricted';
  created_by: string | null;
}

export type EvidenceRuleInput = Partial<Omit<EvidenceRule, 'id' | 'benchmark_code' | 'requirement_code' |
  'evidence_type_name' | 'validation_method_label' | 'created_by' | 'minimum_currency_months'>> & {
  minimum_currency_months?: number | '' | null;
};

export interface BenchmarkEvidenceRules {
  benchmark_rules: EvidenceRule[];
  requirement_rules: EvidenceRule[];
  level_coverage: Record<'L3' | 'L2' | 'L1', number>;
}

export function getBenchmarkEvidenceRules(code: string) {
  return api.get<BenchmarkEvidenceRules>(`/benchmarks/catalogue/${code}/evidence-rules`);
}

export function createBenchmarkEvidenceRule(code: string, body: EvidenceRuleInput) {
  return api.post<EvidenceRule>(`/benchmarks/catalogue/${code}/evidence-rules`, body);
}

export function deleteEvidenceRule(id: string) {
  return api.delete(`/benchmarks/evidence-rules/${id}`);
}

// -- applicability (stage 3.5) ----------------------------------------------------------

export type ApplicabilityResult = 'applies' | 'does_not_apply' | 'optional' | 'requires_review';

export interface ApplicabilityReference {
  institution_types: { code: string; name: string }[];
  programme_types: { code: string; name: string; sector: string }[];
  autonomous_statuses: { code: string; name: string }[];
  approval_bodies: string[];
  results: { code: ApplicabilityResult; name: string }[];
}

export interface ApplicabilityRule {
  /** Model name when AI wrote it; empty = a person. */
  ai_model?: string;
  id: string;
  benchmark_code: string | null;
  requirement_code: string | null;
  result: ApplicabilityResult;
  result_label: string;
  priority: number;
  institution_types: string[];
  autonomous_statuses: string[];
  programme_types: string[];
  approval_bodies: string[];
  jurisdiction: string;
  reason: string;
  created_by: string | null;
}

export type ApplicabilityRuleInput = Pick<ApplicabilityRule, 'result' | 'priority' | 'institution_types' |
  'autonomous_statuses' | 'programme_types' | 'approval_bodies' | 'jurisdiction' | 'reason'>;

export interface InstitutionProfile {
  institution_type: string;
  autonomous_status?: string;
  programme_types?: string[];
  approval_bodies?: string[];
  jurisdiction?: string;
}

export interface ApplicabilityPreview {
  counts: Partial<Record<ApplicabilityResult, number>>;
  benchmarks: { benchmark_code: string; title: string; pillar_code: string; result: ApplicabilityResult; reason: string }[];
}

export function getApplicabilityReference() {
  return api.get<ApplicabilityReference>('/benchmarks/applicability/reference');
}

export function listApplicabilityRules(code: string) {
  return api.get<ApplicabilityRule[]>(`/benchmarks/catalogue/${code}/applicability-rules`);
}

export function createApplicabilityRule(code: string, body: ApplicabilityRuleInput) {
  return api.post<ApplicabilityRule>(`/benchmarks/catalogue/${code}/applicability-rules`, body);
}

export function deleteApplicabilityRule(id: string) {
  return api.delete(`/benchmarks/applicability-rules/${id}`);
}

export function previewApplicability(profile: InstitutionProfile) {
  return api.post<ApplicabilityPreview>('/benchmarks/applicability/preview', profile);
}

// -- releases (stage 3.6) ----------------------------------------------------------------

export type ReleaseStatus = 'draft' | 'review' | 'approved' | 'published' | 'retired';

export interface ReleaseItem {
  benchmark_code: string;
  title: string;
  pillar_code: string;
  benchmark_status: string;
  change_type: 'added' | 'updated' | 'retired' | 'unchanged';
  change_type_label: string;
  impact_summary: string;
  snapshot_hash: string;
}

export interface BenchmarkReleaseInfo {
  id: string;
  release_label: string;
  status: ReleaseStatus;
  release_notes: string;
  based_on: string | null;
  created_by: string | null;
  submitted_by: string | null;
  approved_by: string | null;
  published_by: string | null;
  published_at: string | null;
  retired_at: string | null;
  content_hash: string;
  item_count: number;
}

export interface ReleaseDetail extends BenchmarkReleaseInfo {
  items: ReleaseItem[];
  problems: string[];
  warnings: string[];
}

export interface ReleaseDiffRow {
  benchmark_code: string;
  title: string;
  change_type: string;
  changed: string[];
  impact_summary: string;
}

const rel = (label: string) => `/benchmarks/releases/${encodeURIComponent(label)}`;

export function listReleases() {
  return api.get<BenchmarkReleaseInfo[]>('/benchmarks/releases');
}

export function createRelease(body: { release_label: string; release_notes?: string }) {
  return api.post<ReleaseDetail>('/benchmarks/releases', body);
}

export function getRelease(label: string) {
  return api.get<ReleaseDetail>(rel(label));
}

export function addReleaseItem(label: string, body: { benchmark_code: string; retire?: boolean; impact_summary?: string }) {
  return api.post<ReleaseDetail>(`${rel(label)}/items`, body);
}

export function removeReleaseItem(label: string, benchmarkCode: string) {
  return api.delete<ReleaseDetail>(`${rel(label)}/items/${benchmarkCode}`);
}

export function releaseAction(label: string, action: 'submit' | 'approve' | 'publish' | 'send-back', note = '') {
  return api.post<ReleaseDetail>(`${rel(label)}/${action}`, { note });
}

export function getReleaseDiff(label: string) {
  return api.get<ReleaseDiffRow[]>(`${rel(label)}/diff`);
}


/** Stage 4: daily watcher of official source pages. It only records; people decide. */

export type ChangeKind = 'new_document' | 'new_version' | 'content_change' | 'withdrawal' | 'access_change';
export type ChangeStatus = 'triaged' | 'ignored' | 'under_review' | 'accepted' | 'rejected';

export interface WatcherRunInfo {
  id: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'complete' | 'partial_failure' | 'failed';
  trigger: string;
  feeds_checked: number;
  changes_detected: number;
  candidates_created: number;
  failure_detail: { source_code: string; url: string; error: string }[];
}

export interface WatcherSummary {
  schedule_enabled: boolean;
  schedule_hour_utc: number;
  feeds: number;
  feeds_enabled: number;
  open_events: number;
  new_events: number;
  last_run: WatcherRunInfo | null;
}

export interface SourceFeedInfo {
  id: string;
  source_code: string;
  source_title: string;
  authority: string;
  feed_type: string;
  feed_type_label: string;
  endpoint_url: string;
  enabled: boolean;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_result: string;
  last_error: string;
  snapshot_count: number;
  open_events: number;
}

export interface SourceChangeEventInfo {
  id: string;
  source_code: string;
  source_title: string;
  endpoint_url: string;
  change_kind: ChangeKind;
  change_kind_label: string;
  materiality_score: string;
  summary: string;
  details: {
    added?: [string, string][];
    removed?: [string, string][];
    added_lines?: string[];
    removed_lines?: string[];
    http_status?: number | null;
  };
  impact: { requirements?: string[]; benchmarks?: string[]; published_releases?: string[]; note?: string };
  detected_at: string;
  status: ChangeStatus;
  status_label: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string;
}

export function getWatcherSummary() {
  return api.get<WatcherSummary>('/benchmarks/watcher/summary');
}

export function listWatcherFeeds(params: { enabled?: 'true' | 'false'; q?: string } = {}) {
  return api.get<SourceFeedInfo[]>('/benchmarks/watcher/feeds', { params });
}

export function setFeedEnabled(id: string, enabled: boolean, note = '') {
  return api.post<SourceFeedInfo>(`/benchmarks/watcher/feeds/${id}/enable`, { enabled, note });
}

export function checkFeedNow(id: string) {
  return api.post<{ result: { result: string; events: number; detail: string }; feed: SourceFeedInfo }>(
    `/benchmarks/watcher/feeds/${id}/check`);
}

export function listWatcherRuns() {
  return api.get<WatcherRunInfo[]>('/benchmarks/watcher/runs');
}

export function startWatcherRun() {
  return api.post<{ detail: string }>('/benchmarks/watcher/runs');
}

export function listChangeEvents(status: 'open' | 'all' | ChangeStatus = 'open') {
  return api.get<SourceChangeEventInfo[]>('/benchmarks/watcher/events', { params: { status } });
}

export function reviewChangeEvent(id: string, status: Exclude<ChangeStatus, 'triaged'>, note: string) {
  return api.post<SourceChangeEventInfo>(`/benchmarks/watcher/events/${id}/review`, { status, note });
}

/** Stage 4b: benchmark candidates -- proposed library changes awaiting expert approval. */

export type CandidateStatus = 'research' | 'review' | 'approved' | 'rejected' | 'published';
export type CandidateRole = 'accreditation' | 'academic' | 'legal' | 'ai_governance' | 'cybersecurity' | 'product';

export interface CandidateReviewInfo {
  id: string;
  reviewer: string;
  reviewer_role: CandidateRole;
  reviewer_role_label: string;
  decision: 'approve' | 'reject' | 'needs_research';
  decision_label: string;
  notes: string;
  reviewed_at: string;
}

export interface BenchmarkCandidateInfo {
  id: string;
  candidate_type: 'update_benchmark' | 'new_benchmark' | 'retire_benchmark' | 'source_update';
  type_label: string;
  title: string;
  status: CandidateStatus;
  status_label: string;
  benchmark_code: string | null;
  benchmark_title: string | null;
  benchmark_status: string | null;
  source_code: string | null;
  change_event: string | null;
  proposed_kind: string;
  source_rationale: string;
  emergence_score: string;
  required_roles: CandidateRole[];
  role_status: Record<string, { decision: string; reviewer: string } | null>;
  created_by: string;
  created_at: string;
  decided_at: string | null;
  reviews: CandidateReviewInfo[];
}

export function listBenchmarkCandidates(status: 'open' | 'all' | CandidateStatus = 'open') {
  return api.get<BenchmarkCandidateInfo[]>('/benchmarks/benchmark-candidates', { params: { status } });
}

export function createBenchmarkCandidate(body: {
  candidate_type: string; title: string; source_rationale: string; benchmark_code?: string; source_code?: string;
}) {
  return api.post<BenchmarkCandidateInfo>('/benchmarks/benchmark-candidates', body);
}

export function benchmarkCandidateAction(id: string, action: 'submit' | 'open-revision') {
  return api.post<BenchmarkCandidateInfo>(`/benchmarks/benchmark-candidates/${id}/${action}`);
}

export function reviewBenchmarkCandidate(id: string, body: { reviewer_role: CandidateRole; decision: string; notes: string }) {
  return api.post<BenchmarkCandidateInfo>(`/benchmarks/benchmark-candidates/${id}/review`, body);
}

export function proposeFromEvent(eventId: string) {
  return api.post<BenchmarkCandidateInfo>(`/benchmarks/watcher/events/${eventId}/propose`);
}
