import api from './client';
import type { EvidenceAssignee, EvidenceRequest, EvidenceRequestDetail, Fact } from '../types';

export interface EvidenceRequestFilters {
  status?: string;
  unresolved?: boolean;
  overdue?: boolean;
  assigned_to?: 'me' | 'none' | string;
  sprint?: string;
}

function query(filters: EvidenceRequestFilters) {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export function listEvidenceRequests(filters: EvidenceRequestFilters = {}) {
  return api.get<EvidenceRequest[]>(`/evidence-requests${query(filters)}`);
}

export function getEvidenceRequestSummary() {
  return api.get<{ assigned_to_me: number; assigned_to_me_overdue: number; awaiting_my_review: number }>(
    '/evidence-requests/summary',
  );
}

export function getEvidenceRequest(id: string) {
  return api.get<EvidenceRequestDetail>(`/evidence-requests/${id}`);
}

export function listEvidenceAssignees(sprintId: string) {
  return api.get<EvidenceAssignee[]>(`/sprints/${sprintId}/evidence-requests/assignees`);
}

export function createEvidenceRequest(
  factId: string,
  body: { evidence_needed: string; reason: string; assigned_to?: string | null; due_date?: string | null },
) {
  return api.post<Fact>(`/facts/${factId}/request-evidence`, body);
}

export function assignEvidenceRequest(id: string, assignedTo: string, note = '') {
  return api.post<EvidenceRequestDetail>(`/evidence-requests/${id}/assign`, { assigned_to: assignedTo, note });
}

export function commentOnEvidenceRequest(id: string, note: string) {
  return api.post<EvidenceRequestDetail>(`/evidence-requests/${id}/comment`, { note });
}

export function submitEvidence(
  id: string,
  body: { file?: File | null; document_id?: string; source_page?: string; source_snippet?: string; note?: string;
    submitted_text?: string; source_context?: string },
) {
  const form = new FormData();
  if (body.file) form.append('file', body.file);
  if (body.document_id) form.append('document_id', body.document_id);
  if (body.submitted_text) form.append('submitted_text', body.submitted_text);
  if (body.source_context) form.append('source_context', body.source_context);
  form.append('source_page', body.source_page || '');
  form.append('source_snippet', body.source_snippet || '');
  form.append('note', body.note || '');
  return api.post<EvidenceRequestDetail>(`/evidence-requests/${id}/submit`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export type EvidenceDecision = 'accept' | 'accept_corrected' | 'return' | 'reject' | 'withdraw';

export function reviewEvidenceRequest(
  id: string,
  body: { decision: EvidenceDecision; evidence_id?: string; reason?: string; corrected_value?: unknown;
    source_page?: string; source_snippet?: string },
) {
  return api.post<EvidenceRequestDetail>(`/evidence-requests/${id}/review`, body);
}

/**
 * Retry a FAILED AI assessment of one submission (reviewers only, never the submitter): the same evidence is
 * assessed again from its saved text -- nothing is re-uploaded or re-extracted, and the result stays advisory.
 * 409 (with the current detail) when an assessment of it is already running.
 */
export function retryEvidenceAssessment(id: string, evidenceId: string) {
  return api.post<EvidenceRequestDetail>(`/evidence-requests/${id}/evidence/${evidenceId}/retry-assessment`);
}
