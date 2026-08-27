import api from './client';
import type { Scorecard } from '../types';

export function getScore(sprintId: string) {
  return api.get<Scorecard>(`/sprints/${sprintId}/score`);
}

export function recalculateScore(sprintId: string) {
  return api.post<Scorecard>(`/sprints/${sprintId}/score`);
}
