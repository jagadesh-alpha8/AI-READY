import api from './client';
import type { DriveImportJob } from '../types';

export function listDriveImportJobs(sprintId: string) {
  return api.get<DriveImportJob[]>(`/sprints/${sprintId}/drive-import-jobs`);
}

export function startDriveImport(sprintId: string, driveUrl: string) {
  return api.post<DriveImportJob>(`/sprints/${sprintId}/drive-import-jobs`, { drive_url: driveUrl });
}
