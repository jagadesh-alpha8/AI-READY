import { http } from './http';
import type {
  CollegeProfile, Cycle, CycleDetail, ImprovementPlan, PlanInitiative, PlanStatus, PlanTask,
} from '../types/api';

/** Benchmark assessments of a college against the published release (backend apps/assessments). */
const base = '/assessments';

export const listCycles = (institution?: string) =>
  http.get<Cycle[]>(`${base}/cycles`, { params: institution ? { institution } : {} });
export const getCycle = (id: string) => http.get<CycleDetail>(`${base}/cycles/${id}`);
/** A new cycle freezes the current published release and the college profile (InGage staff). */
export const createCycle = (body: { institution: string; name: string; opens_on?: string; closes_on?: string }) =>
  http.post<CycleDetail>(`${base}/cycles`, body);
export const getCollegeProfile = (institutionId: string) =>
  http.get<CollegeProfile>(`${base}/institutions/${institutionId}/profile`);

export const getPlan = (cycleId: string) => http.get<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
/** Staff, finalized cycles only: gaps -> initiatives -> tasks. */
export const generatePlan = (cycleId: string) => http.post<ImprovementPlan>(`${base}/cycles/${cycleId}/plan`);
export const updateInitiative = (id: string, body: Partial<Pick<PlanInitiative, 'title' | 'owner' | 'status' | 'target_date'>>) =>
  http.patch<PlanInitiative>(`${base}/initiatives/${id}`, body);
export const addTask = (initiativeId: string, body: { title: string; owner?: string; due_date?: string }) =>
  http.post<PlanInitiative>(`${base}/initiatives/${initiativeId}/tasks`, body);
export const updateTask = (id: string, body: { title?: string; owner?: string; status?: PlanStatus; due_date?: string | null }) =>
  http.patch<PlanTask>(`${base}/tasks/${id}`, body);
