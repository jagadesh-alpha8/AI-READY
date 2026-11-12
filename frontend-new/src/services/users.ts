import { http } from './http';
import type { AdminUser } from '../types/api';
import type { UserDeletionPreview, UserPayload } from '../types/workflow';

/** Super Admins manage everyone; IQAC Coordinators only their own college (server-enforced). */
export const listUsers = () => http.get<AdminUser[]>('/users');
export const createUser = (payload: UserPayload) => http.post<AdminUser>('/users', payload);
export const updateUser = (id: string, payload: UserPayload) => http.patch<AdminUser>(`/users/${id}`, payload);
/** Deactivates (the row stays so audit trails still resolve); answers with the updated user. */
export const deactivateUser = (id: string) => http.delete<AdminUser>(`/users/${id}`);
export const previewUserDeletion = (id: string) => http.get<UserDeletionPreview>(`/users/${id}/deletion-preview`);
/** Permanent delete; refused while records still reference the user (see the preview). */
export const permanentlyDeleteUser = (id: string, reason: string) =>
  http.post<{ detail: string }>(`/users/${id}/permanent-delete`, { reason });
