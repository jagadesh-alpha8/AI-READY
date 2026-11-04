import { http } from './http';
import type { Page, PillarConfig, ScoreHistoryRow, Scorecard, SprintBaseline } from '../types/api';

/** Computes and stores a first score if the sprint has never been scored. */
export const getScore = (sprintId: string) => http.get<Scorecard>(`/sprints/${sprintId}/score`);
/** A fresh, recorded scoring run from the current verified facts and open gaps (CanManageSprint). */
export const recalculateScore = (sprintId: string) => http.post<Scorecard>(`/sprints/${sprintId}/score`);
export const getScoreHistory = (sprintId: string) =>
  http.get<ScoreHistoryRow[] | Page<ScoreHistoryRow>>(`/sprints/${sprintId}/score/history`);
export const getScoringConfig = () => http.get<PillarConfig[]>('/scoring/config');
export const getBaseline = (sprintId: string) => http.get<SprintBaseline>(`/sprints/${sprintId}/baseline`);
