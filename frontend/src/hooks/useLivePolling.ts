import { useEffect, useRef } from 'react';

/**
 * Calls `refresh` every `intervalMs` while `active` -- for pages that should follow AI work as it happens
 * (extraction, evidence assessment) without reloading or losing the user's place. Pair it with
 * useApiResource's `refresh()`, which swaps data in place with no loading state.
 *
 * - One round at a time: the next is scheduled only after the previous finishes (never overlapping).
 * - Skips rounds while the tab is hidden and catches up as soon as it is visible again.
 * - `refresh` may change every render; the latest one is always used.
 */
export function useLivePolling(active: boolean, refresh: () => Promise<unknown> | void, intervalMs = 5000) {
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    let running = false;
    let timer: ReturnType<typeof setTimeout>;
    const round = async () => {
      if (running) return;
      running = true;
      try { await refreshRef.current(); } catch { /* keep the last good data; the next round tries again */ }
      finally { running = false; }
    };
    const tick = async () => {
      if (!document.hidden) await round();
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    };
    timer = setTimeout(tick, intervalMs);
    const onVisible = () => { if (!document.hidden) round(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [active, intervalMs]);
}
