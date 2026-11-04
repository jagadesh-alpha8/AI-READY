import { http, saveBlob } from './http';
import type { ExtractionJob, SprintDocument } from '../types/api';

export const listSprintDocuments = (sprintId: string) => http.get<SprintDocument[]>(`/sprints/${sprintId}/documents`);

export function uploadDocument(sprintId: string, file: File, documentType: string, title = '') {
  const form = new FormData();
  form.append('file', file);
  form.append('document_type', documentType);
  if (title) form.append('title', title);
  return http.post<SprintDocument>(`/sprints/${sprintId}/upload-file`, form);
}

export async function downloadDocument(id: string, filename: string) {
  const res = await http.get<Blob>(`/documents/${id}/download`, { responseType: 'blob' });
  saveBlob(res.data, filename);
}

export const listExtractionJobs = (sprintId: string) => http.get<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`);
/** No ids: every eligible (uploaded / failed) document of the sprint. */
export const startExtraction = (sprintId: string, documentIds?: string[]) =>
  http.post<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`,
    documentIds && documentIds.length ? { document_ids: documentIds } : undefined);
export const cancelSprintExtraction = (sprintId: string) =>
  http.post<{ cancelled_count: number }>(`/extraction-jobs/sprints/${sprintId}/cancel`);
