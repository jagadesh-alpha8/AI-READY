/** Display helpers. They never turn a missing value into a number: null stays an em dash. */

export const DASH = '—';

export function num(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === '') return DASH;
  const n = typeof value === 'string' ? Number(value) : value;
  return Number.isFinite(n) ? n.toFixed(digits) : DASH;
}

/** 0.81 or 81 -> "81%". Ratios (<= 1) are scaled; the backend sends confidences both ways. */
export function pct(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === '') return DASH;
  const n = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(n)) return DASH;
  return `${(n <= 1 ? n * 100 : n).toFixed(digits)}%`;
}

export function date(value: string | null | undefined): string {
  if (!value) return DASH;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** snake_case -> "Snake case". */
export function humanize(value: string | null | undefined): string {
  if (!value) return DASH;
  const s = value.replace(/_/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Any fact value as one line of text. */
export function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return DASH;
  if (Array.isArray(value)) return value.map(valueText).join(', ');
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

/** Extracted text keeps its line breaks, but runs of blank lines (common in PDF extraction) become one break. */
export function tidyText(text: string | null | undefined): string {
  return (text || '').replace(/\r/g, '').replace(/[ \t]+\n/g, '\n').replace(/\n{2,}/g, '\n').trim();
}

export function initials(name: string | null | undefined): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** Tone for a status pill. */
export type Tone = 'good' | 'warn' | 'bad' | 'neutral';

const GOOD = new Set(['confirmed', 'corrected', 'processed', 'completed', 'complete', 'ready', 'accepted', 'accepted_corrected',
  'approved', 'resolved', 'strong', 'finalized', 'verified', 'applies', 'met', 'closed', 'validated']);
const WARN = new Set(['extracted', 'pending', 'processing', 'uploaded', 'running', 'retrying', 'generating', 'draft', 'open',
  'submitted', 'ready_for_review', 'in_progress', 'developing', 'provisional', 'needs_review', 'requires_review', 'optional',
  'planned', 'active', 'returned', 'evidence_requested', 'reviewed', 'not_started', 'medium', 'high']);
const BAD = new Set(['failed', 'rejected', 'blocking', 'critical', 'at_risk', 'overdue', 'blocked', 'conflict',
  'invalid', 'conflicting', 'does_not_apply', 'cancelled']);

export function tone(status: string | null | undefined): Tone {
  const s = (status || '').toLowerCase();
  if (GOOD.has(s)) return 'good';
  if (BAD.has(s)) return 'bad';
  if (WARN.has(s)) return 'warn';
  return 'neutral';
}

/** A list endpoint answers a plain array, or a page when ?page was sent. */
export function rows<T>(data: T[] | { results: T[] } | null | undefined): T[] {
  if (!data) return [];
  return Array.isArray(data) ? data : data.results;
}
