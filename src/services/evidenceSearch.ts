import { http } from './http';
import type { EvidenceResult } from '../types/api';

/**
 * Semantic search over the sprint's own indexed documents; every result carries its document and page.
 * Answers 503 when the vector store is not configured: show "not available", not "nothing found".
 */
export const searchEvidence = (sprintId: string, query: string, topK = 5) =>
  http.post<{ query: string; count: number; results: EvidenceResult[] }>(`/sprints/${sprintId}/evidence-search`, {
    query, top_k: topK, scope_to_sprint: true,
  });
