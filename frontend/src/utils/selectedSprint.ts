/**
 * The selected sprint, as pure rules (no React) -- used by context/SelectedSprintContext.tsx and run
 * directly by `npm test`.
 *
 * One selection for the whole app:
 * - On a sprint page (/sprint/<id>/<step>) the URL *is* the selection.
 * - Everywhere else it is the sprint the user last chose, saved per user in localStorage so it survives a
 *   refresh and moving between menus.
 * - It changes only when the user picks another sprint (the header's picker, or opening a sprint) -- never
 *   by defaulting to "the first sprint".
 */

/** The placeholder the sidebar used to link to when no sprint was open; never a real selection. */
export const PLACEHOLDER_SPRINT_ID = 'demo-sprint-id';

const STORAGE_PREFIX = 'aios_selected_sprint:';

export const storageKey = (userId: string) => `${STORAGE_PREFIX}${userId}`;

type ReadStorage = Pick<Storage, 'getItem'>;
type WriteStorage = Pick<Storage, 'setItem' | 'removeItem'>;

/** The sprint id in a /sprint/<id>/<step> URL, or '' (Sprint Setup and the placeholder are not sprints). */
export function sprintIdFromPath(pathname: string): string {
  const match = /^\/sprint\/([^/]+)\/[^/]+/.exec(pathname);
  if (!match) return '';
  const id = decodeURIComponent(match[1]);
  return id === PLACEHOLDER_SPRINT_ID ? '' : id;
}

/** Link to one sprint step, or null when no sprint is selected. */
export function sprintStepPath(sprintId: string, step: string): string | null {
  return sprintId ? `/sprint/${encodeURIComponent(sprintId)}/${step}` : null;
}

/** Switching sprints on a sprint page keeps the step: /sprint/A/gaps -> /sprint/B/gaps. Null off sprint
 * pages (the page stays and reloads for the new sprint). The query string is dropped -- it may name
 * records of the previous sprint. */
export function switchSprintPath(pathname: string, newSprintId: string): string | null {
  if (!sprintIdFromPath(pathname)) return null;
  const rest = pathname.replace(/^\/sprint\/[^/]+/, '');
  return `/sprint/${encodeURIComponent(newSprintId)}${rest}`;
}

export function readStoredSprint(storage: ReadStorage | null, userId: string | undefined): string {
  if (!storage || !userId) return '';
  try {
    return storage.getItem(storageKey(userId)) || '';
  } catch {
    return ''; // storage blocked (private mode etc.): no saved selection
  }
}

export function writeStoredSprint(storage: WriteStorage | null, userId: string | undefined, sprintId: string) {
  if (!storage || !userId) return;
  try {
    if (sprintId) storage.setItem(storageKey(userId), sprintId);
    else storage.removeItem(storageKey(userId));
  } catch {
    // storage blocked: the selection still holds for this visit, it just won't survive a refresh
  }
}

/**
 * - none: nothing selected -- pages ask the user to choose.
 * - loading: selected, but the user's sprints are not loaded yet.
 * - ok: selected and visible to this user.
 * - not_found: selected (or in the URL) but not among the user's sprints -- deleted, or no access.
 */
export type SelectionStatus = 'none' | 'loading' | 'ok' | 'not_found';

export interface Selection {
  sprintId: string;
  fromRoute: boolean;
  status: SelectionStatus;
}

/** The URL's sprint wins; else the saved one. `visibleSprintIds` is null while the list is loading. */
export function resolveSelection(routeSprintId: string, storedSprintId: string,
  visibleSprintIds: readonly string[] | null): Selection {
  const sprintId = routeSprintId || storedSprintId;
  const fromRoute = !!routeSprintId;
  if (!sprintId) return { sprintId: '', fromRoute, status: 'none' };
  if (visibleSprintIds === null) return { sprintId, fromRoute, status: 'loading' };
  return { sprintId, fromRoute, status: visibleSprintIds.includes(sprintId) ? 'ok' : 'not_found' };
}

/**
 * What to save once a selection is resolved, or null for no change: the URL's sprint, once it is known
 * to be visible (opening a sprint selects it); '' to forget a saved sprint that is gone (deleted, or no
 * longer visible), so pages ask for a choice instead.
 */
export function storedAfter(selection: Selection, storedSprintId: string): string | null {
  if (selection.fromRoute && selection.status === 'ok' && selection.sprintId !== storedSprintId) {
    return selection.sprintId;
  }
  if (!selection.fromRoute && selection.status === 'not_found') return '';
  return null;
}
