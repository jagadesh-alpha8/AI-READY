import { http } from './http';
import type { DashboardData, ProcessingSummary, Sprint, SprintOverview, WorkSummary } from '../types/api';

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
export const getProcessingSummary = (id: string) => http.get<ProcessingSummary>(`/sprints/${id}/processing-summary`);
export const getWorkSummary = (id: string) => http.get<WorkSummary>(`/sprints/${id}/work-summary`);
export const getDashboard = () => http.get<DashboardData>('/dashboard');
