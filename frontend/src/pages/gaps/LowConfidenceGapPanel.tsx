import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';

import { getFact } from '../../api/facts';
import { markGapUnavailable, resolveGap, skipGap } from '../../api/gaps';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import type { Fact, Gap } from '../../types';
import { ACTIVE_GAP_STATUSES } from '../../types/gaps';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import { RequestEvidenceModal } from '../facts/RequestEvidenceModal';

const fmt = (v: unknown) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '—'));

/**
 * A low-confidence gap's fact: what was extracted, from where, and how sure the extraction was -- and the
 * way to settle it. The gap is settled by evidence: request it here (the existing evidence-request flow),
 * and it closes when a reviewer accepts the evidence. Resolve / Skip / Mark unavailable stay available only
 * where the server allows them (gap.resolve_blocked_reason / close_blocked_reason), with an explanation.
 */
export const LowConfidenceGapPanel: React.FC<{
  gap: Gap;
  onClose: () => void;
  onChanged: () => void;
}> = ({ gap, onClose, onChanged }) => {
  const { can } = useAccess();
  const { data: fact, loading, error, refetch } = useApiResource<Fact>(
    () => getFact(gap.source_fact_id!), [gap.source_fact_id],
  );
  const [requesting, setRequesting] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const gapOpen = ACTIVE_GAP_STATUSES.includes(gap.status);
  const request = gap.evidence_request;
  const requestOpen = !!request && ['open', 'submitted', 'returned'].includes(request.status);

  const close = async (fn: (id: string, value: string) => Promise<unknown>) => {
    setBusy(true);
    setActionError('');
    try {
      await fn(gap.id, reason.trim());
      onChanged();
      onClose();
    } catch (err) {
      setActionError(getErrorMessage(err, 'The gap could not be closed.'));
    } finally {
      setBusy(false);
    }
  };

  if (requesting && fact) {
    return (
      <RequestEvidenceModal
        fact={fact}
        onClose={() => setRequesting(false)}
        onCreated={() => { setRequesting(false); refetch(); onChanged(); }}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true">
      <div className="glass-card w-full max-w-xl p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink-900">{gap.title}</h2>
            <p className="text-xs text-ink-500 mt-0.5">
              Gap {gap.status.replace(/_/g, ' ')} · {gap.priority} · -{gap.score_impact} pts while open
            </p>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>

        {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

        {loading && !fact ? <LoadingState message="Loading the fact..." />
          : error ? <ErrorState message={error} onRetry={refetch} />
            : fact && (
              <dl className="grid grid-cols-3 gap-x-3 gap-y-1.5 text-xs">
                <dt className="text-ink-500">Fact</dt>
                <dd className="col-span-2 font-semibold text-ink-900">{fact.field_name} <span className="font-mono text-ink-500">{fact.field_key}</span></dd>
                <dt className="text-ink-500">Extracted value</dt>
                <dd className="col-span-2 font-mono text-ink-900">{fmt(fact.value_json)}</dd>
                <dt className="text-ink-500">Fact status</dt>
                <dd className="col-span-2">{fact.status.replace(/_/g, ' ')}</dd>
                <dt className="text-ink-500">Confidence</dt>
                <dd className="col-span-2">
                  {(fact.confidence * 100).toFixed(0)}%
                  {fact.confidence_reason && <span className="block text-ink-500">{fact.confidence_reason}</span>}
                </dd>
                <dt className="text-ink-500">Source</dt>
                <dd className="col-span-2">
                  {fact.source_document_filename || '—'}{fact.source_page ? ` · page ${fact.source_page}` : ''}
                  {fact.source_snippet && <span className="block italic text-ink-600">“{fact.source_snippet}”</span>}
                </dd>
                <dt className="text-ink-500">Owner role</dt>
                <dd className="col-span-2">{fact.owner_role || '—'} <span className="text-ink-500">(the role that owns this data, not a named person)</span></dd>
                <dt className="text-ink-500">Evidence request</dt>
                <dd className="col-span-2">
                  {request ? (
                    <Link to={`/evidence-requests?view=all&id=${request.id}`} className="font-semibold text-accent hover:underline">
                      {request.overdue ? 'Overdue · ' : ''}{request.status_label}
                      {' '}· {request.assigned_to_name ? `assigned to ${request.assigned_to_name}` : 'not assigned yet'}
                      {request.due_date ? ` · due ${request.due_date}` : ''}
                    </Link>
                  ) : 'None yet'}
                </dd>
              </dl>
            )}

        {gapOpen && (
          <div className="space-y-3 border-t border-line-200 pt-3">
            {requestOpen ? (
              <p className="text-xs text-ink-700">
                Waiting on the evidence request. This gap closes when a reviewer other than the submitter accepts
                the evidence there; rejected or returned evidence leaves it open.
              </p>
            ) : can('facts.review') && fact && (
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn-primary btn-sm" onClick={() => setRequesting(true)}>Request evidence</button>
                <span className="text-[11px] text-ink-500">
                  Ask a named person of the college for evidence. Accepting it confirms the fact and closes this gap.
                </span>
              </div>
            )}

            {can('gaps.resolve') && (
              <div className="space-y-2">
                <label className="block text-xs font-semibold text-ink-700">
                  Close the gap another way (explanation required)
                  <input className="input mt-1 w-full" value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. Verified against the signed register; fact confirmed with its citation." />
                </label>
                {gap.resolve_blocked_reason && <p className="text-[11px] text-warning">{gap.resolve_blocked_reason}</p>}
                {!gap.resolve_blocked_reason && gap.close_blocked_reason && (
                  <p className="text-[11px] text-warning">{gap.close_blocked_reason}</p>
                )}
                <div className="flex flex-wrap gap-2">
                  <button className="btn-secondary btn-sm" disabled={busy || !!gap.resolve_blocked_reason || !reason.trim()}
                    onClick={() => close(resolveGap)}>Resolve</button>
                  <button className="btn-secondary btn-sm" disabled={busy || !!gap.close_blocked_reason || !reason.trim()}
                    onClick={() => close(markGapUnavailable)}>Mark unavailable</button>
                  <button className="btn-secondary btn-sm" disabled={busy || !!gap.close_blocked_reason || !reason.trim()}
                    onClick={() => close(skipGap)}>Skip</button>
                </div>
              </div>
            )}
          </div>
        )}
        {!gapOpen && gap.resolution && (
          <p className="text-xs text-ink-700 border-t border-line-200 pt-3">Closed: “{gap.resolution}”</p>
        )}
      </div>
    </div>
  );
};
