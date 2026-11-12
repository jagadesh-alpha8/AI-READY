import { http } from './http';
import type { Gap, GapDetail, GapFacets, Page } from '../types/api';
import { cleanParams } from '../utils/params';

export interface GapQuery {
  page?: number;
  page_size?: number;
  gap_type?: string;
  priority?: string;
  status?: string;
  ordering?: string;
}

export const listSprintGapsPage = (sprintId: string, query: GapQuery = {}) =>
  http.get<Page<Gap>>(`/sprints/${sprintId}/gaps`, { params: cleanParams({ page: 1, ...query }) });
export const getSprintGapFacets = (sprintId: string) => http.get<GapFacets>(`/sprints/${sprintId}/gaps/facets`);
/** One gap in full, with its history and (for contradictions) every competing value. */
export const getGap = (id: string) => http.get<GapDetail>(`/gaps/${id}`);
export const resolveGap = (id: string, resolution: string) => http.post<Gap>(`/gaps/${id}/resolve`, { resolution });
export const markGapUnavailable = (id: string, resolution: string) =>
  http.post<Gap>(`/gaps/${id}/mark-unavailable`, { resolution });
export const skipGap = (id: string, resolution: string) => http.post<Gap>(`/gaps/${id}/skip`, { resolution });
/** Coordinators assign (or unassign with null) a gap to someone who may settle it. */
export const assignGap = (id: string, assignedTo: string | null, dueDate?: string | null, note = '') =>
  http.post<Gap>(`/gaps/${id}/assign`, { assigned_to: assignedTo, due_date: dueDate || null, note });
/** Settle a contradiction: confirm the chosen fact's value, reject the competing ones (owner role or Super Admin). */
export const chooseConflictValue = (id: string, factId: string, reason = '') =>
  http.post<Gap>(`/gaps/${id}/choose-value`, { fact_id: factId, reason });
/** Upload evidence for a Missing Document / Low Confidence gap; it is stored and processed in the gap's sprint. */
export function uploadGapEvidence(id: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return http.post<{ gap: Gap; document_id: string; reused: boolean }>(`/gaps/${id}/upload-evidence`, form);
}
