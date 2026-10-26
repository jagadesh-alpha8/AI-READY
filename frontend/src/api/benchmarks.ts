import api from './client';

/**
 * Benchmark Studio API, read-only: the manager-provided standard catalogue (sources, indicators with their levels,
 * origin and source mappings, applicability from a college's saved profile). The server refuses every change to
 * this master data (backend apps/benchmarks/permissions.py); it changes only through the controlled workbook import.
 */

export interface SourceVersion {
  id: string;
  version_label: string;
  status: 'draft' | 'active' | 'superseded' | 'withdrawn';
  issued_on: string | null;
  effective_from: string | null;
  collection_status: string;
  collection_status_label: string;
  reported_status: string;
  notes: string;
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
  /** Indicators this source supports through linked requirements (backend services/provenance.py). */
  linked_indicators: LinkedIndicator[];
  /** Why it cannot be deleted (backend services/source_edit.py); [] = it can. */
  delete_blockers: string[];
}

export interface LinkedIndicator {
  benchmark_code: string;
  title: string;
  status: string;
  links: { requirement_code: string; relationship: LinkRelationship }[];
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

export interface MaturityLevel {
  level: 'L3' | 'L2' | 'L1';
  level_label: string;
  definition: string;
  measurement_rule: string;
  is_placeholder: boolean;
  /** Model name when AI drafted it (needs a reviewer's confirmation); empty = a person. */
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
  /** framework_import / candidate / manual, or '' when none is stored (see getProvenance for the full origin). */
  origin_type: '' | OriginType;
  origin_type_label: string;
  /** Drafts only (null state once published / withdrawn). Separate from publishing. */
  confirmation: {
    state: 'confirmed' | 'changed' | 'none' | null;
    confirmed_by: string | null;
    confirmed_at: string | null;
  };
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

export type LinkRelationship = 'primary' | 'supporting' | 'crosswalk';

export type OriginType = 'framework_import' | 'candidate' | 'manual';

/** How the indicator entered the library -- not the documents that support it (those are source references). */
export interface IndicatorOrigin {
  type: '' | OriginType;
  label: string;
  /** 'row' stored on the indicator, 'audit' read from its import event, 'candidate', or '' (not recorded). */
  recorded: string;
  // framework_import
  workbook?: string;
  framework?: string | null;
  framework_version?: string;
  sheet?: string | null;
  row?: number | null;
  indicator_code?: string;
  imported_at?: string;
  imported_by?: string;
  workbook_source_refs?: {
    sheet: string; row: number; source_code: string; source_version: string; page: number | null;
    source_quote: string; relationship: LinkRelationship; status: string;
  }[];
  // candidate
  candidate_id?: string;
  candidate_title?: string;
  source_code?: string | null;
  // manual
  description?: string;
  reference?: string;
  entered_by?: string;
  entered_at?: string;
}

export interface SourceReferenceRow {
  requirement_code: string;
  statement: string;
  kind?: string;
  source_code: string;
  source_title?: string;
  source_version: string;
  source_version_status?: string;
  page: number | null;
  source_quote: string;
  /** true / false against the version's extracted text; null when there is no text to check. */
  quote_in_source_text?: boolean | null;
  relationship: LinkRelationship;
  relationship_label: string;
  note?: string;
  /** manager_workbook: a mapping in the authoritative workbook; the others are earlier reviewed links. */
  requirement_origin?: 'manager_workbook' | 'ai_draft_accepted' | 'entered_by_reviewer';
  workbook_ref?: { workbook: string; workbook_sha256: string; sheet: string; row: number } | null;
  ai_model?: string;
  accepted_by?: string | null;
  accepted_at?: string | null;
  linked_by?: string | null;
  linked_at?: string | null;
}

export interface IndicatorProvenance {
  benchmark_code: string;
  version_label: string | null;
  status: string;
  origin: IndicatorOrigin;
  source_references: SourceReferenceRow[];
  source_document_linked: boolean;
  naac_crosswalk_count: number;
  /** Set when this is the copy frozen in a published / retired release. */
  frozen_in: { release_label: string; status: string; published_at: string | null } | null;
  releases: { release_label: string; status: string; published_at: string | null }[];
}

export function getProvenance(benchmarkCode: string, release?: string) {
  return api.get<IndicatorProvenance>(`/benchmarks/catalogue/${benchmarkCode}/provenance`,
    { params: { release: release || undefined } });
}

export type ApplicabilityResult = 'applies' | 'does_not_apply' | 'optional' | 'requires_review';

export interface ApplicabilityPreview {
  institution: string;
  /** The college's SAVED benchmark profile that was used; null = it has none, and nothing is shown or guessed. */
  profile: { institution_type: string; autonomous_status: string; programme_types: string[];
    approval_bodies: string[]; jurisdiction: string } | null;
  detail?: string;
  counts: Partial<Record<ApplicabilityResult, number>>;
  benchmarks: { benchmark_code: string; title: string; pillar_code: string; result: ApplicabilityResult; reason: string }[];
}

export interface PreviewCollege {
  id: string;
  name: string;
  has_profile: boolean;
}

/** The colleges, and whether each has a saved benchmark profile. */
export function listPreviewColleges() {
  return api.get<PreviewCollege[]>('/benchmarks/applicability/preview');
}

/** Every indicator's applicability for a college, from its saved profile only. */
export function previewApplicability(institutionId: string) {
  return api.get<ApplicabilityPreview>('/benchmarks/applicability/preview', { params: { institution: institutionId } });
}

export interface VersionComparison {
  base: { id: string; version_label: string; status: string; issued_on: string | null } | null;
  note: string;
  file_changed?: boolean;
  same_file?: boolean;
  pages?: { before: number | null; after: number | null };
  added?: string[];
  removed?: string[];
  requirements_on_base?: number;
}

export function compareVersion(versionId: string) {
  return api.get<VersionComparison>(`/benchmarks/versions/${versionId}/compare`);
}
