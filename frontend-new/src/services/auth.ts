import { http } from './http';
import type { LoginResponse, RoleAccessDefinition, User } from '../types/api';

export const login = (email: string, password: string) => http.post<LoginResponse>('/auth/login', { email, password });
export const getCurrentUser = () => http.get<User>('/auth/me');
export const logout = (refresh: string) => http.post('/auth/logout', { refresh });
export const changePassword = (oldPassword: string, newPassword: string) =>
  http.post<{ detail: string }>('/auth/change-password', { old_password: oldPassword, new_password: newPassword });
/** Always answers the same way, whether or not the email has an account. */
export const requestPasswordReset = (email: string) => http.post<{ detail: string }>('/auth/password-reset', { email });
/** The emailed link is {FRONTEND_BASE_URL}/reset-password?uid=...&token=... (works once, expires in 1 hour). */
export const confirmPasswordReset = (uid: string, token: string, newPassword: string) =>
  http.post<{ detail: string }>('/auth/password-reset/confirm', { uid, token, new_password: newPassword });
export const getRoleAccessMatrix = () => http.get<{ roles: RoleAccessDefinition[] }>('/auth/access-matrix');

/** The IQAC Coordinator invitation link is {FRONTEND_BASE_URL}/activate-account?token=... (public, single use). */
export const checkInvitation = (token: string) =>
  http.post<{ institution_name: string; name: string; email: string; needs_password: boolean }>('/auth/invitation', { token });
export const acceptInvitation = (token: string, newPassword: string) =>
  http.post<{ detail: string; email: string }>('/auth/invitation/accept', { token, new_password: newPassword });

// --- onboarding guide (derived from real data; skip / dismiss / tours never change business records) ---
export interface GuideStep {
  id: string;
  number: number;
  title: string;
  purpose: string;
  status: 'completed' | 'in_progress' | 'not_started' | 'skipped' | 'blocked' | string;
  action_label: string;
  target_path: string;
  is_authorized: boolean;
  block_reason: string | null;
  details: Record<string, unknown>;
}
export interface GuideStatus {
  current_step_id: string | null;
  current_step: GuideStep | null;
  steps: GuideStep[];
  is_dismissed: boolean;
  completed_count: number;
  skipped_count: number;
  total_steps: number;
  menu_tours: Record<string, string>;
  institution_name: string | null;
  sprint_code: string | null;
}
type GuideScope = { sprint_id?: string; institution_id?: string };
export const getGuideStatus = (scope: GuideScope = {}) => http.get<GuideStatus>('/auth/guide-status', { params: scope });
export const skipGuideStep = (stepId: string, skipped: boolean, scope: GuideScope = {}) =>
  http.post<GuideStatus>('/auth/guide-skip', { step_id: stepId, skipped, ...scope });
export const dismissGuide = (dismissed: boolean, scope: GuideScope = {}) =>
  http.post<GuideStatus>('/auth/guide-dismiss', { dismissed, ...scope });
export const resetGuide = (scope: GuideScope = {}) => http.post<GuideStatus>('/auth/guide-reset', scope);
export const updateMenuTour = (menuKey: string, status: 'completed' | 'dismissed' | 'in_progress' | 'reset', scope: GuideScope = {}) =>
  http.post<GuideStatus>('/auth/menu-tour-update', { menu_key: menuKey, status, ...scope });
