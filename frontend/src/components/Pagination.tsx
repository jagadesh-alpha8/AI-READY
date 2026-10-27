import React from 'react';

/** Previous / next and "x–y of N" for a server-paginated list (api/pagination.ts). */
export const Pagination: React.FC<{
  page: number;
  pageSize: number;
  count: number;
  onPage: (page: number) => void;
}> = ({ page, pageSize, count, onPage }) => {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (count <= pageSize) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(count, page * pageSize);
  return (
    <div className="flex items-center justify-end gap-2 mt-3 text-xs text-ink-600" data-testid="pagination">
      <span className="tabular-nums">{from}–{to} of {count}</span>
      <button type="button" className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
      <span className="tabular-nums">Page {page} of {pages}</span>
      <button type="button" className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
    </div>
  );
};

/** `value` after it has stopped changing for `ms` (search boxes: one request per pause, not per key). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [settled, setSettled] = React.useState(value);
  React.useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

/** Filter options from server facet counts ({value: count}), most common first. */
export function optionsFromCounts(counts: Record<string, number> | undefined, label: (v: string) => string = (v) => v) {
  return Object.entries(counts || {})
    .filter(([value]) => value !== '')
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, label: label(value), count }));
}

/** One CRI pillar option from the facets API (backend scoring.constants.pillar_facet). */
export interface PillarFacet { value: string; code: string; label: string; count: number }

/** The CRI Pillar filter options, in the API's framework order (all 9 AI-QIF criteria, an unused one as 0). */
export function pillarOptions(pillars: PillarFacet[] | undefined) {
  return (pillars || []).map((p) => ({
    value: p.value, label: p.code ? `${p.code.replace('AIQIF-', '')} ${p.label}` : p.label, count: p.count,
  }));
}
