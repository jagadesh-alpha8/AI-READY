/**
 * What the conflict comparison shows for each side, worked out from the API's `conflict_sides`
 * (apps/gaps/serializers.py). Pure functions with no React, so `npm test` can run them on Node directly.
 * Anything not recorded shows as "Not available" -- never a guess.
 */
import type { ConflictSide } from '../../types/gaps.ts';

export const NOT_AVAILABLE = 'Not available';

export interface SideRow {
  label: string;
  value: string;
  /** True when nothing was recorded (shown muted). */
  missing: boolean;
  /** Render in a monospace face (values) / as a quotation (snippets). */
  kind?: 'value' | 'quote';
}

export interface SideView {
  heading: string;
  /** The fact this side is (for a link), or null when the gap has no fact on this side. */
  factId: string | null;
  rows: SideRow[];
  /** A note under the value: it changed since detection, or no snapshot was stored. */
  valueNote: string;
}

const isMissing = (v: unknown) => v === null || v === undefined || (typeof v === 'string' && v.trim() === '');

export function formatValue(v: unknown): string {
  if (isMissing(v)) return NOT_AVAILABLE;
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}

function row(label: string, v: unknown, kind?: SideRow['kind']): SideRow {
  return { label, value: formatValue(v), missing: isMissing(v), kind };
}

export function describeSide(side: ConflictSide): SideView {
  const snapshot = side.value_at_detection;
  const current = side.current_value;
  // The value the conflict was found on; without a stored snapshot, the fact's own (current) value.
  const shown = isMissing(snapshot) ? current : snapshot;
  let valueNote = '';
  if (isMissing(snapshot) && !isMissing(current)) {
    valueNote = 'Current value of the fact; no value was stored when the conflict was found.';
  } else if (!isMissing(snapshot) && side.fact_id && JSON.stringify(snapshot) !== JSON.stringify(current)) {
    valueNote = `The fact has changed since: now ${formatValue(current)}.`;
  }
  const confidence = typeof side.confidence_score === 'number'
    ? `${Math.round(side.confidence_score * 100)}%` : null;
  return {
    heading: `Source ${side.side}${side.field_name ? ` · ${side.field_name}` : ''}`,
    factId: side.fact_id,
    rows: [
      row('Extracted value', shown, 'value'),
      row('Source document', side.document_name),
      // Recorded by the verification pipeline; shown only when the API sends them.
      ...(side.document_version !== undefined
        ? [row('Version', side.document_version ? `v${side.document_version}${side.superseded ? ' (superseded)' : ''}` : null)] : []),
      row('Page', side.page),
      ...(side.period !== undefined ? [row('Period', side.period)] : []),
      ...(side.population !== undefined ? [row('Population', side.population?.length ? side.population.join(', ') : null)] : []),
      row('Snippet', side.snippet, 'quote'),
      row('Confidence', confidence),
      ...(side.validation_status !== undefined
        ? [row('Checks', side.validation_status ? `${side.validation_status}${side.grounding_status ? ` · quote ${side.grounding_status.replace(/_/g, ' ')}` : ''}` : null)] : []),
    ],
    valueNote,
  };
}
