import api from './client';
import type { Gap, WorkSummary } from '../types';

export function listSprintGaps(sprintId: string) {
  return api.get<Gap[]>(`/sprints/${sprintId}/gaps`);
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
