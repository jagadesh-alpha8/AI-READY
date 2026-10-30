import api from './client';

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  role: string;
  role_label: string;
  institution_id: string | null;
  institution_name: string;
  department_name: string;
  is_active: boolean;
  date_joined: string;
  updated_at: string;
}

export interface UserPayload {
  email?: string;
  username?: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
  role?: string;
  institution_id?: string | null;
  department_name?: string;
  is_active?: boolean;
  password?: string;
}

export interface UserDeletionDependency {
  model: string;
  field: string;
  count: number;
}

export interface UserDeletionPreview {
  can_delete: boolean;
  dependencies: UserDeletionDependency[];
  detail: string;
}

export function listUsers() {
  return api.get<AdminUser[]>('/users');
}

export function createUser(payload: UserPayload) {
  return api.post<AdminUser>('/users', payload);
}

export function updateUser(id: string, payload: UserPayload) {
  return api.patch<AdminUser>(`/users/${id}`, payload);
}

/** Deactivates rather than destroys — the row stays so audit trails naming
 * this person still resolve. Returns the updated user, not an empty 204. */
export function deactivateUser(id: string) {
  return api.delete<AdminUser>(`/users/${id}`);
}

export function previewUserDeletion(id: string) {
  return api.get<UserDeletionPreview>(`/users/${id}/deletion-preview`);
}

export function permanentlyDeleteUser(id: string, reason = '') {
  return api.post<{ detail: string }>(`/users/${id}/permanent-delete`, { reason });
}
