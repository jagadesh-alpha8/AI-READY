import api from './client';
import type { Baseline, SprintBaseline } from '../types';

export function getBaseline(sprintId: string) {
  return api.get<SprintBaseline>(`/sprints/${sprintId}/baseline`);
}

export function approveBaseline(sprintId: string, comments: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve`, { comments });
}

export function approveBaselineProvisional(sprintId: string, comments: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve-provisional`, { comments });
}

export function returnBaseline(sprintId: string, comments: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/return`, { comments });
}
