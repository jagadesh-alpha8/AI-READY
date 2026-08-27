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
