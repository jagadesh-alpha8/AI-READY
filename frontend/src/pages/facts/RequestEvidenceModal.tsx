import React, { useState } from 'react';
import { X } from 'lucide-react';

import { createEvidenceRequest, listEvidenceAssignees } from '../../api/evidenceRequests';
import { InlineError } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import type { EvidenceAssignee, Fact } from '../../types';
import { getErrorMessage } from '../../utils/errors';

/**
 * "Request Evidence": what is needed and why, the fact's suggested owner role (a hint only), the person
 * who should provide it (chosen from this college's users -- never guessed from the role) and a due date.
 */
export const RequestEvidenceModal: React.FC<{
  fact: Fact;
  onClose: () => void;
  onCreated: () => void;
}> = ({ fact, onClose, onCreated }) => {
  const { data: people, loading } = useApiResource<EvidenceAssignee[]>(
    () => listEvidenceAssignees(fact.sprint_id), [fact.sprint_id],
  );
  const [evidenceNeeded, setEvidenceNeeded] = useState('');
  const [reason, setReason] = useState('');
  const [assignee, setAssignee] = useState('');
  const [due, setDue] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const role = (fact.owner_role || '').toLowerCase();
  const sorted = [...(people || [])].sort((a, b) => Number(b.role === role) - Number(a.role === role));
  const roleHolders = sorted.filter((p) => p.role === role).length;

  const submit = async () => {
    setSaving(true);
    setError('');
    try {
      await createEvidenceRequest(fact.id, {
        evidence_needed: evidenceNeeded, reason, assigned_to: assignee || null, due_date: due || null,
      });
      onCreated();
    } catch (err) {
      setError(getErrorMessage(err, 'Could not create the evidence request.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true">
      <div className="glass-card w-full max-w-lg p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink-900">Request evidence</h2>
            <p className="text-xs text-ink-500 mt-0.5">
              {fact.field_name}: <span className="font-mono">{String(fact.value_json)}</span>
              {fact.source_page ? ` · cited ${fact.source_page}` : ''}
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>

        {error && <InlineError message={error} onDismiss={() => setError('')} />}

        <label className="block text-xs font-semibold text-ink-700">
          What evidence is needed? *
          <textarea
            className="input mt-1 w-full min-h-[90px]"
            value={evidenceNeeded}
            onChange={(e) => setEvidenceNeeded(e.target.value)}
            placeholder="e.g. The signed FDP attendance register for 2025-26."
          />
        </label>

        <label className="block text-xs font-semibold text-ink-700">
          Why is it needed? *
          <textarea className="input mt-1 w-full min-h-[70px]" value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. To verify the reported 62.5% faculty certification figure." />
        </label>

        <div className="text-xs text-ink-600">
          Responsible role: <strong>{fact.owner_role || 'Assign to an appropriate college role'}</strong>
          {fact.owner_role && !loading && roleHolders === 0 && (
            <span className="block text-warning mt-0.5">
              No active user of this college has this role. Choose someone else, or leave it unassigned for an
              admin or IQAC to assign.
            </span>
          )}
        </div>

        <label className="block text-xs font-semibold text-ink-700">
          Who should provide it
          <select className="input mt-1 w-full" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">Not assigned yet</option>
            {sorted.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.role.replace(/_/g, ' ')}{p.role === role ? ' (suggested role)' : ''}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-xs font-semibold text-ink-700">
          Due date (optional)
          <input type="date" className="input mt-1 w-full" value={due} onChange={(e) => setDue(e.target.value)}
            min={new Date().toISOString().slice(0, 10)} />
        </label>

        <p className="text-[11px] text-ink-500">
          The fact moves to "evidence requested" and stays out of the CRI until a reviewer decides on the evidence.
        </p>

        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={saving || !evidenceNeeded.trim() || !reason.trim()} onClick={submit}>
            {saving ? 'Sending...' : 'Request evidence'}
          </button>
        </div>
      </div>
    </div>
  );
};
