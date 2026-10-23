import api from './client';

/** A server-paginated list (backend config/pagination.py: 50 per page by default, at most 100). */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export const DEFAULT_PAGE_SIZE = 50;
export const MAX_PAGE_SIZE = 100;

/** Query params without empty values (an empty filter means "all"). */
export function cleanParams(params: Record<string, string | number | undefined | null>) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null));
}

/**
 * Every row of a paginated list, fetched 100 at a time -- for pages that genuinely need the whole sprint
 * (e.g. an owner's task list across facts and gaps). Lists shown as tables use one page at a time instead.
 * Returns `{ data }` like an axios response, so `useApiResource` takes it unchanged.
 */
export async function fetchAllPages<T>(url: string, params: Record<string, string | number | undefined> = {}) {
  const rows: T[] = [];
  for (let page = 1; ; page += 1) {
    const { data } = await api.get<Page<T>>(url, { params: { ...cleanParams(params), page, page_size: MAX_PAGE_SIZE } });
    rows.push(...data.results);
    if (!data.next || data.results.length === 0) break;
  }
  return { data: rows };
}
