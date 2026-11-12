import { http } from './http';
import type { EvidenceRequest, EvidenceRequestSummary } from '../types/api';
import type { EvidenceAssignee, EvidenceDecision, EvidenceRequestDetail } from '../types/workflow';
import { cleanParams } from '../utils/params';

export interface EvidenceRequestFilters {
  sprint?: string;
  status?: string;
  unresolved?: boolean;
  overdue?: boolean;
  assigned_to?: string;
}

export const listEvidenceRequests = (filters: EvidenceRequestFilters = {}) =>
  http.get<EvidenceRequest[]>('/evidence-requests', {
    params: cleanParams({
      ...filters,
      unresolved: filters.unresolved ? 'true' : undefined,
      overdue: filters.overdue ? 'true' : undefined,
    }),
  });
export const listSprintEvidenceRequests = (sprintId: string) => http.get<EvidenceRequest[]>(`/sprints/${sprintId}/evidence-requests`);
export const getEvidenceRequestSummary = () => http.get<EvidenceRequestSummary>('/evidence-requests/summary');
export const getEvidenceRequest = (id: string) => http.get<EvidenceRequestDetail>(`/evidence-requests/${id}`);
/** People who may be assigned evidence work in this sprint. */
export const listEvidenceAssignees = (sprintId: string) => http.get<EvidenceAssignee[]>(`/sprints/${sprintId}/evidence-requests/assignees`);
export const assignEvidenceRequest = (id: string, assignedTo: string, note = '') =>
  http.post<EvidenceRequestDetail>(`/evidence-requests/${id}/assign`, { assigned_to: assignedTo, note });
export const commentOnEvidenceRequest = (id: string, note: string) =>
  http.post<EvidenceRequestDetail>(`/evidence-requests/${id}/comment`, { note });

/** Respond to a request with a file and/or text (the assignee). */
export function submitEvidence(id: string, body: { file?: File | null; submitted_text?: string; note?: string }) {
  const form = new FormData();
  if (body.file) form.append('file', body.file);
  if (body.submitted_text) form.append('submitted_text', body.submitted_text);
  form.append('source_page', '');
  form.append('source_snippet', '');
  form.append('note', body.note || '');
  return http.post<EvidenceRequestDetail>(`/evidence-requests/${id}/submit`, form);
}

/** A reviewer decides on submitted evidence (never the person who submitted it). */
export const reviewEvidenceRequest = (id: string, body: { decision: EvidenceDecision; evidence_id?: string; reason?: string; corrected_value?: unknown }) =>
  http.post<EvidenceRequestDetail>(`/evidence-requests/${id}/review`, body);
/** Retry a failed AI assessment of one submission; the result stays advisory. */
export const retryEvidenceAssessment = (id: string, evidenceId: string) =>
  http.post<EvidenceRequestDetail>(`/evidence-requests/${id}/evidence/${evidenceId}/retry-assessment`);
