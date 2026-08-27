import api from './client';
import type { CreateSprintPayload, Sprint, SprintOverview } from '../types';

export function listSprints() {
  return api.get<Sprint[]>('/sprints');
}

export function deleteSprint(id: string) {
  return api.delete<void>(`/sprints/${id}`);
}

export function archiveSprint(id: string) {
  return api.patch<Sprint>(`/sprints/${id}`, { status: 'archived' });
}

export function createSprint(payload: CreateSprintPayload) {
  return api.post<Sprint>('/sprints', payload);
}

export function getSprint(id: string) {
  return api.get<Sprint>(`/sprints/${id}`);
}

export function getSprintOverview(id: string) {
  return api.get<SprintOverview>(`/sprints/${id}/overview`);
}
