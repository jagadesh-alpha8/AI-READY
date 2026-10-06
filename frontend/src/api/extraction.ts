import api from './client';
import type { ExtractionJob } from '../types';

export function listExtractionJobs(sprintId: string) {
  return api.get<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`);
}

/** No ids: every eligible document in the sprint. Ids: only those documents. */
export function startExtraction(sprintId: string, documentIds?: string[]) {
  return api.post<ExtractionJob[]>(
    `/sprints/${sprintId}/extraction-jobs`,
    documentIds && documentIds.length > 0 ? { document_ids: documentIds } : undefined,
  );
}

export function cancelSprintExtraction(sprintId: string) {
  return api.post<{ cancelled_count: number }>(`/extraction-jobs/sprints/${sprintId}/cancel`);
}

export function deleteExtractionJob(jobId: string) {
  return api.delete<void>(`/extraction-jobs/${jobId}`);
}

