import { useEffect, useRef, type ReactNode } from 'react';
import { useResource } from '../hooks/useResource';
import { getGap } from '../services/gaps';
import type { Gap, GapDetail } from '../types/api';
import { date, dateTime, humanize, pct, tidyText, valueText } from '../utils/format';
import { gapClass, gapImpact } from '../utils/gapClass';
import { ErrorState, Loading, Pill } from './ui';

/**
 * The whole gap (GET /gaps/{id}): description, source quote and location, competing values of a contradiction,
 * evidence state, responsibility and history. `actions` renders the settle buttons for the loaded gap.
 * Same layout as the full-fact view (FactDetailDialog).
 */
export function GapDetailDialog({ gap, onClose, actions }: {
  gap: Gap;
  onClose: () => void;
  actions?: (gap: GapDetail) => ReactNode;
}) {
  const detail = useResource<GapDetail>(() => getGap(gap.id), `gap:${gap.id}`);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
  }, []);

  const g = detail.data;
  return (
    <dialog ref={ref} className="action-dialog fact-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="gap-title">
      <div className="fact-dialog-body">
        <div className="fact-dialog-head">
          <div>
            <span className="eyebrow">{gap.pillar_label || 'Gap'}</span>
            <h2 id="gap-title">{gap.title}</h2>
          </div>
          <button className="notice-close" aria-label="Close" onClick={onClose}>×</button>
        </div>

        {detail.loading && !g ? <Loading label="Loading the gap…" /> : detail.error ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : g && (
          <>
            <section className="fact-section">
              <h3>Why it matters</h3>
              <p className="fact-value">{tidyText(g.description) || '—'}</p>
              <div className="fact-meta">
                <Pill status={g.priority} label={gapImpact(g.priority)} />
                <Pill status={g.status} />
                <span>{gapClass(g.gap_type)}</span>
                <span>{humanize(g.gap_type)}</span>
                <span>−{g.score_impact} CRI points</span>
              </div>
            </section>

            {(g.source_document_filename || g.source_snippet) && (
              <section className="fact-section">
                <h3>Source</h3>
                <p>{g.source_document_filename || 'No source document'}{g.source_page && `, page ${g.source_page}`}</p>
                {g.source_snippet && <blockquote>{tidyText(g.source_snippet)}</blockquote>}
              </section>
            )}

            {g.conflict_candidates && g.conflict_candidates.length > 0 && (
              <section className="fact-section">
                <h3>Competing values</h3>
                <ul className="gap-sides">
                  {g.conflict_candidates.map((c) => (
                    <li key={c.side}>
                      <b>{c.side}</b>
                      <div>
                        <span className="fact-value">{valueText(c.current_value ?? c.value_at_detection)}</span>
                        <span className="cell-sub">
                          {c.document_name || 'No document'}{c.page && `, page ${c.page}`}
                          {c.confidence_score != null && ` · confidence ${pct(c.confidence_score)}`} · {humanize(c.fact_status)}
                        </span>
                        {c.snippet && <blockquote>{tidyText(c.snippet)}</blockquote>}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {g.evidence_state && (
              <section className="fact-section">
                <h3>Evidence</h3>
                <p><Pill status={g.evidence_state.state} label={g.evidence_state.label} /></p>
                {g.evidence_state.reason && <p className="muted">{g.evidence_state.reason}</p>}
                {g.evidence_state.next_action && <p>Next: {g.evidence_state.next_action}</p>}
              </section>
            )}

            <section className="fact-section">
              <h3>Responsibility</h3>
              <dl className="kv">
                <dt>Owner role</dt><dd>{g.owner_role_label || humanize(g.owner_role)}</dd>
                <dt>Assigned to</dt><dd>{g.assigned_to_name || 'Unassigned'}</dd>
                <dt>Due</dt><dd>{date(g.due_date)}</dd>
                {g.resolution && <><dt>Resolution</dt><dd>{tidyText(g.resolution)}</dd></>}
              </dl>
            </section>

            <section className="fact-section">
              <h3>History</h3>
              {!g.events?.length ? <p className="muted">No actions yet.</p> : (
                <ol className="fact-history">
                  {g.events.map((e) => (
                    <li key={e.id}>
                      <b>{e.action_label || humanize(e.action)}</b> by {e.user_name || 'the system'} · {dateTime(e.created_at)}
                      {e.note && <span className="cell-sub">{tidyText(e.note)}</span>}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </div>
      <div className="button-row dialog-actions fact-dialog-foot">
        {g && actions?.(g)}
        <button className="secondary-button" onClick={onClose}>Close</button>
      </div>
    </dialog>
  );
}
