import { useEffect, useRef, type ReactNode } from 'react';
import { useResource } from '../hooks/useResource';
import { getFact } from '../services/facts';
import type { Fact, FactDetail } from '../types/api';
import { dateTime, humanize, pct, tidyText as tidy, valueText } from '../utils/format';
import { ErrorState, Loading, Pill } from './ui';

/**
 * The whole fact (GET /facts/{id}): full value, source quote and location, verification, AI-QIF tags and the
 * review history. `actions` renders the decision buttons for the loaded fact (review page only).
 */
export function FactDetailDialog({ fact, onClose, actions }: {
  fact: Fact;
  onClose: () => void;
  actions?: (fact: FactDetail) => ReactNode;
}) {
  const detail = useResource<FactDetail>(() => getFact(fact.id), `fact:${fact.id}`);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
  }, []);

  const f = detail.data;
  return (
    <dialog ref={ref} className="action-dialog fact-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="fact-title">
      <div className="fact-dialog-body">
        <div className="fact-dialog-head">
          <div>
            <span className="eyebrow">{fact.pillar_label || 'Extracted fact'}</span>
            <h2 id="fact-title">{fact.field_name}</h2>
          </div>
          <button className="notice-close" aria-label="Close" onClick={onClose}>×</button>
        </div>

        {detail.loading && !f ? <Loading label="Loading the fact…" /> : detail.error ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : f && (
          <>
            <section className="fact-section">
              <h3>Value</h3>
              <p className="fact-value">{tidy(valueText(f.value))}</p>
              <div className="fact-meta">
                <Pill status={f.status} />
                {f.verification && <Pill status={f.verification.status} label={f.verification.status_label} />}
                <span>Confidence {pct(f.confidence_score)}</span>
                {f.data_type && <span>{humanize(f.data_type)}</span>}
              </div>
              {f.confidence_reason && <p className="muted">{f.confidence_reason}</p>}
            </section>

            <section className="fact-section">
              <h3>Source</h3>
              <p>{f.source_document_filename || 'No source document'}{f.source_page && `, page ${f.source_page}`}</p>
              {f.source_snippet ? <blockquote>{tidy(f.source_snippet)}</blockquote> : <p className="muted">No quote was recorded for this fact.</p>}
            </section>

            {f.aiqif_mappings.length > 0 && (
              <section className="fact-section">
                <h3>AI-QIF indicators</h3>
                <ul className="plain-list">
                  {f.aiqif_mappings.map((m) => (
                    <li key={m.indicator_code}><b>{m.indicator_code}</b> {m.indicator_name} · {pct(m.confidence)} · {humanize(m.status)}</li>
                  ))}
                </ul>
              </section>
            )}

            <section className="fact-section">
              <h3>Review history</h3>
              {f.review_history.length === 0 ? <p className="muted">No decisions yet.</p> : (
                <ol className="fact-history">
                  {f.review_history.map((h) => (
                    <li key={h.id}>
                      <b>{humanize(h.action)}</b> by {h.user_name || 'the system'} · {dateTime(h.created_at)}
                      {h.reason && <span className="cell-sub">{h.reason}</span>}
                      {h.action === 'corrected' && <span className="cell-sub">{valueText(h.original_value)} → {valueText(h.new_value)}</span>}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </div>
      <div className="button-row dialog-actions fact-dialog-foot">
        {f && actions?.(f)}
        <button className="secondary-button" onClick={onClose}>Close</button>
      </div>
    </dialog>
  );
}
