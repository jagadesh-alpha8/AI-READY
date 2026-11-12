import { useEffect, useRef, useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import {
  assignEvidenceRequest, commentOnEvidenceRequest, getEvidenceRequest, listEvidenceAssignees, retryEvidenceAssessment,
  reviewEvidenceRequest,
} from '../services/evidenceRequests';
import type { EvidenceAssignee, EvidenceDecision, EvidenceRequestDetail } from '../types/workflow';
import { errorMessage } from '../utils/errors';
import { date, dateTime, humanize, tidyText, valueText } from '../utils/format';
import { ActionDialog, ErrorState, Loading, Notice, Pill, type DialogField } from './ui';

const DECISIONS: { value: EvidenceDecision; label: string }[] = [
  { value: 'accept', label: 'Accept: the evidence supports the fact' },
  { value: 'accept_corrected', label: 'Accept with a corrected value' },
  { value: 'return', label: 'Return: more information needed' },
  { value: 'reject', label: 'Reject this submission' },
  { value: 'withdraw', label: 'Withdraw the request' },
];
/** Statuses a reviewer can decide on (backend EvidenceRequestReviewView). */
const REVIEWABLE = new Set(['submitted', 'ready_for_review', 'processing']);

/**
 * One evidence request in full (GET /evidence-requests/{id}): what is needed, every submission with its advisory AI
 * check, and the history. Coordinators assign; anyone in scope comments; a reviewer other than the submitter decides.
 */
export function EvidenceRequestDialog({ id, sprintId, onClose, onChanged }: {
  id: string; sprintId: string; onClose: () => void; onChanged: () => void;
}) {
  const { can, user } = useAccess();
  const detail = useResource<EvidenceRequestDetail>(() => getEvidenceRequest(id), `er:${id}`);
  const assignees = useResource<EvidenceAssignee[]>(() => listEvidenceAssignees(sprintId), `assignees:${sprintId}`, can('sprint.manage'));
  const [form, setForm] = useState<'assign' | 'comment' | 'review' | null>(null);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
  }, []);

  const r = detail.data;
  const changed = async (text: string) => {
    setMsg({ tone: 'success', text });
    await detail.refetch();
    onChanged();
  };
  const ownSubmission = !!r?.evidence.some((e) => e.submitted_by_name && e.submitted_by_name === user?.name);

  const reviewFields: DialogField[] = [
    { name: 'decision', label: 'Decision', type: 'select', required: true, options: DECISIONS },
    { name: 'evidence_id', label: 'Submission', type: 'select', options: (r?.evidence || []).map((e) => ({ value: e.id, label: `${e.document_filename || 'Text'} · ${dateTime(e.created_at)}` })), initial: r?.evidence[0]?.id || '' },
    { name: 'corrected_value', label: 'Corrected value (for "accept with a corrected value")', type: 'text' },
    { name: 'reason', label: 'Reason', type: 'textarea', required: true },
  ];

  return (
    <dialog ref={ref} className="action-dialog fact-dialog" onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="er-title">
      <div className="fact-dialog-body">
        <div className="fact-dialog-head">
          <div>
            <span className="eyebrow">Evidence request</span>
            <h2 id="er-title">{r?.fact_field_name || 'Loading…'}</h2>
          </div>
          <button className="notice-close" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
        {detail.loading && !r ? <Loading /> : detail.error ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : r && (
          <>
            <section className="fact-section">
              <h3>What is needed</h3>
              <p>{tidyText(r.evidence_needed) || '—'}</p>
              <div className="fact-meta">
                <Pill status={r.status} label={r.status_label} />
                {r.overdue && <Pill status="overdue" label="Overdue" />}
                <span>Current value: {valueText(r.fact_value)}</span>
              </div>
              {r.reason && <p className="muted">{tidyText(r.reason)}</p>}
              {r.fact_source_snippet && <blockquote>{tidyText(r.fact_source_snippet)}<cite>{r.fact_source_page && `page ${r.fact_source_page}`}</cite></blockquote>}
            </section>
            <section className="fact-section">
              <h3>Responsibility</h3>
              <dl className="kv">
                <dt>Responsible role</dt><dd>{humanize(r.responsible_role)}</dd>
                <dt>Assigned to</dt><dd>{r.assigned_to_name || 'Unassigned'}</dd>
                <dt>Due</dt><dd>{date(r.due_date)}</dd>
                {r.resolution_note && <><dt>Resolution</dt><dd>{tidyText(r.resolution_note)}</dd></>}
              </dl>
            </section>
            <section className="fact-section">
              <h3>Submissions ({r.evidence.length})</h3>
              {!r.evidence.length ? <p className="muted">Nothing submitted yet.</p> : r.evidence.map((e) => (
                <article key={e.id} className="condition">
                  <div><Pill status={e.status} /> <b>{e.document_filename || 'Text response'}</b> · {e.submitted_by_name} · {dateTime(e.created_at)}</div>
                  {e.submitted_text && <p>{tidyText(e.submitted_text)}</p>}
                  {e.note && <p className="muted">Note: {tidyText(e.note)}</p>}
                  <p className="muted">
                    AI check (advisory): {humanize(e.analysis_status)}{e.analysis_outcome && ` · ${humanize(e.analysis_outcome)}`}
                    {e.analysis_error && ` · ${e.analysis_error}`}
                  </p>
                  {e.analysis_summary && <p>{tidyText(e.analysis_summary)}</p>}
                  {e.analysis_quote && <blockquote>{tidyText(e.analysis_quote)}</blockquote>}
                  {e.review_reason && <p className="muted">Reviewer: {tidyText(e.review_reason)}</p>}
                  {e.analysis_status === 'failed' && (
                    <button className="secondary-button" onClick={() => void retryEvidenceAssessment(r.id, e.id)
                      .then(() => changed('AI check queued again.')).catch((err) => setMsg({ tone: 'error', text: errorMessage(err) }))}>
                      Retry AI check
                    </button>
                  )}
                </article>
              ))}
            </section>
            <section className="fact-section">
              <h3>History</h3>
              {!r.events.length ? <p className="muted">No actions yet.</p> : (
                <ol className="fact-history">
                  {r.events.map((e) => (
                    <li key={e.id}><b>{e.action_label}</b> by {e.user_name || 'the system'} · {dateTime(e.created_at)}{e.note && <span className="cell-sub">{tidyText(e.note)}</span>}</li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </div>
      <div className="button-row dialog-actions fact-dialog-foot">
        {r && (
          <div className="row-actions">
            {can('sprint.manage') && <button className="secondary-button" onClick={() => setForm('assign')}>Assign</button>}
            <button className="secondary-button" onClick={() => setForm('comment')}>Comment</button>
            {can('facts.review') && REVIEWABLE.has(r.status) && r.evidence.length > 0 && (
              <button className="primary-action" disabled={ownSubmission} title={ownSubmission ? 'A different person reviews your own submission' : ''} onClick={() => setForm('review')}>Review</button>
            )}
          </div>
        )}
        <button className="secondary-button" onClick={onClose}>Close</button>
      </div>
      {form === 'assign' && r && (
        <ActionDialog title="Assign this request" confirmLabel="Assign"
          fields={[
            { name: 'assigned_to', label: 'Assign to', type: 'select', required: true, options: (assignees.data || []).map((a) => ({ value: a.id, label: `${a.name} · ${a.role}` })) },
            { name: 'note', label: 'Note', type: 'textarea' },
          ]}
          onSubmit={async (v) => { await assignEvidenceRequest(r.id, v.assigned_to, v.note); await changed('Request assigned.'); }}
          onClose={() => setForm(null)} />
      )}
      {form === 'comment' && r && (
        <ActionDialog title="Add a comment" confirmLabel="Comment"
          fields={[{ name: 'note', label: 'Comment', type: 'textarea', required: true }]}
          onSubmit={async (v) => { await commentOnEvidenceRequest(r.id, v.note); await changed('Comment added.'); }}
          onClose={() => setForm(null)} />
      )}
      {form === 'review' && r && (
        <ActionDialog title="Review the evidence" confirmLabel="Record decision" fields={reviewFields}
          onSubmit={async (v) => {
            const decision = v.decision as EvidenceDecision;
            if (decision === 'accept_corrected' && !v.corrected_value.trim()) throw new Error('Enter the corrected value.');
            await reviewEvidenceRequest(r.id, {
              decision, evidence_id: v.evidence_id || undefined, reason: v.reason,
              corrected_value: decision === 'accept_corrected' ? v.corrected_value : undefined,
            });
            await changed('Decision recorded.');
          }}
          onClose={() => setForm(null)} />
      )}
    </dialog>
  );
}
