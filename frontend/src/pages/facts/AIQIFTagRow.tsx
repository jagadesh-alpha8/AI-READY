import React, { useState } from 'react';

import { editFactMapping, reopenFactMapping, reviewFactMapping } from '../../api/facts';
import type { AIQIFMapping, Fact } from '../../types';
import { getErrorMessage } from '../../utils/errors';

type Relationship = 'direct' | 'supporting' | 'contextual';
type Indicator = { code: string; criterion: string; name: string };

const shortCode = (code: string) => code.replace(/^AIQIF-/, '');
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '');

/** The fact's own review state -- separate from its tags' decisions. */
export const FactReviewState: React.FC<{ fact: Fact }> = ({ fact }) => {
  const label = fact.status === 'confirmed' ? (fact.auto_confirmed ? 'Fact confirmed automatically' : 'Fact confirmed')
    : fact.status === 'corrected' ? 'Fact corrected'
      : fact.status === 'rejected' ? 'Fact rejected'
        : fact.status === 'evidence_requested' ? 'Fact waiting for evidence' : 'Fact not yet reviewed';
  const ok = fact.status === 'confirmed' || fact.status === 'corrected';
  return <p className={`text-[11px] ${ok ? 'text-success' : 'text-ink-500'}`}>{label}</p>;
};

/**
 * One AI-QIF tag for the AI-QIF expert (Super Admin): the tag's decision (who, when), its relationship, whether it
 * counts toward coverage now and why not, and the actions -- Confirm, Reject, Edit (a new indicator or relationship
 * never keeps the old approval: decide it now or leave it pending), Reopen (back to the expert queue, the earlier
 * decision kept in history). Tag decisions never change the fact itself. Backend apps/facts/aiqif_tagging.py.
 */
export const AIQIFTagRow: React.FC<{
  fact: Fact;
  mapping: AIQIFMapping;
  indicators: Indicator[];
  onChanged?: () => void;
  onError?: (message: string) => void;
  /** Extracted Facts Review: the decision and counting state only; changes happen in the AI-QIF expert queue. */
  readOnly?: boolean;
}> = ({ fact, mapping: m, indicators, onChanged = () => {}, onError = () => {}, readOnly = false }) => {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ code: m.indicator_code, relationship: m.relationship as Relationship, note: '',
    decision: '' as '' | 'confirm' | 'reject' });

  const run = async (call: () => Promise<unknown>, failure: string) => {
    setBusy(true);
    try { await call(); setEditing(false); onChanged(); } catch (err) { onError(getErrorMessage(err, failure)); }
    finally { setBusy(false); }
  };
  const review = (decision: 'confirm' | 'reject') =>
    run(() => reviewFactMapping(fact.id, m.indicator_code, decision), 'The tag decision could not be saved.');
  const reopen = () => {
    const reason = window.prompt(`Why reopen the review of ${shortCode(m.indicator_code)}? (kept in the history)`, '');
    if (!reason || !reason.trim()) return;
    run(() => reopenFactMapping(fact.id, m.indicator_code, reason.trim()), 'The review could not be reopened.');
  };
  const save = () => run(() => editFactMapping(fact.id, m.indicator_code, {
    indicator_code: form.code !== m.indicator_code ? form.code : undefined,
    relationship: form.relationship !== m.relationship ? form.relationship : undefined,
    note: form.note.trim(), decision: form.decision || undefined,
  }), 'The mapping could not be changed.');
  const changesMapping = form.code !== m.indicator_code || form.relationship !== m.relationship;

  const decided = m.review_status !== 'unreviewed';
  const autoRejected = m.auto_decision === 'rejected_precedent';
  const canReopen = !m.pending && (decided || m.auto_accepted || autoRejected);
  return (
    <div className="space-y-0.5" title={`${m.criterion_code} ${m.criterion_name}\n${m.indicator_code} ${m.indicator_name}\n\nWhy: ${m.reason}`}>
      <div className="flex items-start gap-1.5">
        <span className="font-mono text-[11px] font-bold text-brand-800 shrink-0 mt-px">{shortCode(m.indicator_code)}</span>
        <span className="text-xs font-semibold text-ink-800 leading-snug">{m.indicator_name}</span>
        <span className="ml-auto shrink-0 badge-neutral">{m.relationship}</span>
      </div>
      <p className="text-[11px]">
        {m.review_status === 'confirmed' && <span className="font-semibold text-success">Tag confirmed{m.reviewed_by_name ? ` by ${m.reviewed_by_name}` : ''}{m.reviewed_at ? ` · ${when(m.reviewed_at)}` : ''}</span>}
        {m.review_status === 'rejected' && <span className="font-semibold text-danger">Tag rejected{m.reviewed_by_name ? ` by ${m.reviewed_by_name}` : ''}{m.reviewed_at ? ` · ${when(m.reviewed_at)}` : ''}</span>}
        {!decided && m.pending && (
          <span className="font-semibold text-warning">
            Pending expert review{m.pending_since ? ` · ${m.pending_by_name ? `reopened by ${m.pending_by_name} ` : ''}${when(m.pending_since)}` : ''}
            {m.pending_reason ? ` — ${m.pending_reason}` : ''}
          </span>
        )}
        {!decided && !m.pending && autoRejected && (
          <span className="font-semibold text-danger">Rejected automatically (earlier expert decision)</span>
        )}
        {!decided && !m.pending && !autoRejected && (
          <span className="text-ink-500">
            Accepted automatically ({m.auto_decision === 'accepted_precedent' ? 'earlier expert decision'
              : m.auto_decision === 'accepted_ai_check' ? 'AI second opinion'
                : m.source === 'crosswalk' ? `NAAC crosswalk ${m.framework_version}` : `AI ${Math.round(m.confidence * 100)}%`})
          </span>
        )}
      </p>
      {m.auto_reason && !decided && <p className="text-[11px] text-ink-500">{m.auto_reason}</p>}
      <p className={`text-[11px] ${m.counts ? 'text-success font-semibold' : 'text-ink-500'}`}>
        {m.counts ? 'Counts toward coverage' : `Does not count: ${m.counts_reason}`}
      </p>
      {m.review_note && decided && <p className="text-[11px] text-ink-500">Note: {m.review_note}</p>}
      {readOnly ? null : !editing ? (
        <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
          {m.review_status !== 'confirmed' && <button disabled={busy} className="text-success hover:underline disabled:opacity-50" onClick={() => review('confirm')}>✓ Confirm</button>}
          {m.review_status !== 'rejected' && <button disabled={busy} className="text-danger hover:underline disabled:opacity-50" onClick={() => review('reject')}>✕ Reject</button>}
          <button disabled={busy} className="text-brand-800 hover:underline disabled:opacity-50" onClick={() => setEditing(true)}>Edit mapping</button>
          {canReopen && <button disabled={busy} className="text-ink-600 hover:underline disabled:opacity-50" onClick={reopen}>Reopen review</button>}
        </div>
      ) : (
        <div className="space-y-1 rounded border border-line-200 p-2 text-[11px]">
          <select className="input text-xs py-1 w-full" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })}>
            {indicators.map((i) => <option key={i.code} value={i.code}>{shortCode(i.code)} {i.name}</option>)}
          </select>
          <div className="flex gap-1">
            <select className="input text-xs py-1" value={form.relationship} onChange={(e) => setForm({ ...form, relationship: e.target.value as Relationship })}>
              <option value="direct">Direct</option>
              <option value="supporting">Supporting</option>
              <option value="contextual">Contextual (never counts)</option>
            </select>
            <select className="input text-xs py-1" value={form.decision} onChange={(e) => setForm({ ...form, decision: e.target.value as typeof form.decision })}>
              <option value="">{changesMapping ? 'Leave pending' : 'Keep decision'}</option>
              <option value="confirm">Confirm</option>
              <option value="reject">Reject</option>
            </select>
          </div>
          <input className="input text-xs py-1 w-full" placeholder="Reason / note (kept in the history)" value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })} />
          {changesMapping && !form.decision && (
            <p className="text-ink-500">A new indicator or relationship does not keep the earlier approval: it waits in the expert queue.</p>
          )}
          <div className="flex gap-2">
            <button className="btn-primary btn-sm" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save'}</button>
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
};
