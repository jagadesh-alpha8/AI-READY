import { http } from './http';
import type { Recommendation } from '../types/api';

export const listRecommendations = (sprintId: string) => http.get<Recommendation[]>(`/sprints/${sprintId}/recommendations`);
/** Idempotent: never duplicates a recommendation already raised for the same gap / fact / pillar. */
export const generateRecommendations = (sprintId: string) =>
  http.post<Recommendation[]>(`/sprints/${sprintId}/recommendations/generate`);
export const getRecommendation = (id: string) => http.get<Recommendation>(`/recommendations/${id}`);
/** InGage staff only: edit, accept, hide or complete. Editing a draft moves it to `edited`. */
export const updateRecommendation = (id: string, body: Partial<Pick<Recommendation,
  'title' | 'description' | 'priority' | 'timeline' | 'expected_cri_lift' | 'status'>> & { support_offering?: string; consultant_notes?: string }) =>
  http.patch<Recommendation>(`/recommendations/${id}`, body);
