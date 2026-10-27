import { useCallback, useEffect, useRef, useState } from 'react';
import { getErrorMessage } from '../utils/errors';

/**
 * Fetch-on-mount (and on `deps` change) with loading/error state and a
 * stable `refetch` for retry buttons. `fetcher`'s *latest* closure is
 * always used (via a ref) so callers can pass a fresh inline arrow
 * function on every render without retriggering the effect -- only
 * changes to `deps` (or `enabled`) do that.
 *
 * `enabled` mirrors the `if (!sprintId || sprintId === 'demo-sprint-id')
 * return;` guard pages already use before their sprint is real -- pass
 * `false` instead of calling the hook conditionally (hooks can't be
 * conditional) to skip the request without erroring or showing loading.
 */
export function useApiResource<T>(
  fetcher: () => Promise<{ data: T }>,
  deps: React.DependencyList,
  enabled: boolean = true,
) {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState('');

  const refetch = useCallback(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    fetcherRef
      .current()
      .then((res) => setData(res.data))
      .catch((err) => setError(getErrorMessage(err, 'Failed to load data.')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  /** Background refresh for live pages: no loading state, and the current data stays shown while it fetches.
   * Resolves to '' on success, or the error message on failure -- the last good data is kept, and the error is
   * left to the caller to show unobtrusively (it does not become this resource's `error`). */
  const refresh = useCallback(async (): Promise<string> => {
    if (!enabled) return '';
    try {
      const res = await fetcherRef.current();
      setData(res.data);
      setError('');
      return '';
    } catch (err) {
      return getErrorMessage(err, 'Failed to refresh data.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return { data, setData, loading, error, refetch, refresh };
}
