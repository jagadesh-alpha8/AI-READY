import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';

import { chooseConflictValue, getGap } from '../../api/gaps';
import { InlineError } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import type { Gap } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { describeSide } from './conflictSides.ts';
import { promptDialog } from '../../components/Dialog';

/**
 * The two sides of a conflict gap, next to each other on wide screens and stacked on narrow ones. Every
 * value is rendered as React text (escaped) -- source snippets are document text, never markup.
 */
export const ConflictComparison: React.FC<{
  gap: Gap;
  /** The owner / a Super Admin: a "Use this value" button under each side. */
  onChoose?: (factId: string) => void;
  busy?: boolean;
}> = ({ gap, onChoose, busy }) => {
  // The detail lists every competing value; the list row only its recorded sides.
  const sides = (gap.conflict_candidates || gap.conflict_sides || []).map(describeSide);
  return (
    <div className="space-y-2">
      {gap.description && <p className="text-xs text-ink-600">{gap.description}</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {sides.map((side) => (
          <section key={side.heading} className="border border-line-200 rounded-lg p-3 bg-card"
            aria-label={side.heading}>
            <h4 className="text-xs font-bold text-ink-900 mb-2">{side.heading}</h4>
            <dl className="grid grid-cols-[7.5rem_1fr] gap-x-3 gap-y-1.5 text-xs">
              {side.rows.map((r) => (
                <React.Fragment key={r.label}>
                  <dt className="text-ink-500">{r.label}</dt>
                  <dd className={`min-w-0 break-words whitespace-pre-wrap ${r.missing ? 'text-ink-400 italic'
                    : r.kind === 'value' ? 'font-mono font-semibold text-ink-900'
                      : r.kind === 'quote' ? 'italic text-ink-700' : 'text-ink-800'}`}>
                    {r.kind === 'quote' && !r.missing ? `“${r.value}”` : r.value}
                    {r.label === 'Extracted value' && side.valueNote && (
                      <span className="block not-italic font-sans font-normal text-[11px] text-ink-500">{side.valueNote}</span>
                    )}
                  </dd>
                </React.Fragment>
              ))}
            </dl>
            {onChoose && side.factId && (
              <button type="button" className="btn-primary btn-sm mt-3" disabled={busy} onClick={() => onChoose(side.factId!)}>
                Use this value
              </button>
            )}
          </section>
        ))}
      </div>
      {typeof gap.conflict_confidence === 'number' && (
        <p className="text-[11px] text-ink-500">
          Conflict check confidence: {Math.round(gap.conflict_confidence * 100)}%
        </p>
      )}
    </div>
  );
};

/** The comparison in a dialog, opened from a conflict row of the Gap Dashboard (Escape or X closes it). The gap's
 * owner role -- or a Super Admin -- chooses the correct value there: that fact is confirmed, the competing values
 * are rejected and the conflict closes. */
export const ConflictComparisonDialog: React.FC<{ gap: Gap; onClose: () => void; onResolved?: () => void }> = ({
  gap: listed, onClose, onResolved,
}) => {
  const { data: detail } = useApiResource<Gap>(() => getGap(listed.id), [listed.id]);
  const gap = detail || listed;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const choose = async (factId: string) => {
    const side = (gap.conflict_candidates || []).find((c) => c.fact_id === factId);
    const reason = await promptDialog(
      `Use ${JSON.stringify(side?.current_value)} from ${side?.document_name || 'this document'} as the correct value? `
      + 'It is confirmed, the other values are rejected and the conflict closes. Reason (optional):',
      { title: 'Choose the correct value', confirmLabel: 'Use this value' });
    if (reason === null) return;
    setBusy(true); setError('');
    try {
      await chooseConflictValue(gap.id, factId, reason);
      onResolved?.();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, 'The conflict could not be resolved.'));
    } finally { setBusy(false); }
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog"
      aria-modal="true" aria-labelledby={`conflict-title-${gap.id}`} onClick={onClose}>
      <div className="glass-card w-full max-w-4xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id={`conflict-title-${gap.id}`} className="text-base font-bold text-ink-900">{gap.title}</h2>
            <p className="text-xs text-ink-500 mt-0.5">
              Conflict gap · {gap.status.replace(/_/g, ' ')} · {gap.priority}
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        {error && <InlineError message={error} onDismiss={() => setError('')} />}
        <ConflictComparison gap={gap} onChoose={gap.can_choose_value ? choose : undefined} busy={busy} />
        {detail && !detail.can_choose_value && detail.choose_value_blocked_reason && (
          <p className="text-xs text-ink-500">{detail.choose_value_blocked_reason}</p>
        )}
      </div>
    </div>
  );
};
