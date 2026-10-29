import React, { useState } from 'react';
import { X } from 'lucide-react';

import { listSprintDocuments } from '../../api/documents';
import { decideCorrection, proposeCorrection } from '../../api/facts';
import { InlineError } from '../../components/ApiStates';
import { confirmDialog, promptDialog } from '../../components/Dialog';
import { useApiResource } from '../../hooks/useApiResource';
import type { Fact, SprintDocument } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { VERIFICATION_LABEL } from './FactVerification';

/**
 * Correcting a value a person already reviewed: propose it with a reason and its source; a different reviewer
 * approves (backend apps/facts/verification/corrections.py). The fact is unchanged until then.
 */
export const ProposeCorrectionModal: React.FC<{ fact: Fact; onClose: () => void; onDone: () => void }> = ({
  fact, onClose, onDone,
}) => {
  const { data: docs } = useApiResource<SprintDocument[]>(() => listSprintDocuments(fact.sprint_id), [fact.sprint_id]);
  const [value, setValue] = useState(String(fact.value ?? ''));
  const [reason, setReason] = useState('');
  const [documentId, setDocumentId] = useState(fact.source_document_id || '');
  const [page, setPage] = useState('');
  const [snippet, setSnippet] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError('');
    const parsed = ['number', 'percentage'].includes(fact.data_type) && value.trim() !== '' && !Number.isNaN(Number(value))
      ? Number(value) : value;
    try {
      await proposeCorrection(fact.id, {
        value: parsed, reason, source_document_id: documentId || null, source_page: page, source_snippet: snippet,
      });
      onDone();
    } catch (err) {
      setError(getErrorMessage(err, 'The correction could not be proposed.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true">
      <div className="glass-card w-full max-w-lg p-5 space-y-3 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink-900">Propose a correction</h2>
            <p className="text-xs text-ink-500 mt-0.5">
              {fact.field_name}: <span className="font-mono">{JSON.stringify(fact.value)}</span> ({fact.status}).
              Another reviewer must approve it; until then the fact stays as it is.
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <label className="block text-xs font-semibold text-ink-700">Correct value
          <input className="input w-full mt-1" value={value} onChange={(e) => setValue(e.target.value)} />
        </label>
        <label className="block text-xs font-semibold text-ink-700">Why the current value is wrong
          <textarea className="input w-full mt-1 min-h-[64px]" value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <label className="block text-xs font-semibold text-ink-700">Supporting document (this sprint)
          <select className="input w-full mt-1" value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
            <option value="">Choose a document…</option>
            {(docs || []).map((d) => (
              <option key={d.id} value={d.id}>{d.original_filename}{d.version_number ? ` (v${d.version_number})` : ''}</option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-3 gap-2">
          <label className="block text-xs font-semibold text-ink-700">Page
            <input className="input w-full mt-1" value={page} onChange={(e) => setPage(e.target.value)} />
          </label>
          <label className="block col-span-2 text-xs font-semibold text-ink-700">Quote from that page
            <input className="input w-full mt-1" value={snippet} onChange={(e) => setSnippet(e.target.value)} />
          </label>
        </div>
        <p className="text-[11px] text-ink-500">The value is checked against the quote and page before the approver sees it.</p>
        {error && <InlineError message={error} />}
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={submit} disabled={saving || !reason.trim() || !documentId || !page.trim()}>
            {saving ? 'Submitting…' : 'Propose correction'}
          </button>
        </div>
      </div>
    </div>
  );
};

/** A pending proposal on a fact row: approve / reject for another reviewer, withdraw for its author. */
export const PendingCorrectionNote: React.FC<{ fact: Fact; onChanged: () => void; onError: (m: string) => void }> = ({
  fact, onChanged, onError,
}) => {
  const p = fact.pending_correction;
  const [busy, setBusy] = useState(false);
  if (!p) return null;
  const act = async (decision: 'approve' | 'reject' | 'withdraw') => {
    let reason = '';
    if (decision === 'reject') {
      const answer = await promptDialog('Why is this correction rejected? (kept in the fact history)',
        { title: 'Reject correction', confirmLabel: 'Reject', danger: true, required: true });
      if (!answer) return;
      reason = answer;
    } else if (decision === 'approve') {
      if (!(await confirmDialog(`Change ${fact.field_name} from ${JSON.stringify(fact.value)} to ${JSON.stringify(p.proposed_value)}?`,
        { title: 'Approve correction', confirmLabel: 'Approve' }))) return;
    }
    setBusy(true);
    try {
      await decideCorrection(p.id, decision, reason);
      onChanged();
    } catch (err) {
      onError(getErrorMessage(err, 'The correction decision could not be saved.'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="block text-[11px] text-ink-600 mt-1 max-w-[15rem] whitespace-normal">
      <span className="font-semibold text-accent">Correction proposed:</span> {JSON.stringify(p.proposed_value)}
      {' '}by {p.submitted_by_name}
      {p.verification_outcome ? ` · source check: ${VERIFICATION_LABEL[p.verification_outcome] || p.verification_outcome}` : ''}
      <span className="block text-ink-500 italic">“{p.reason}”</span>
      <span className="flex gap-2 mt-0.5">
        {p.mine ? (
          <button className="text-accent font-semibold hover:underline" disabled={busy} onClick={() => act('withdraw')}>Withdraw</button>
        ) : (
          <>
            <button className="text-success font-semibold hover:underline" disabled={busy} onClick={() => act('approve')}>Approve</button>
            <button className="text-danger font-semibold hover:underline" disabled={busy} onClick={() => act('reject')}>Reject</button>
          </>
        )}
      </span>
    </span>
  );
};
