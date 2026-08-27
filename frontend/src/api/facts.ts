import api from './client';
import type { Fact } from '../types';

export function listSprintFacts(sprintId: string) {
  return api.get<Fact[]>(`/sprints/${sprintId}/facts`);
}

export function getFact(id: string) {
  return api.get<Fact>(`/facts/${id}`);
}

export function confirmFact(id: string, comment = 'Confirmed by reviewer') {
  return api.post<Fact>(`/facts/${id}/confirm`, { comment });
}

export function correctFact(id: string, correctedValue: unknown, comment = 'User correction') {
  return api.post<Fact>(`/facts/${id}/correct`, { corrected_value: correctedValue, comment });
}

export function rejectFact(id: string, comment = 'Rejected by reviewer') {
  return api.post<Fact>(`/facts/${id}/reject`, { comment });
}

export function requestFactEvidence(id: string, comment = 'Additional evidence requested') {
  return api.post<Fact>(`/facts/${id}/request-evidence`, { comment });
}
