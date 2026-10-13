import api from './client';
import type { ExtractionJob, PlatformAIUsage, SprintAIUsage } from '../types';

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

/** Stop one queued/running job (per-row Stop). */
export function cancelExtractionJob(jobId: string) {
  return api.post<ExtractionJob>(`/extraction-jobs/${jobId}/cancel`);
}

/** Run a failed/stopped job again, as the same row (per-row Process). */
export function processExtractionJob(jobId: string) {
  return api.post<ExtractionJob>(`/extraction-jobs/${jobId}/process`);
}

/** Run every not-completed document in the sprint again. */
export function processIncompleteExtraction(sprintId: string) {
  return api.post<ExtractionJob[]>(`/extraction-jobs/sprints/${sprintId}/process-incomplete`);
}

export function deleteExtractionJob(jobId: string) {
  return api.delete<void>(`/extraction-jobs/${jobId}`);
}


/** AI tokens and cost for the sprint (totals, by stage, by model, top documents). */
export function getSprintAIUsage(sprintId: string) {
  return api.get<SprintAIUsage>(`/sprints/${sprintId}/ai-usage`);
}

/** Admin only: AI tokens and cost across all colleges, per college x sprint x month. */
export function getPlatformAIUsage(params: { since?: string; until?: string; institution?: string } = {}) {
  return api.get<PlatformAIUsage>('/extraction-jobs/usage-report', { params });
}
