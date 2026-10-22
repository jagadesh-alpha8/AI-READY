import api from './client';
import type { Baseline, SprintBaseline } from '../types';

export function getBaseline(sprintId: string) {
  return api.get<SprintBaseline>(`/sprints/${sprintId}/baseline`);
}

/** `processingOverrideReason`: required by the server when included documents are not fully processed. */
export function approveBaseline(sprintId: string, comments: string, processingOverrideReason = '') {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve`,
    { comments, processing_override_reason: processingOverrideReason });
}

export function approveBaselineProvisional(sprintId: string, comments: string, processingOverrideReason = '') {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve-provisional`,
    { comments, processing_override_reason: processingOverrideReason });
}

export function returnBaseline(sprintId: string, comments: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/return`, { comments });
}
