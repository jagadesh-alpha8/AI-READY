import api from './client';

/** One chunk of a college's own document, returned by semantic search.
 * Every field but `score` and `text` exists so the passage can be cited —
 * the backend has no code path that returns an anonymous vector. */
export interface EvidenceResult {
  score: number;
  text: string;
  document_id: string;
  document_name: string;
  document_type: string;
  page_number: number | null;
  chunk_index: number | null;
  sprint_id: string;
  institution_id: string;
}

export interface EvidenceSearchResponse {
  query: string;
  count: number;
  results: EvidenceResult[];
}

/**
 * Semantic search over this sprint's indexed documents.
 *
 * The institution is taken from the sprint in the URL, never from this
 * payload — that is what makes cross-college retrieval impossible, so there
 * is deliberately no institution argument to pass.
 *
 * Answers `503` when the vector store is not configured on the server, which
 * callers must present as "not available" rather than "nothing found".
 */
export function searchEvidence(
  sprintId: string,
  query: string,
  options: { topK?: number; scopeToSprint?: boolean } = {},
) {
  return api.post<EvidenceSearchResponse>(`/sprints/${sprintId}/evidence-search`, {
    query,
    top_k: options.topK ?? 4,
    scope_to_sprint: options.scopeToSprint ?? true,
  });
}
