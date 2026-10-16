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

/** Settle a document's category: a checklist slug, or null for "not a checklist document". */
export function confirmDocumentCategory(id: string, category: string | null) {
  return api.post<SprintDocument>(`/documents/${id}/confirm-category`, { category });
}
