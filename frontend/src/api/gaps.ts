import api from './client';
import type { Gap, WorkSummary } from '../types';
import { cleanParams, fetchAllPages, type Page } from './pagination';

/** Server-side filters of the sprint gaps list (backend apps/gaps/filters.py). '' = any. */
export interface GapQuery {
  page?: number;
  page_size?: number;
  q?: string;
  gap_type?: string;
  priority?: string;
  status?: string;
  owner_role?: string;
  source_document?: string;
  ordering?: string;
}

/** One page of the sprint's gaps (50 by default, at most 100), filtered on the server. */
export function listSprintGapsPage(sprintId: string, query: GapQuery = {}) {
  return api.get<Page<Gap>>(`/sprints/${sprintId}/gaps`, { params: cleanParams({ ...query }) });
}

/** Every gap of the sprint (fetched a page at a time) -- only for screens that need them all. */
export function listSprintGaps(sprintId: string, query: GapQuery = {}) {
  return fetchAllPages<Gap>(`/sprints/${sprintId}/gaps`, { ...query });
}

/** Counts per filter value over the whole sprint -- for filter options and totals. */
export interface GapFacets {
  total: number;
  open: number;
  gap_type: Record<string, number>;
  priority: Record<string, number>;
  status: Record<string, number>;
  owner_role: Record<string, number>;
  source_document: Record<string, number>;
}

export function getSprintGapFacets(sprintId: string) {
  return api.get<GapFacets>(`/sprints/${sprintId}/gaps/facets`);
}

export function resolveGap(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/resolve`, { value });
}

export function markGapUnavailable(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/mark-unavailable`, { value });
}

export function skipGap(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/skip`, { value });
}

export function getGap(id: string) {
  return api.get<Gap>(`/gaps/${id}`);
}

/** Coordinators assign / reassign (or unassign, with null) a gap to someone who may settle it. */
export function assignGap(id: string, body: { assigned_to: string | null; due_date?: string | null; note?: string }) {
  return api.post<Gap>(`/gaps/${id}/assign`, body);
}

/** Outstanding confirmation work for the whole sprint, by role and by assignee, and its readiness. */
export function getWorkSummary(sprintId: string) {
  return api.get<WorkSummary>(`/sprints/${sprintId}/work-summary`);
}

/** Upload evidence from a Missing Document / Low Confidence gap: stored and processed in the gap's sprint. */
export function uploadGapEvidence(gapId: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return api.post<{ gap: Gap; document_id: string; reused: boolean }>(`/gaps/${gapId}/upload-evidence`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

/** Settle a conflict: confirm the chosen fact's value, reject the competing ones, close the conflict
 * (owner role or Super Admin only; backend gaps/services.choose_conflict_value). */
export function chooseConflictValue(gapId: string, factId: string, reason = '') {
  return api.post<Gap>(`/gaps/${gapId}/choose-value`, { fact_id: factId, reason });
}
