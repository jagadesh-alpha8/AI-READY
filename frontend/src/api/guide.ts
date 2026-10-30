import api from './client';
import type { GuideStatusResponse, GuideStepId } from '../types/guide';

export async function getGuideStatus(
  sprintId?: string,
  institutionId?: string
): Promise<{ data: GuideStatusResponse }> {
  const params: Record<string, string> = { workflow: 'capability' };
  if (sprintId) params.sprint_id = sprintId;
  if (institutionId) params.institution_id = institutionId;
  return api.get<GuideStatusResponse>('/auth/guide-status', { params });
}

export async function skipGuideStep(
  stepId: GuideStepId,
  sprintId?: string,
  institutionId?: string,
  skipped: boolean = true
): Promise<{ data: GuideStatusResponse }> {
  return api.post<GuideStatusResponse>('/auth/guide-skip', {
    workflow: 'capability',
    step_id: stepId,
    sprint_id: sprintId || undefined,
    institution_id: institutionId || undefined,
    skipped,
  });
}

export async function dismissGuide(
  dismissed: boolean,
  sprintId?: string,
  institutionId?: string
): Promise<{ data: GuideStatusResponse }> {
  return api.post<GuideStatusResponse>('/auth/guide-dismiss', {
    workflow: 'capability',
    dismissed,
    sprint_id: sprintId || undefined,
    institution_id: institutionId || undefined,
  });
}

export async function resetGuide(
  sprintId?: string,
  institutionId?: string
): Promise<{ data: GuideStatusResponse }> {
  return api.post<GuideStatusResponse>('/auth/guide-reset', { workflow: 'capability',
    sprint_id: sprintId || undefined,
    institution_id: institutionId || undefined,
  });
}

export async function updateMenuTour(
  menuKey: string,
  status: 'completed' | 'dismissed' | 'in_progress' | 'reset',
  sprintId?: string,
  institutionId?: string
): Promise<{ data: GuideStatusResponse }> {
  return api.post<GuideStatusResponse>('/auth/menu-tour-update', {
    menu_key: menuKey,
    status,
    sprint_id: sprintId || undefined,
    institution_id: institutionId || undefined,
  });
}


