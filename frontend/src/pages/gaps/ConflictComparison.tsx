import React, { useEffect } from 'react';
import { X } from 'lucide-react';

import type { Gap } from '../../types';
import { describeSide } from './conflictSides.ts';

/**
 * The two sides of a conflict gap, next to each other on wide screens and stacked on narrow ones. Every
 * value is rendered as React text (escaped) -- source snippets are document text, never markup.
 */
export const ConflictComparison: React.FC<{ gap: Gap }> = ({ gap }) => {
  const sides = (gap.conflict_sides || []).map(describeSide);
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

/** The comparison in a dialog, opened from a conflict row of the Gap Dashboard (Escape or X closes it). */
export const ConflictComparisonDialog: React.FC<{ gap: Gap; onClose: () => void }> = ({ gap, onClose }) => {
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
        <ConflictComparison gap={gap} />
      </div>
    </div>
  );
};
