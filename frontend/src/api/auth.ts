import api from './client';
import type { LoginResponse, User } from '../types';

export function login(email: string, password: string) {
  return api.post<LoginResponse>('/auth/login', { email, password });
}

export function getCurrentUser() {
  return api.get<User>('/auth/me');
}

export function logout(refresh: string) {
  return api.post('/auth/logout', { refresh });
}

export function refreshAccessToken(refresh: string) {
  return api.post<{ access: string }>('/auth/refresh', { refresh });
}

export function changePassword(oldPassword: string, newPassword: string) {
  return api.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword });
}

/** Always answers the same way, whether or not the email has an account. */
export function requestPasswordReset(email: string) {
  return api.post<{ detail: string }>('/auth/password-reset', { email });
}

export function confirmPasswordReset(uid: string, token: string, newPassword: string) {
  return api.post<{ detail: string }>('/auth/password-reset/confirm', { uid, token, new_password: newPassword });
}

export interface RoleAccessModule {
  name: string;
  access: string;
  description: string;
}

export interface RoleAccessDefinition {
  role: string;
  name: string;
  institution_scope: string;
  description: string;
  modules: RoleAccessModule[];
  permitted_actions: string[];
  prohibited_actions: string[];
}

export interface RoleAccessMatrixResponse {
  roles: RoleAccessDefinition[];
}

export function getRoleAccessMatrix() {
  return api.get<RoleAccessMatrixResponse>('/auth/access-matrix');
}
