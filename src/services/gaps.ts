import { http } from './http';
import type { Gap, GapDetail, GapFacets, Page } from '../types/api';
import { cleanParams } from '../utils/params';

export interface GapQuery {
  page?: number;
  page_size?: number;
  gap_type?: string;
  priority?: string;
  status?: string;
  ordering?: string;
}

export const listSprintGapsPage = (sprintId: string, query: GapQuery = {}) =>
  http.get<Page<Gap>>(`/sprints/${sprintId}/gaps`, { params: cleanParams({ page: 1, ...query }) });
export const getSprintGapFacets = (sprintId: string) => http.get<GapFacets>(`/sprints/${sprintId}/gaps/facets`);
/** One gap in full, with its history and (for contradictions) every competing value. */
export const getGap = (id: string) => http.get<GapDetail>(`/gaps/${id}`);
export const resolveGap = (id: string, resolution: string) => http.post<Gap>(`/gaps/${id}/resolve`, { resolution });
export const markGapUnavailable = (id: string, resolution: string) =>
  http.post<Gap>(`/gaps/${id}/mark-unavailable`, { resolution });
export const skipGap = (id: string, resolution: string) => http.post<Gap>(`/gaps/${id}/skip`, { resolution });
