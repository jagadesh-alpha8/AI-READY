import api from './client';
import type { CreateInstitutionPayload, Institution } from '../types';

export function listInstitutions() {
  return api.get<Institution[]>('/institutions');
}

export function createInstitution(payload: CreateInstitutionPayload) {
  return api.post<Institution>('/institutions', payload);
}

export function getInstitution(id: string) {
  return api.get<Institution>(`/institutions/${id}`);
}
