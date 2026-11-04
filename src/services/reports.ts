import { http, saveBlob } from './http';
import type { Report } from '../types/api';

export const listReports = (sprintId: string) => http.get<Report[]>(`/sprints/${sprintId}/reports`);
/** Asynchronous: answers 202 with a `draft` row; poll the list until it is `ready` or `failed`. */
export const generateReport = (sprintId: string) => http.post<Report>(`/sprints/${sprintId}/reports/generate`);
export async function downloadReport(id: string, format: 'pdf' | 'docx', filename: string) {
  const res = await http.get<Blob>(`/reports/${id}/download`, { params: { file: format }, responseType: 'blob' });
  saveBlob(res.data, filename);
}
