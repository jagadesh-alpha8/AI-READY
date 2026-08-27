import api from './client';
import type { SprintDocument } from '../types';

export function listSprintDocuments(sprintId: string) {
  return api.get<SprintDocument[]>(`/sprints/${sprintId}/documents`);
}

export function uploadDocument(
  sprintId: string,
  file: File,
  documentType: string,
  ownerRole: string,
) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', documentType);
  formData.append('owner_role', ownerRole);
  return api.post<SprintDocument>(`/sprints/${sprintId}/upload-file`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export function deleteDocument(id: string) {
  return api.delete<void>(`/documents/${id}`);
}
