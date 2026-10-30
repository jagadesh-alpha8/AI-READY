import api from './client';
import type {
  CoordinatorStatus,
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

/** Creates the institution and invites its IQAC Coordinator; `invitation_email_sent` says whether the email went. */
export function createInstitution(payload: CreateInstitutionPayload) {
  return api.post<Institution & { invitation_email_sent: boolean }>('/institutions', payload);
}

// --- IQAC Coordinator (backend apps/institutions/coordinator.py) --------------

export function getCoordinator(institutionId: string) {
  return api.get<CoordinatorStatus>(`/institutions/${institutionId}/coordinator`);
}

/** Name or change the coordinator (InGage staff). Same email: name corrected; new email: new invitation. */
export function setCoordinator(institutionId: string, coordinator_name: string, coordinator_email: string) {
  return api.post<CoordinatorStatus>(`/institutions/${institutionId}/coordinator`, { coordinator_name, coordinator_email });
}

export function resendCoordinatorInvitation(institutionId: string) {
  return api.post<CoordinatorStatus>(`/institutions/${institutionId}/coordinator/resend`, {});
}

/** Public: what an invitation link is for (college, person, whether a password must be chosen). */
export function checkInvitation(token: string) {
  return api.post<{ institution_name: string; name: string; email: string; needs_password: boolean }>(
    '/auth/invitation', { token });
}

export function acceptInvitation(token: string, new_password: string) {
  return api.post<{ detail: string; email: string }>('/auth/invitation/accept', { token, new_password });
}

/** The single-record read — the only one that carries leaders and the derived counts. */
export function getInstitution(id: string) {
  return api.get<InstitutionDetail>(`/institutions/${id}`);
}

export function updateInstitution(id: string, payload: UpdateInstitutionPayload) {
  return api.patch<InstitutionDetail>(`/institutions/${id}`, payload);
}

export interface InstitutionDeletionDependencies {
  sprints: number;
  documents: number;
  facts: number;
  evidence_requests: number;
  evidence_submissions: number;
  gaps: number;
  baselines: number;
  reports: number;
  benchmark_cycles: number;
  benchmark_assessments: number;
  benchmark_evidence: number;
  audit_records: number;
  coordinator_events: number;
  departments: number;
  leaders: number;
  systems: number;
}

export interface InstitutionDeletionPreview {
  institution_id: string;
  institution_name: string;
  can_delete: boolean;
  is_blocked: boolean;
  block_reason: string | null;
  recommended_action: 'delete' | 'archive';
  alternative_available: boolean;
  alternative_action: string;
  dependencies: InstitutionDeletionDependencies;
  protected_counts: Partial<InstitutionDeletionDependencies>;
}

/** Hard delete: permanently removes an institution when no protected records exist.
 * Restricted server-side strictly to Super Admins. */
export function deleteInstitution(id: string) {
  return api.delete(`/institutions/${id}`);
}

/** Fetches backend dependency breakdown before attempting deletion. */
export function getInstitutionDeletionPreview(id: string) {
  return api.get<InstitutionDeletionPreview>(`/institutions/${id}/deletion-preview/`);
}

/** Safely deactivates / archives an institution, preserving historical evidence and audit logs. */
export function archiveInstitution(id: string) {
  return api.post<InstitutionDetail>(`/institutions/${id}/archive/`);
}

/** Reactivates an archived institution. */
export function unarchiveInstitution(id: string) {
  return api.post<InstitutionDetail>(`/institutions/${id}/unarchive/`);
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
