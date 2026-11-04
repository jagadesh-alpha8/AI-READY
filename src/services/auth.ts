import { http } from './http';
import type { LoginResponse, RoleAccessDefinition, User } from '../types/api';

export const login = (email: string, password: string) => http.post<LoginResponse>('/auth/login', { email, password });
export const getCurrentUser = () => http.get<User>('/auth/me');
export const logout = (refresh: string) => http.post('/auth/logout', { refresh });
export const changePassword = (oldPassword: string, newPassword: string) =>
  http.post<{ detail: string }>('/auth/change-password', { old_password: oldPassword, new_password: newPassword });
/** Always answers the same way, whether or not the email has an account. */
export const requestPasswordReset = (email: string) => http.post<{ detail: string }>('/auth/password-reset', { email });
export const getRoleAccessMatrix = () => http.get<{ roles: RoleAccessDefinition[] }>('/auth/access-matrix');
