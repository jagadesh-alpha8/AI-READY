import React, { useState } from 'react';
import { X } from 'lucide-react';

import { uploadGapEvidence } from '../../api/gaps';
import { InlineError } from '../../components/ApiStates';
import type { Gap } from '../../types';
import { getErrorMessage } from '../../utils/errors';

/**
 * Upload Evidence from a Missing Document / Low Confidence gap (backend apps/gaps/evidence_upload.py).
 * Shows the context the upload belongs to; the server stores the file in this gap's sprint, links it to the
 * gap and processes it there. It never confirms a fact or resolves the gap -- the normal reviews do.
 */
export const UploadEvidenceModal: React.FC<{
  gap: Gap;
  sprintLabel: string;
  onClose: () => void;
  onUploaded: (message: string) => void;
}> = ({ gap, sprintLabel, onClose, onUploaded }) => {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const missing = gap.gap_type === 'missing_document';

  const submit = async () => {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const { data } = await uploadGapEvidence(gap.id, file);
      onUploaded(data.reused
        ? 'This file is already in the sprint; it is now linked to the gap (not stored or processed twice).'
        : `${file.name} uploaded and queued for processing. ${missing
          ? 'Confirm its category in Upload Data Pack once processed.'
          : 'Review its facts in Extracted Facts Review once processed.'}`);
    } catch (err) {
      setError(getErrorMessage(err, 'The upload failed.'));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true">
      <div className="glass-card w-full max-w-lg p-5 space-y-3 text-sm">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-bold text-ink-900">Upload evidence</h2>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 text-xs">
          <dt className="text-ink-500">Sprint</dt><dd className="text-ink-900">{sprintLabel}</dd>
          <dt className="text-ink-500">Gap</dt><dd className="text-ink-900">{gap.title} ({missing ? 'Missing Document' : 'Low Confidence'})</dd>
          <dt className="text-ink-500">Requested document</dt><dd className="text-ink-900">{gap.requested_document_type.replace(/_/g, ' ')}</dd>
          {gap.audit_field_id && (<><dt className="text-ink-500">Related fact</dt><dd className="text-ink-900 font-mono">{gap.audit_field_id}</dd></>)}
          {gap.pillar_label && (<><dt className="text-ink-500">Criterion</dt><dd className="text-ink-900">{gap.pillar_label}</dd></>)}
          <dt className="text-ink-500">Responsible</dt>
          <dd className="text-ink-900">{gap.owner_role_label || gap.owner_role || '—'}{gap.assigned_to_name ? ` · ${gap.assigned_to_name}` : ''}</dd>
        </dl>
        {error && <InlineError message={error} onDismiss={() => setError('')} />}
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <p className="text-xs text-ink-500">
          The file goes into this sprint's Upload Data Pack and is processed for this sprint. Uploading does not confirm
          any fact or close the gap: {missing
            ? 'the gap closes when a reviewer confirms the document’s category.'
            : 'the gap closes when a reviewer confirms or corrects the value from this document, with its citation.'}
        </p>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary btn-sm" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn-primary btn-sm" onClick={submit} disabled={busy || !file}>{busy ? 'Uploading…' : 'Upload'}</button>
        </div>
      </div>
    </div>
  );
};
