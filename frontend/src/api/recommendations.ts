import api from './client';
import type { Recommendation, UpdateRecommendationPayload } from '../types';

export function listRecommendations(sprintId: string) {
  return api.get<Recommendation[]>(`/sprints/${sprintId}/recommendations`);
}

export function generateRecommendations(sprintId: string) {
  return api.post<Recommendation[]>(`/sprints/${sprintId}/recommendations/generate`);
}

export function updateRecommendation(id: string, payload: UpdateRecommendationPayload) {
  return api.patch<Recommendation>(`/recommendations/${id}`, payload);
}
