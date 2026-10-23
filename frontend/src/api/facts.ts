import api from './client';
import type { Fact } from '../types';

export function listSprintFacts(sprintId: string) {
  return api.get<Fact[]>(`/sprints/${sprintId}/facts`);
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
