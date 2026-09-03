import api from './client';
import type {
  CreateInstitutionPayload,
  Department,
  DepartmentPayload,
  Institution,
  InstitutionDetail,
  InstitutionLeader,
  InstitutionLeaderPayload,
  InstitutionSystem,
  InstitutionSystemPayload,
  UpdateInstitutionPayload,
} from '../types';

export function listInstitutions() {
  return api.get<Institution[]>('/institutions');
}

export function createInstitution(payload: CreateInstitutionPayload) {
  return api.post<Institution>('/institutions', payload);
}

/** The single-record read — the only one that carries leaders and the derived counts. */
export function getInstitution(id: string) {
  return api.get<InstitutionDetail>(`/institutions/${id}`);
}

export function updateInstitution(id: string, payload: UpdateInstitutionPayload) {
  return api.patch<InstitutionDetail>(`/institutions/${id}`, payload);
}

// --- Institution DNA sub-resources -----------------------------------------
// All nested under their institution, which is what scopes and authorizes them.

export function listDepartments(institutionId: string) {
  return api.get<Department[]>(`/institutions/${institutionId}/departments`);
}

export function createDepartment(institutionId: string, payload: DepartmentPayload) {
  return api.post<Department>(`/institutions/${institutionId}/departments`, payload);
}

export function updateDepartment(institutionId: string, id: string, payload: DepartmentPayload) {
  return api.patch<Department>(`/institutions/${institutionId}/departments/${id}`, payload);
}

export function deleteDepartment(institutionId: string, id: string) {
  return api.delete(`/institutions/${institutionId}/departments/${id}`);
}

export function listSystems(institutionId: string) {
  return api.get<InstitutionSystem[]>(`/institutions/${institutionId}/systems`);
}

export function createSystem(institutionId: string, payload: InstitutionSystemPayload) {
  return api.post<InstitutionSystem>(`/institutions/${institutionId}/systems`, payload);
}

export function updateSystem(institutionId: string, id: string, payload: InstitutionSystemPayload) {
  return api.patch<InstitutionSystem>(`/institutions/${institutionId}/systems/${id}`, payload);
}

export function deleteSystem(institutionId: string, id: string) {
  return api.delete(`/institutions/${institutionId}/systems/${id}`);
}

export function createLeader(institutionId: string, payload: InstitutionLeaderPayload) {
  return api.post<InstitutionLeader>(`/institutions/${institutionId}/leaders`, payload);
}

export function deleteLeader(institutionId: string, id: string) {
  return api.delete(`/institutions/${institutionId}/leaders/${id}`);
}
