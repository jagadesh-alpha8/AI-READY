import React from 'react';
import { Search, X } from 'lucide-react';

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface FilterSelect {
  key: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: FilterOption[];
}

/**
 * Distinct values of one column, with how many rows have each -- the options
 * for a filter dropdown. Built from the loaded rows, so it only ever offers
 * values that actually exist (no empty results from a stale fixed list).
 */
export function optionsFrom<T>(
  rows: T[],
  getValue: (row: T) => string | null | undefined,
  getLabel: (value: string) => string = (value) => value,
): FilterOption[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = getValue(row) || '';
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count, label: value ? getLabel(value) : '(none)' }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** Case-insensitive "does any of these fields contain the search text". */
export function matchesSearch(search: string, ...fields: unknown[]): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return fields.some((field) => {
    if (field === null || field === undefined) return false;
    const text = typeof field === 'string' ? field : JSON.stringify(field);
    return text.toLowerCase().includes(needle);
  });
}

/** A search box plus one dropdown per column, with a "Showing X of Y" count. */
export const TableFilters: React.FC<{
  search: string;
  onSearch: (value: string) => void;
  placeholder: string;
  selects: FilterSelect[];
  shown: number;
  total: number;
}> = ({ search, onSearch, placeholder, selects, shown, total }) => {
  const active = !!search.trim() || selects.some((s) => s.value);
  const clearAll = () => {
    onSearch('');
    selects.forEach((s) => s.onChange(''));
  };

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <div className="relative flex-1 min-w-[200px] max-w-sm">
        <Search className="w-4 h-4 text-ink-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={placeholder}
          className="input w-full pl-9 py-2 text-sm"
          aria-label="Search"
        />
      </div>
      {selects.map((select) => (
        <select
          key={select.key}
          value={select.value}
          onChange={(e) => select.onChange(e.target.value)}
          className={`input py-2 text-sm w-auto max-w-[220px] ${select.value ? 'border-brand-500 text-ink-900' : ''}`}
          aria-label={select.label}
        >
          <option value="">{select.label}: All</option>
          {select.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}{option.count === undefined ? '' : ` (${option.count})`}
            </option>
          ))}
        </select>
      ))}
      {active && (
        <button onClick={clearAll} className="btn-secondary btn-sm">
          <X className="w-3.5 h-3.5" />
          <span>Clear filters</span>
        </button>
      )}
      <span className="text-xs text-ink-500 ml-auto tabular-nums">
        Showing {shown} of {total}
      </span>
    </div>
  );
};
