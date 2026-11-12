import { http } from './http';
import type { Baseline, Page, PillarConfig, ScoreHistoryRow, Scorecard, SprintBaseline } from '../types/api';

/** Computes and stores a first score if the sprint has never been scored. */
export const getScore = (sprintId: string) => http.get<Scorecard>(`/sprints/${sprintId}/score`);
/** A fresh, recorded scoring run from the current verified facts and open gaps (CanManageSprint). */
export const recalculateScore = (sprintId: string) => http.post<Scorecard>(`/sprints/${sprintId}/score`);
export const getScoreHistory = (sprintId: string) =>
  http.get<ScoreHistoryRow[] | Page<ScoreHistoryRow>>(`/sprints/${sprintId}/score/history`);
export const getScoringConfig = () => http.get<PillarConfig[]>('/scoring/config');

/**
 * The baseline decision cycle. Reading it opens a pending baseline (and moves the sprint to baseline review)
 * the first time, so it is only called when someone opens baseline approval, never in passing.
 */
export const getBaseline = (sprintId: string) => http.get<SprintBaseline>(`/sprints/${sprintId}/baseline`);
/**
 * Approve exactly the calculation on screen (`scoringRunId`). If the data changed since, the server decides
 * nothing and answers 409 with the new preview. `processingOverrideReason` is required while documents are
 * not fully processed.
 */
export const approveBaseline = (sprintId: string, scoringRunId: string, comments: string, processingOverrideReason = '') =>
  http.post<Baseline>(`/sprints/${sprintId}/baseline/approve`,
    { comments, processing_override_reason: processingOverrideReason, scoring_run_id: scoringRunId });
export const approveBaselineProvisional = (sprintId: string, scoringRunId: string, comments: string, processingOverrideReason = '') =>
  http.post<Baseline>(`/sprints/${sprintId}/baseline/approve-provisional`,
    { comments, processing_override_reason: processingOverrideReason, scoring_run_id: scoringRunId });
export const returnBaseline = (sprintId: string, comments: string) =>
  http.post<Baseline>(`/sprints/${sprintId}/baseline/return`, { comments });
/** Open a new pending cycle on current data that may replace the decided one (reason required). */
export const reviseBaseline = (sprintId: string, reason: string) =>
  http.post<Baseline>(`/sprints/${sprintId}/baseline/revise`, { comments: reason });
