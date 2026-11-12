import { useCallback, useEffect, useRef, useState } from 'react';
import type { AxiosResponse } from 'axios';

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  refetch: () => Promise<void>;
  setData: (data: T | null) => void;
}

/**
 * Load one API resource. `key` names what is loaded (e.g. the sprint id): a new key reloads, and an answer for
 * an old key is dropped so a slow response never overwrites a newer one. `enabled = false` loads nothing.
 */
export function useResource<T>(loader: () => Promise<AxiosResponse<T> | { data: T }>, key: string, enabled = true): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<unknown>(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const requestId = useRef(0);

  const run = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const res = await loaderRef.current();
      if (id === requestId.current) setData(res.data);
    } catch (e) {
      if (id === requestId.current) setError(e);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setData(null);
    void run();
  }, [key, enabled, run]);

  return { data, loading, error, refetch: run, setData };
}

/** Call `tick` every `ms` while `active` (processing jobs, report generation). */
export function usePolling(tick: () => void, active: boolean, ms = 5000) {
  const tickRef = useRef(tick);
  tickRef.current = tick;
  useEffect(() => {
    if (!active) return;
    const handle = window.setInterval(() => tickRef.current(), ms);
    return () => window.clearInterval(handle);
  }, [active, ms]);
}
