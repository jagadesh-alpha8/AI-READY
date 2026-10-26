import api from './client';
import type { Baseline, SprintBaseline } from '../types';

export function getBaseline(sprintId: string) {
  return api.get<SprintBaseline>(`/sprints/${sprintId}/baseline`);
}

/**
 * Approve exactly the calculation the reviewer saw (`scoringRunId` = baseline.scoring_run_id on screen).
 * If the data changed since, the server decides nothing and answers 409 with the new preview
 * (BaselineChangedResponse). `processingOverrideReason`: required when documents are not fully processed.
 */
export function approveBaseline(sprintId: string, scoringRunId: string, comments: string, processingOverrideReason = '') {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve`,
    { comments, processing_override_reason: processingOverrideReason, scoring_run_id: scoringRunId });
}

export function approveBaselineProvisional(sprintId: string, scoringRunId: string, comments: string,
  processingOverrideReason = '') {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/approve-provisional`,
    { comments, processing_override_reason: processingOverrideReason, scoring_run_id: scoringRunId });
}

export function returnBaseline(sprintId: string, comments: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/return`, { comments });
}

/** Open a new pending baseline cycle on the current data that may replace the decided one (reason required). */
export function reviseBaseline(sprintId: string, reason: string) {
  return api.post<Baseline>(`/sprints/${sprintId}/baseline/revise`, { comments: reason });
}
