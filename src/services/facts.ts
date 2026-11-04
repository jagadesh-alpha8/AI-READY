import { http } from './http';
import type { Fact, FactDetail, FactFacets, Page } from '../types/api';
import { cleanParams } from '../utils/params';

export interface FactQuery {
  page?: number;
  page_size?: number;
  q?: string;
  status?: string;
  pillar?: string;
  ordering?: string;
}

export const listSprintFactsPage = (sprintId: string, query: FactQuery = {}) =>
  http.get<Page<Fact>>(`/sprints/${sprintId}/facts`, { params: cleanParams({ page: 1, ...query }) });
export const getSprintFactFacets = (sprintId: string) => http.get<FactFacets>(`/sprints/${sprintId}/facts/facets`);
/** One fact in full, with its review history. */
export const getFact = (id: string) => http.get<FactDetail>(`/facts/${id}`);
export const confirmFact = (id: string, reason: string) => http.post<Fact>(`/facts/${id}/confirm`, { reason });
export const rejectFact = (id: string, reason: string) => http.post<Fact>(`/facts/${id}/reject`, { reason });
export const correctFact = (id: string, newValue: unknown, reason: string) =>
  http.post<Fact>(`/facts/${id}/correct`, { new_value: newValue, reason });
/** Creates an evidence request behind the fact ("evidence insufficient"). */
export const requestFactEvidence = (id: string, evidenceNeeded: string, reason: string) =>
  http.post<Fact>(`/facts/${id}/request-evidence`, { evidence_needed: evidenceNeeded, reason });
