import api from './client';
import type { Fact } from '../types';
import { cleanParams, fetchAllPages, type Page } from './pagination';

/** Server-side filters of the sprint facts list (backend apps/facts/filters.py). '' = any. */
export interface FactQuery {
  page?: number;
  page_size?: number;
  q?: string;
  status?: string;
  pillar?: string;
  fact_kind?: string;          // 'ai_evidence' | 'context' | 'profile' | 'none'
  aiqif_criterion?: string;
  aiqif_mapping_status?: string;
  owner_role?: string;
  source_document?: string;    // file name
  confidence_band?: string;    // 'high' | 'medium' | 'low'
  document?: string;
  /** Facts with a tag confirmed / rejected / pending an expert decision. */
  tag_review?: string;
  ordering?: string;
}

/** One page of the sprint's facts (50 by default, at most 100), filtered on the server. */
export function listSprintFactsPage(sprintId: string, query: FactQuery = {}) {
  return api.get<Page<Fact>>(`/sprints/${sprintId}/facts`, { params: cleanParams({ ...query }) });
}

/** Every fact of the sprint (fetched a page at a time) -- only for screens that need them all. */
export function listSprintFacts(sprintId: string, query: FactQuery = {}) {
  return fetchAllPages<Fact>(`/sprints/${sprintId}/facts`, { ...query });
}

/** Counts per filter value over the whole sprint (database aggregates) -- for filter options and totals. */
export interface FactFacets {
  total: number;
  status: Record<string, number>;
  pillar: Record<string, number>;
  fact_kind: Record<string, number>;
  aiqif_mapping_status: Record<string, number>;
  owner_role: Record<string, number>;
  source_document: Record<string, number>;
  confidence_band: Record<string, number>;
  aiqif_criterion: { criterion: string; code: string; name: string; count: number }[];
  by_document: Record<string, number>;
  /** Facts with a tag in each review state (the "Tag review" filter). */
  tag_review: { confirmed: number; rejected: number; pending: number };
  indicators: { code: string; criterion: string; name: string }[];
}

export function getSprintFactFacets(sprintId: string) {
  return api.get<FactFacets>(`/sprints/${sprintId}/facts/facets`);
}

export function getFact(id: string) {
  return api.get<Fact>(`/facts/${id}`);
}

export function confirmFact(id: string, comment = 'Confirmed by reviewer') {
  return api.post<Fact>(`/facts/${id}/confirm`, { comment });
}

export interface BulkFactConfirmResult {
  requested_count: number;
  confirmed: string[];
  confirmed_count: number;
  skipped: Array<{ id: string; reason: string }>;
  skipped_count: number;
}

/** Confirm up to 100 facts in one sprint while preserving backend ownership checks and per-fact audit history. */
export function bulkConfirmSprintFacts(sprintId: string, factIds: string[], comment = '') {
  return api.post<BulkFactConfirmResult>(`/sprints/${sprintId}/facts/bulk-confirm`, {
    fact_ids: factIds,
    comment,
  });
}

export function correctFact(id: string, correctedValue: unknown, comment = 'User correction') {
  return api.post<Fact>(`/facts/${id}/correct`, { corrected_value: correctedValue, comment });
}

export function rejectFact(id: string, comment = 'Rejected by reviewer') {
  return api.post<Fact>(`/facts/${id}/reject`, { comment });
}

/** A reviewer's decision on one AI-QIF tag of a fact (counts toward evidence coverage at the next recalculation). */
export function reviewFactMapping(id: string, indicatorCode: string, decision: 'confirm' | 'reject', note = '') {
  return api.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/review`, { decision, note });
}

/** Coordinators assign / reassign (or unassign, with null) a fact to someone who may act on it. */
export function assignFact(id: string, body: { assigned_to: string | null; due_date?: string | null; note?: string }) {
  return api.post<Fact>(`/facts/${id}/assign`, body);
}

export interface BulkTagSummary {
  pending_count: number;
  eligible_count: number;
  low_confidence_count: number;
  low_confidence_threshold: number;
  confidence_min: number | null;
  confidence_max: number | null;
  facts_count: number;
}

export interface BulkTagResult {
  confirmed_count: number;
  already_decided_count: number;
  still_pending_count: number;
  still_pending: { id: string; fact_id: string; indicator_code: string; reason: string }[];
  coverage: { raw_cri: number; coverage_adjusted_cri: number | null; covered_count: number | null;
    applicable_count: number | null; ratio: number | null } | null;
}

/** Confirm pending AI-QIF tag mappings (never the facts). dryRun returns the summary only. */
export function bulkConfirmSprintTags(sprintId: string, mappingIds: string[] | undefined, dryRun: boolean, note = '') {
  return api.post<BulkTagSummary | BulkTagResult>(`/sprints/${sprintId}/aiqif-mappings/bulk-confirm`, {
    ...(mappingIds ? { mapping_ids: mappingIds } : {}), dry_run: dryRun, note,
  });
}

/** The sales view of AI-QIF tagging: fact kinds and the expert queue size (no indicator codes). */
export interface AIQIFSummary {
  facts: number;
  ai_evidence: number;
  context: number;
  profile: number;
  not_classified: number;
  expert_queue: { tags: number; facts: number; total: number };
  coverage_provisional: boolean;
}

export function getAIQIFSummary(sprintId: string) {
  return api.get<AIQIFSummary>(`/sprints/${sprintId}/aiqif-summary`);
}

/** Super Admin: the facts and tags waiting for an AI-QIF expert, and the indicator list for adding a tag. */
export interface AIQIFExpertQueue {
  count: number;
  facts: Fact[];
  indicators: { code: string; criterion: string; name: string }[];
}

export function getAIQIFExpertQueue(sprintId: string) {
  return api.get<AIQIFExpertQueue>(`/sprints/${sprintId}/aiqif-expert-queue`);
}

export function addFactMapping(id: string, indicatorCode: string, relationship: 'direct' | 'supporting' | 'contextual',
  note = '') {
  return api.post<Fact>(`/facts/${id}/aiqif-mappings`, { indicator_code: indicatorCode, relationship, note });
}

export function decideFactKind(id: string, factKind: 'ai_evidence' | 'context' | 'profile', note = '') {
  return api.post<Fact>(`/facts/${id}/fact-kind`, { fact_kind: factKind, note });
}

/** The benchmark profile as read from the sprint's documents (backend apps/facts/profile_suggestion.py). */
export interface ProfileSource { fact_id: string; value: unknown; field_name: string; document: string; page: string }
export interface ProfileSuggestion {
  institution: string;
  institution_name: string;
  current: ProfileValues | null;
  suggested: {
    institution_type: { value: string; conflict: boolean; candidates: { code: string; sources: ProfileSource[] }[] };
    autonomous_status: { value: string; conflict: boolean; candidates: { code: string; sources: ProfileSource[] }[] };
    approval_bodies: string[];
    programmes: { name: string; programme_type: string; approval_body: string; sources: ProfileSource[] }[];
  };
  unmatched: (ProfileSource & { profile_field: string })[];
  options: {
    institution_types: { code: string; name: string }[];
    autonomous_statuses: { code: string; name: string }[];
    approval_bodies: string[];
    programme_types: { code: string; name: string }[];
  };
}
export interface ProfileValues {
  institution_type: string;
  autonomous_status: string;
  approval_bodies: string[];
  programmes: { name: string; programme_type: string; approval_body: string }[];
}

export function getProfileSuggestion(sprintId: string) {
  return api.get<ProfileSuggestion>(`/sprints/${sprintId}/profile-suggestion`);
}

export function confirmProfile(sprintId: string, values: ProfileValues) {
  return api.post<ProfileSuggestion>(`/sprints/${sprintId}/profile-suggestion`, values);
}

/** Super Admin: change a tag's indicator / relationship / note. A new indicator or relationship waits for a
 * decision unless `decision` is given now (backend aiqif_tagging.edit_tag). */
export function editFactMapping(id: string, indicatorCode: string, body: {
  indicator_code?: string; relationship?: 'direct' | 'supporting' | 'contextual'; note?: string;
  decision?: 'confirm' | 'reject';
}) {
  return api.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/edit`, body);
}

/** Super Admin: send a decided tag back to the expert queue; the earlier decision stays in the history. */
export function reopenFactMapping(id: string, indicatorCode: string, reason: string) {
  return api.post<Fact>(`/facts/${id}/aiqif-mappings/${indicatorCode}/reopen`, { reason });
}
