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
