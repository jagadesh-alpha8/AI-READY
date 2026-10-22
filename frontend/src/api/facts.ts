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
