/**
 * A store of versioned API answers (issue 60): a copy is reused only after the server confirms, with 304 Not
 * Modified, that the version marker it was sent with is still current. Requests for the same key made while one is
 * in flight share it. No imports, so the Node test runner can load it (see versioned.test.ts); runCache.ts wires it
 * to the HTTP client.
 */
export interface Answer<T> { status: number; data: T }
/** Fetch `key`; `ifNoneMatch` is the held version (send it as If-None-Match), or null when nothing is held. */
export type Fetcher = (key: string, ifNoneMatch: string | null) => Promise<Answer<unknown>>;

export function versionedStore(fetcher: Fetcher, maxKept = 6) {
  const kept = new Map<string, { version: string; data: unknown }>();
  const inFlight = new Map<string, Promise<{ data: unknown }>>();

  const remember = (key: string, version: string, data: unknown) => {
    kept.delete(key);
    kept.set(key, { version, data });
    while (kept.size > maxKept) kept.delete(kept.keys().next().value as string);
  };

  function get<T extends { version?: string }>(key: string): Promise<{ data: T }> {
    const pending = inFlight.get(key);
    if (pending) return pending as Promise<{ data: T }>;
    const entry = kept.get(key) || null;
    const request = fetcher(key, entry ? entry.version : null)
      .then((res) => {
        if (res.status === 304) {
          if (!entry) throw new Error('Not Modified without a kept copy');
          remember(key, entry.version, entry.data);
          return { data: entry.data as T };
        }
        const version = (res.data as T | null)?.version;
        if (version) remember(key, version, res.data);
        else kept.delete(key);
        return { data: res.data as T };
      })
      .finally(() => inFlight.delete(key));
    inFlight.set(key, request);
    return request;
  }

  return {
    get,
    clear() {
      kept.clear();
      inFlight.clear();
    },
    size: () => kept.size,
  };
}
