import { http } from './http';
import type {
  CoordinatorStatus, CreateInstitutionPayload, Department, Institution, InstitutionDetail, InstitutionLeader, InstitutionSystem,
} from '../types/api';
import type { DepartmentPayload, InstitutionDeletionPreview, LeaderPayload, SystemPayload } from '../types/workflow';

export const listInstitutions = () => http.get<Institution[]>('/institutions');
export const getInstitution = (id: string) => http.get<InstitutionDetail>(`/institutions/${id}`);
/** Creates the college and invites its IQAC Coordinator by email (InGage staff). */
export const createInstitution = (payload: CreateInstitutionPayload) =>
  http.post<Institution & { invitation_email_sent: boolean }>('/institutions', payload);
export const updateInstitution = (id: string, payload: Partial<Institution> & { affiliation?: string }) =>
  http.patch<InstitutionDetail>(`/institutions/${id}`, payload);

/** What deleting would remove, and whether protected records force an archive instead. */
export const getDeletionPreview = (id: string) => http.get<InstitutionDeletionPreview>(`/institutions/${id}/deletion-preview`);
/** Permanent delete (Super Admin only); refused while protected records exist. */
export const deleteInstitution = (id: string) => http.delete(`/institutions/${id}`);
export const archiveInstitution = (id: string) => http.post<InstitutionDetail>(`/institutions/${id}/archive`);
export const unarchiveInstitution = (id: string) => http.post<InstitutionDetail>(`/institutions/${id}/unarchive`);

export const getCoordinator = (id: string) => http.get<CoordinatorStatus>(`/institutions/${id}/coordinator`);
/** Name or change the coordinator (InGage staff): same email corrects the name, a new email sends a new invitation. */
export const setCoordinator = (id: string, name: string, email: string) =>
  http.post<CoordinatorStatus>(`/institutions/${id}/coordinator`, { coordinator_name: name, coordinator_email: email });
export const resendCoordinatorInvitation = (id: string) =>
  http.post<CoordinatorStatus>(`/institutions/${id}/coordinator/resend`, {});

// Institution DNA: departments, systems and leaders, nested under their institution.
export const listDepartments = (id: string) => http.get<Department[]>(`/institutions/${id}/departments`);
export const createDepartment = (id: string, body: DepartmentPayload) => http.post<Department>(`/institutions/${id}/departments`, body);
export const updateDepartment = (id: string, deptId: string, body: DepartmentPayload) =>
  http.patch<Department>(`/institutions/${id}/departments/${deptId}`, body);
export const deleteDepartment = (id: string, deptId: string) => http.delete(`/institutions/${id}/departments/${deptId}`);

export const listSystems = (id: string) => http.get<InstitutionSystem[]>(`/institutions/${id}/systems`);
export const createSystem = (id: string, body: SystemPayload) => http.post<InstitutionSystem>(`/institutions/${id}/systems`, body);
export const updateSystem = (id: string, sysId: string, body: SystemPayload) =>
  http.patch<InstitutionSystem>(`/institutions/${id}/systems/${sysId}`, body);
export const deleteSystem = (id: string, sysId: string) => http.delete(`/institutions/${id}/systems/${sysId}`);

export const listLeaders = (id: string) => http.get<InstitutionLeader[]>(`/institutions/${id}/leaders`);
export const createLeader = (id: string, body: LeaderPayload) => http.post<InstitutionLeader>(`/institutions/${id}/leaders`, body);
export const updateLeader = (id: string, leaderId: string, body: LeaderPayload) =>
  http.patch<InstitutionLeader>(`/institutions/${id}/leaders/${leaderId}`, body);
export const deleteLeader = (id: string, leaderId: string) => http.delete(`/institutions/${id}/leaders/${leaderId}`);
