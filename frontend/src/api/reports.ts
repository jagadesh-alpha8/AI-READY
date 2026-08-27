import api from './client';
import type { Report } from '../types';

export function listReports(sprintId: string) {
  return api.get<Report[]>(`/sprints/${sprintId}/reports`);
}

export function generateReport(sprintId: string) {
  return api.post<Report>(`/sprints/${sprintId}/reports/generate`);
}

export function getReport(id: string) {
  return api.get<Report>(`/reports/${id}`);
}

/**
 * Downloads use the shared, authenticated axios instance (a plain `<a
 * href="/api/v1/...">` wouldn't carry the Bearer token) as a blob, then
 * triggers a normal browser save via an in-memory object URL.
 */
export async function downloadReport(id: string, fileFormat: 'pdf' | 'docx', filename: string) {
  const response = await api.get(`/reports/${id}/download`, {
    params: { file: fileFormat },
    responseType: 'blob',
  });
  const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}
