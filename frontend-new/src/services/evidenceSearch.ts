import { http } from './http';
import type { EvidenceResult, Page } from '../types/api';
import type { VectorIndexRow } from '../types/workflow';

/**
 * Semantic search over the sprint's own indexed documents; every result carries its document and page.
 * Answers 503 when the vector store is not configured: show "not available", not "nothing found".
 */
export const searchEvidence = (sprintId: string, query: string, topK = 5) =>
  http.post<{ query: string; count: number; results: EvidenceResult[] }>(`/sprints/${sprintId}/evidence-search`, {
    query, top_k: topK, scope_to_sprint: true,
  });
/** Which processed documents are in the search index, how many vectors each holds, and why any failed. */
export const getVectorIndexStatus = (sprintId: string) =>
  http.get<VectorIndexRow[] | Page<VectorIndexRow>>(`/sprints/${sprintId}/vector-index/status`);
/** Queue every processed document for indexing (CanManageSprint); `force` re-indexes ones already done. 503 when disabled. */
export const buildVectorIndex = (sprintId: string, force = false) =>
  http.post<VectorIndexRow[]>(`/sprints/${sprintId}/vector-index`, { force });
