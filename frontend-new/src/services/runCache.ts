import { http } from './http';
import { versionedStore } from '../utils/versioned';

/**
 * Run details kept for this tab, so a run is downloaded once and reused across screens (issue 60), but never shown
 * stale. Every screen that opens a run still asks the server, sending the version marker it holds (If-None-Match).
 * The server answers 304 only while nothing the response depends on has changed: the run's events, its stored
 * explanations, the follow-up stage, the execution ledger, the deployed code. Anything else is a full answer, which
 * replaces the kept copy. A completed run still changes after completion (explanations, recommendations), so the
 * copy is never used without that check. Parts of one screen asking at the same moment share one request.
 */
const store = versionedStore((path, version) =>
  http.get(path, {
    headers: version ? { 'If-None-Match': `"${version}"` } : {},
    // 304 is an answer only when there is a copy to reuse.
    validateStatus: (s) => (s >= 200 && s < 300) || (s === 304 && !!version),
  }));

/** GET `path`, reusing the kept copy when the server confirms its version is current. */
export const getVersioned = <T extends { version?: string }>(path: string) => store.get<T>(path);

/** Forget every kept run (signing out, or the session ending). */
export const clearKeptRuns = () => store.clear();
