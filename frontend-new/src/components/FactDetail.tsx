import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { assignFact, getFact, getFactVerification, listFactCorrections, proposeCorrection } from '../services/facts';
import { listEvidenceAssignees } from '../services/evidenceRequests';
import type { CorrectionProposal, EvidenceAssignee, FactVerificationDetail } from '../types/workflow';
import type { Fact, FactDetail } from '../types/api';
import { dateTime, humanize, pct, tidyText as tidy, valueText } from '../utils/format';
import { ActionDialog, ErrorState, Loading, Notice, Pill } from './ui';

/**
 * The whole fact (GET /facts/{id}): full value, source quote and location, verification, AI-QIF tags and the
 * review history. `actions` renders the decision buttons for the loaded fact (review page only).
 */
export function FactDetailDialog({ fact, onClose, actions }: {
  fact: Fact;
  onClose: () => void;
  actions?: (fact: FactDetail) => ReactNode;
}) {
  const { can } = useAccess();
  const detail = useResource<FactDetail>(() => getFact(fact.id), `fact:${fact.id}`);
  const verification = useResource<FactVerificationDetail>(() => getFactVerification(fact.id), `fv:${fact.id}`);
  const corrections = useResource<CorrectionProposal[]>(() => listFactCorrections(fact.id), `fc:${fact.id}`);
  const assignees = useResource<EvidenceAssignee[]>(() => listEvidenceAssignees(fact.sprint_id), `assignees:${fact.sprint_id}`, can('sprint.manage'));
  const [form, setForm] = useState<'assign' | 'propose' | null>(null);
  const [msg, setMsg] = useState('');
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

            {verification.data?.latest && (
              <section className="fact-section">
                <h3>Verification ({humanize(verification.data.mode)} mode)</h3>
                <div className="fact-meta">
                  <Pill status={verification.data.latest.outcome === 'verified' ? 'active' : 'pending'} label={humanize(verification.data.latest.outcome)} />
                  <span>Risk {humanize(verification.data.latest.risk_level)}</span>
                  <span>{humanize(verification.data.latest.automation_decision)}</span>
                </div>
                <p className="muted">{verification.data.latest.reason}{verification.data.latest.automation_reason && ` · ${verification.data.latest.automation_reason}`}</p>
                <ul className="plain-list">
                  <li>Grounding: {humanize(verification.data.latest.grounding.status)}{verification.data.latest.grounding.value_support && ` · ${humanize(verification.data.latest.grounding.value_support)}`}</li>
                  {verification.data.latest.validation.checks.map((c) => <li key={c.code}>{c.label}: {humanize(c.status)}{c.detail && ` · ${c.detail}`}</li>)}
                  <li>Other sources: {humanize(verification.data.latest.cross_source.status)} ({verification.data.latest.cross_source.compared.filter((x) => x.agrees).length} of {verification.data.latest.cross_source.compared.length} agree)</li>
                  {verification.data.latest.blockers.map((b) => <li key={b}>Blocker: {b}</li>)}
                </ul>
              </section>
            )}

            {!!corrections.data?.length && (
              <section className="fact-section">
                <h3>Proposed corrections</h3>
                <ul className="plain-list">
                  {corrections.data.map((c) => (
                    <li key={c.id}><Pill status={c.status} /> {valueText(c.value_before)} → <b>{valueText(c.proposed_value)}</b> · {c.submitted_by_name} · {dateTime(c.created_at)}{c.reason && <span className="cell-sub">{tidy(c.reason)}</span>}</li>
                  ))}
                </ul>
                <p className="muted">A different reviewer decides these in Verification & corrections.</p>
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
      {msg && <div className="fact-dialog-body"><Notice tone="success" onClose={() => setMsg('')}>{msg}</Notice></div>}
      <div className="button-row dialog-actions fact-dialog-foot">
        {f && actions?.(f)}
        {f && (
          <div className="row-actions">
            {can('sprint.manage') && <button className="secondary-button" onClick={() => setForm('assign')}>Assign</button>}
            {can('facts.review') && <button className="secondary-button" onClick={() => setForm('propose')}>Propose correction</button>}
          </div>
        )}
        <button className="secondary-button" onClick={onClose}>Close</button>
      </div>
      {form === 'assign' && (
        <ActionDialog title={`Assign: ${fact.field_name}`} confirmLabel="Assign"
          fields={[
            { name: 'assigned_to', label: 'Assign to (blank = unassign)', type: 'select', options: (assignees.data || []).map((a) => ({ value: a.id, label: `${a.name} · ${a.role}` })) },
            { name: 'due_date', label: 'Due date', type: 'date' },
            { name: 'note', label: 'Note', type: 'textarea' },
          ]}
          onSubmit={async (v) => { await assignFact(fact.id, v.assigned_to || null, v.due_date || null, v.note); setMsg(v.assigned_to ? 'Fact assigned.' : 'Fact unassigned.'); await detail.refetch(); }}
          onClose={() => setForm(null)} />
      )}
      {form === 'propose' && (
        <ActionDialog title="Propose a correction" confirmLabel="Propose"
          description="The proposed value waits for a different reviewer; the fact keeps its value until then."
          fields={[
            { name: 'value', label: 'Correct value', required: true },
            { name: 'reason', label: 'Reason', type: 'textarea', required: true },
            { name: 'source_page', label: 'Source page', initial: f?.source_page || '' },
            { name: 'source_snippet', label: 'Quote that supports it', type: 'textarea' },
          ]}
          onSubmit={async (v) => {
            await proposeCorrection(fact.id, { value: v.value, reason: v.reason, source_document_id: f?.source_document_id || null, source_page: v.source_page, source_snippet: v.source_snippet });
            setMsg('Correction proposed.');
            await corrections.refetch();
          }}
          onClose={() => setForm(null)} />
      )}
    </dialog>
  );
}
