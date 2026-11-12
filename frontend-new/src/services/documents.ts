import { http, saveBlob } from './http';
import type { ExtractionJob, SprintDocument } from '../types/api';
import type { DriveImportJob } from '../types/workflow';

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

/** Deletes the record and its stored file (uploader, or a quality lead for anyone's document). */
export const deleteDocument = (id: string) => http.delete(`/documents/${id}`);
export const updateDocument = (id: string, body: { title?: string; document_type?: string }) =>
  http.patch<SprintDocument>(`/documents/${id}`, body);
/** A person settles the AI category: a checklist slug, or null for "not a checklist document". */
export const confirmDocumentCategory = (id: string, category: string | null) =>
  http.post<SprintDocument>(`/documents/${id}/confirm-category`, { category });

// --- Google Drive import (public link-shared folder) ---
export const listDriveImports = (sprintId: string) => http.get<DriveImportJob[]>(`/sprints/${sprintId}/drive-import-jobs`);
export const startDriveImport = (sprintId: string, driveUrl: string) =>
  http.post<DriveImportJob>(`/sprints/${sprintId}/drive-import-jobs`, { drive_url: driveUrl });
export const stopDriveImport = (sprintId: string, jobId: string) =>
  http.post<DriveImportJob>(`/sprints/${sprintId}/drive-import-jobs/${jobId}/stop`);

// --- extraction ---
export const listExtractionJobs = (sprintId: string) => http.get<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`);
/** No ids: every eligible (uploaded / failed) document of the sprint. */
export const startExtraction = (sprintId: string, documentIds?: string[]) =>
  http.post<ExtractionJob[]>(`/sprints/${sprintId}/extraction-jobs`,
    documentIds && documentIds.length ? { document_ids: documentIds } : undefined);
export const cancelSprintExtraction = (sprintId: string) =>
  http.post<{ cancelled_count: number }>(`/extraction-jobs/sprints/${sprintId}/cancel`);
/** Re-run every document of the sprint that is not completed. */
export const processIncomplete = (sprintId: string) =>
  http.post<ExtractionJob[]>(`/extraction-jobs/sprints/${sprintId}/process-incomplete`);
export const getExtractionJob = (id: string) => http.get<ExtractionJob>(`/extraction-jobs/${id}`);
export const cancelExtractionJob = (id: string) => http.post<ExtractionJob>(`/extraction-jobs/${id}/cancel`);
/** Run a failed or stopped job again, as the same row. */
export const processExtractionJob = (id: string) => http.post<ExtractionJob>(`/extraction-jobs/${id}/process`);
export const deleteExtractionJob = (id: string) => http.delete(`/extraction-jobs/${id}`);
