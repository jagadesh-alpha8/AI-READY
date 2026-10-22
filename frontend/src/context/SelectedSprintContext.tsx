import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { listSprints } from '../api/sprints';
import type { Sprint } from '../types';
import {
  readStoredSprint, resolveSelection, sprintIdFromPath, storedAfter, switchSprintPath, writeStoredSprint,
} from '../utils/selectedSprint.ts';
import type { SelectionStatus } from '../utils/selectedSprint.ts';
import { useAuth } from './AuthContext';

/**
 * The one selected sprint (rules: utils/selectedSprint.ts). Read it with useSelectedSprint(); change it
 * only with selectSprint(), which is what the header's picker and "Open" call.
 */
export interface SelectedSprintValue {
  /** The selected sprint's id ('' when none, or when it is not one of the user's sprints). */
  sprintId: string;
  /** The selected sprint, once the user's sprints are loaded. */
  sprint: Sprint | null;
  status: SelectionStatus;
  /** The user's sprints (null while loading, or when loading failed). */
  sprints: Sprint[] | null;
  /** The list could not be loaded: the selection is kept (never treated as gone) until a retry works. */
  loadError: boolean;
  /** The user explicitly chooses a sprint. On a sprint page this opens the same step for that sprint. */
  selectSprint: (sprintId: string) => void;
  /** Reload the user's sprints (after creating, archiving or deleting one). */
  refreshSprints: () => void;
}

export const SelectedSprintContext = createContext<SelectedSprintValue | null>(null);

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const SelectedSprintProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const userId = user?.id;
  const { pathname } = useLocation();
  const navigate = useNavigate();

  const [storedId, setStoredId] = useState(() => readStoredSprint(browserStorage(), userId));
  const storedRef = useRef(storedId);
  storedRef.current = storedId;
  useEffect(() => setStoredId(readStoredSprint(browserStorage(), userId)), [userId]);

  const [sprints, setSprints] = useState<Sprint[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const loadSeq = useRef(0);
  const refreshSprints = useCallback(() => {
    const seq = ++loadSeq.current;
    if (!userId) {
      setSprints(null);
      return;
    }
    listSprints()
      .then(({ data }) => { if (seq === loadSeq.current) { setSprints(data); setLoadError(false); } })
      .catch(() => { if (seq === loadSeq.current) setLoadError(true); });
  }, [userId]);
  useEffect(() => {
    setSprints(null);
    refreshSprints();
  }, [refreshSprints]);

  const routeId = sprintIdFromPath(pathname);
  const visibleIds = useMemo(() => (sprints ? sprints.map((s) => s.id) : null), [sprints]);
  const selection = resolveSelection(routeId, storedId, visibleIds);

  const remember = useCallback((id: string) => {
    writeStoredSprint(browserStorage(), userId, id);
    storedRef.current = id;
    setStoredId(id);
  }, [userId]);

  // Save what the resolution implies (utils/selectedSprint.ts storedAfter): a sprint opened by its URL
  // (a link, a bookmark, browser back/forward) once the list confirms the user can see it; or forget a
  // saved sprint that is gone. Runs when the resolution changes -- not when the saved id does, so a switch
  // in progress is never undone by the old URL.
  useEffect(() => {
    const next = storedAfter(selection, storedRef.current);
    if (next !== null) remember(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.fromRoute, selection.status, selection.sprintId, remember]);

  // A sprint in the URL that is not in the list may have just been created: reload the list once for it.
  const reloadedFor = useRef('');
  useEffect(() => {
    if (selection.fromRoute && selection.status === 'not_found' && reloadedFor.current !== routeId) {
      reloadedFor.current = routeId;
      refreshSprints();
    }
  }, [selection.fromRoute, selection.status, routeId, refreshSprints]);

  const selectSprint = useCallback((id: string) => {
    remember(id);
    const next = id ? switchSprintPath(pathname, id) : null;
    if (next && next !== pathname) navigate(next);
  }, [remember, pathname, navigate]);

  const value = useMemo<SelectedSprintValue>(() => ({
    // Kept while the list loads (the sidebar's links); dropped once the sprint is known to be missing.
    sprintId: selection.status === 'ok' || selection.status === 'loading' ? selection.sprintId : '',
    sprint: sprints?.find((s) => s.id === selection.sprintId) || null,
    status: selection.status,
    sprints,
    loadError,
    selectSprint,
    refreshSprints,
  }), [selection.status, selection.sprintId, sprints, loadError, selectSprint, refreshSprints]);

  return <SelectedSprintContext.Provider value={value}>{children}</SelectedSprintContext.Provider>;
};

export function useSelectedSprint(): SelectedSprintValue {
  const value = useContext(SelectedSprintContext);
  if (!value) throw new Error('useSelectedSprint must be used inside SelectedSprintProvider');
  return value;
}
