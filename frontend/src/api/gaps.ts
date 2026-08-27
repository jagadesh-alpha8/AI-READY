import api from './client';
import type { Gap } from '../types';

export function listSprintGaps(sprintId: string) {
  return api.get<Gap[]>(`/sprints/${sprintId}/gaps`);
}

export function resolveGap(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/resolve`, { value });
}

export function markGapUnavailable(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/mark-unavailable`, { value });
}

export function skipGap(id: string, value: string) {
  return api.post<Gap>(`/gaps/${id}/skip`, { value });
}
