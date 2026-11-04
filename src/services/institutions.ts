import { http } from './http';
import type {
  CoordinatorStatus, CreateInstitutionPayload, Department, Institution, InstitutionDetail, InstitutionSystem,
} from '../types/api';

export const listInstitutions = () => http.get<Institution[]>('/institutions');
export const getInstitution = (id: string) => http.get<InstitutionDetail>(`/institutions/${id}`);
/** Creates the college and invites its IQAC Coordinator by email (InGage staff). */
export const createInstitution = (payload: CreateInstitutionPayload) =>
  http.post<Institution & { invitation_email_sent: boolean }>('/institutions', payload);
export const updateInstitution = (id: string, payload: Partial<Institution> & { affiliation?: string }) =>
  http.patch<InstitutionDetail>(`/institutions/${id}`, payload);
export const getCoordinator = (id: string) => http.get<CoordinatorStatus>(`/institutions/${id}/coordinator`);
export const resendCoordinatorInvitation = (id: string) =>
  http.post<CoordinatorStatus>(`/institutions/${id}/coordinator/resend`, {});
export const listDepartments = (id: string) => http.get<Department[]>(`/institutions/${id}/departments`);
export const listSystems = (id: string) => http.get<InstitutionSystem[]>(`/institutions/${id}/systems`);
