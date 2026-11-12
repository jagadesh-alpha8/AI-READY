import { http } from './http';
import type { DashboardData, ProcessingSummary, Sprint, SprintOverview, WorkSummary } from '../types/api';
import type { PlatformAIUsage, SprintAIUsage } from '../types/workflow';
import { cleanParams } from '../utils/params';

export const listSprints = () => http.get<Sprint[]>('/sprints');
export const getSprint = (id: string) => http.get<Sprint>(`/sprints/${id}`);
export const getSprintOverview = (id: string) => http.get<SprintOverview>(`/sprints/${id}/overview`);
/** A new sprint always starts in `draft` (CanManageSprint). */
export const createSprint = (payload: {
  institution_id: string; name?: string; academic_year?: string; description?: string;
  start_date?: string | null; target_completion_date?: string | null;
}) => http.post<Sprint>('/sprints', payload);
/** Dates, description, or a status transition (the server validates the pipeline order). */
export const updateSprint = (id: string, payload: Partial<Pick<Sprint,
  'name' | 'description' | 'academic_year' | 'start_date' | 'target_completion_date' | 'status'>>) =>
  http.patch<Sprint>(`/sprints/${id}`, payload);
/** Archive: reachable from any non-terminal status. */
export const archiveSprint = (id: string) => http.patch<Sprint>(`/sprints/${id}`, { status: 'archived' });
/** Delete: only a draft or archived sprint (the server refuses others). */
export const deleteSprint = (id: string) => http.delete(`/sprints/${id}`);
export const getProcessingSummary = (id: string) => http.get<ProcessingSummary>(`/sprints/${id}/processing-summary`);
export const getWorkSummary = (id: string) => http.get<WorkSummary>(`/sprints/${id}/work-summary`);
export const getDashboard = () => http.get<DashboardData>('/dashboard');

/** AI tokens and cost for one sprint. */
export const getSprintAIUsage = (id: string) => http.get<SprintAIUsage>(`/sprints/${id}/ai-usage`);
/** InGage staff: AI usage across colleges, per institution × sprint × month. */
export const getPlatformAIUsage = (params: { since?: string; until?: string; institution?: string } = {}) =>
  http.get<PlatformAIUsage>('/extraction-jobs/usage-report', { params: cleanParams(params) });
