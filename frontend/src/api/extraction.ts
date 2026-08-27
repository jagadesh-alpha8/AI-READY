import api from './client';
import type { ExtractionJob } from '../types';

export function listExtractionJobs(sprintId: string) {
  return api.get<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`);
}

export function startExtraction(sprintId: string, documentId?: string) {
  return api.post<ExtractionJob[]>(
    `/sprints/${sprintId}/extraction-jobs`,
    documentId ? { document_id: documentId } : undefined,
  );
}

export function cancelSprintExtraction(sprintId: string) {
  return api.post<{ cancelled_count: number }>(`/extraction-jobs/sprints/${sprintId}/cancel`);
}

export function deleteExtractionJob(jobId: string) {
  return api.delete<void>(`/extraction-jobs/${jobId}`);
}

