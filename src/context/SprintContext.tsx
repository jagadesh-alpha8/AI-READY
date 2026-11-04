import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { listSprints } from '../services/sprints';
import { SELECTED_SPRINT_KEY } from '../config/env';
import { storage } from '../utils/storage';
import type { Sprint } from '../types/api';
import { useAuth } from './AuthContext';

/**
 * The audit sprint every screen works on (the prototype's "institution switcher"). The choice is remembered per
 * browser; with none remembered, the most recently updated sprint that is not archived is used.
 */
interface SprintState {
  sprints: Sprint[];
  sprint: Sprint | null;
  loading: boolean;
  error: unknown;
  select: (id: string) => void;
  reload: () => Promise<void>;
}

const SprintContext = createContext<SprintState | undefined>(undefined);

export function SprintProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(storage.get(SELECTED_SPRINT_KEY));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listSprints();
      setSprints(res.data);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) void reload();
    else setSprints([]);
  }, [user, reload]);

  const sprint = useMemo(() => {
    const chosen = sprints.find((s) => s.id === selectedId);
    if (chosen) return chosen;
    const live = [...sprints]
      .filter((s) => s.status !== 'archived')
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return live[0] || sprints[0] || null;
  }, [sprints, selectedId]);

  const select = useCallback((id: string) => {
    storage.set(SELECTED_SPRINT_KEY, id);
    setSelectedId(id);
  }, []);

  const value = useMemo(() => ({ sprints, sprint, loading, error, select, reload }), [sprints, sprint, loading, error, select, reload]);
  return <SprintContext.Provider value={value}>{children}</SprintContext.Provider>;
}

export function useSprint() {
  const ctx = useContext(SprintContext);
  if (!ctx) throw new Error('useSprint must be used inside SprintProvider');
  return ctx;
}
