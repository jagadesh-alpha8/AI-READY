import { http } from './http';
import type { Recommendation } from '../types/api';

export const listRecommendations = (sprintId: string) => http.get<Recommendation[]>(`/sprints/${sprintId}/recommendations`);
/** Idempotent: never duplicates a recommendation already raised for the same gap / fact / pillar. */
export const generateRecommendations = (sprintId: string) =>
  http.post<Recommendation[]>(`/sprints/${sprintId}/recommendations/generate`);
