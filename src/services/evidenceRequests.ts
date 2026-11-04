import { http } from './http';
import type { EvidenceRequest, EvidenceRequestSummary } from '../types/api';
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
export const getEvidenceRequestSummary = () => http.get<EvidenceRequestSummary>('/evidence-requests/summary');

/** Respond to a request with a file and/or text (the assignee). */
export function submitEvidence(id: string, body: { file?: File | null; submitted_text?: string; note?: string }) {
  const form = new FormData();
  if (body.file) form.append('file', body.file);
  if (body.submitted_text) form.append('submitted_text', body.submitted_text);
  form.append('source_page', '');
  form.append('source_snippet', '');
  form.append('note', body.note || '');
  return http.post(`/evidence-requests/${id}/submit`, form);
}
