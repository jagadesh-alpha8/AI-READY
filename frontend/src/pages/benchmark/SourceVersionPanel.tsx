import React, { useState } from 'react';
import { CheckCircle2, FileCheck2, Sparkles, XCircle } from 'lucide-react';

import {
  approveVersion, draftRequirements, ingestVersionFile, listCandidates, reviewCandidate, withdrawVersion,
} from '../../api/benchmarks';
import type { RequirementCandidate, SourceVersion } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';

/**
 * The workflow for one source version, in order:
 *   1. Fetch & verify the file (store it, check its SHA-256 against the register)
 *   2. Approve the version (locks it; supersedes the previous active one)
 *   3. Draft requirements with AI, then accept / edit / reject each draft
 * Every action is server-side and audited; this panel only calls the API.
 */

const INTAKE_LABEL: Record<SourceVersion['intake_status'], [string, string]> = {
  not_run: ['File not checked', 'badge-neutral'],
  verified: ['File verified', 'badge-success'],
  computed: ['File stored (checksum new)', 'badge-success'],
  mismatch: ['Checksum mismatch', 'badge-danger'],
  failed: ['File fetch failed', 'badge-danger'],
  skipped: ['File not fetched', 'badge-warning'],
};

export const SourceVersionPanel: React.FC<{ version: SourceVersion; onChanged: () => void }> = ({
  version, onChanged,
}) => {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reviewOpen, setReviewOpen] = useState(false);

  const run = async (label: string, action: () => Promise<unknown>, done?: string) => {
    setBusy(label);
    setError('');
    setMessage('');
    try {
      await action();
      if (done) setMessage(done);
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy('');
    }
  };

  const approve = () => run('approve', async () => {
    const note = window.prompt('Approval note (what you checked):', '') ?? null;
    if (note === null) return;
    try {
      await approveVersion(version.id, { note });
    } catch (err: any) {
      const flags: string[] = err?.response?.data?.flags || [];
      if (!flags.length) throw err;
      const ok = window.confirm(`This version has ${flags.length} open review flag(s):\n\n- ${flags.join('\n- ')}\n\n`
        + 'Approve anyway? Approval locks the version permanently.');
      if (ok) await approveVersion(version.id, { note, acknowledge_flags: true });
    }
  }, 'Approved and locked.');

  const withdraw = () => run('withdraw', async () => {
    const note = window.prompt('Why is this version being withdrawn?', '');
    if (note) await withdrawVersion(version.id, note);
  });

  const [intakeLabel, intakeClass] = INTAKE_LABEL[version.intake_status];
  const locked = version.status !== 'draft';
  const drafting = version.extraction_status === 'queued' || version.extraction_status === 'running';
  // Mirrors the server's approval_blockers(): a file must be stored and checked,
  // or the source is link-only / licensed. (Flags can still be acknowledged.)
  const fileChecked = version.intake_status === 'verified' || version.intake_status === 'computed';
  const approvable = version.status === 'draft' && version.version_label !== 'unversioned' && (
    (version.collection_status === 'downloaded' && fileChecked)
    || version.collection_status === 'link_only' || version.collection_status === 'licensed_link_only');

  return (
    <div className="rounded-lg border border-line-200 bg-surface p-3 space-y-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`badge ${intakeClass}`} title={version.intake_note}>{intakeLabel}</span>
        {version.approved_by && (
          <span className="text-ink-500">Approved by {version.approved_by}</span>
        )}
        {version.requirement_count > 0 && (
          <span className="badge badge-brand">{version.requirement_count} requirement(s)</span>
        )}
        <span className="flex-1" />
        {!locked && version.collection_status === 'downloaded' && version.intake_status !== 'verified'
          && version.intake_status !== 'computed' && (
          <button className="btn-secondary btn-sm" disabled={!!busy}
            onClick={() => run('intake', () => ingestVersionFile(version.id))}>
            <FileCheck2 className="w-3.5 h-3.5" /> {busy === 'intake' ? 'Fetching…' : 'Fetch & verify file'}
          </button>
        )}
        {version.status === 'draft' && !approvable && (
          <span className="text-ink-500">
            {version.version_label === 'unversioned' ? 'Needs a version before approval' : 'Needs a checked file before approval'}
          </span>
        )}
        {approvable && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={approve}>
            <CheckCircle2 className="w-3.5 h-3.5" /> {busy === 'approve' ? 'Approving…' : 'Approve'}
          </button>
        )}
        {version.status === 'active' && (
          <button className="btn-secondary btn-sm" disabled={!!busy} onClick={withdraw}>
            <XCircle className="w-3.5 h-3.5" /> Withdraw
          </button>
        )}
        {version.file_uri && (
          <button className="btn-secondary btn-sm" disabled={!!busy || drafting}
            onClick={() => run('draft', () => draftRequirements(version.id), 'Queued: the Celery worker drafts in the background.')}>
            <Sparkles className="w-3.5 h-3.5" /> {drafting ? 'Drafting…' : 'Draft requirements with AI'}
          </button>
        )}
        {version.pending_candidates > 0 && (
          <button className="btn-secondary btn-sm" onClick={() => setReviewOpen(!reviewOpen)}>
            Review {version.pending_candidates} draft(s)
          </button>
        )}
      </div>

      {version.intake_note && <p className="text-ink-500">{version.intake_note}</p>}
      {version.extraction_note && (
        <p className={version.extraction_status === 'failed' ? 'text-danger' : 'text-ink-500'}>
          AI drafting: {version.extraction_note}
        </p>
      )}
      {message && <p className="text-success">{message}</p>}
      {error && <InlineError message={error} onDismiss={() => setError('')} />}
      {reviewOpen && <CandidateReview versionId={version.id} onChanged={onChanged} />}
    </div>
  );
};

const CandidateReview: React.FC<{ versionId: string; onChanged: () => void }> = ({ versionId, onChanged }) => {
  const { data, loading, error, refetch } = useApiResource<RequirementCandidate[]>(
    () => listCandidates(versionId), [versionId],
  );
  if (loading) return <LoadingState message="Loading drafts…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  return (
    <div className="space-y-2">
      <p className="text-ink-500">
        Each draft quotes the source word for word (drafts whose quote wasn't found in the text were already
        dropped). Accept only what the quote really says; edit the statement if needed.
      </p>
      {(data || []).map((c) => (
        <CandidateRow key={c.id} candidate={c} onDone={() => { refetch(); onChanged(); }} />
      ))}
      {data && data.length === 0 && <p className="text-ink-500">No drafts waiting.</p>}
    </div>
  );
};

const CandidateRow: React.FC<{ candidate: RequirementCandidate; onDone: () => void }> = ({ candidate, onDone }) => {
  const [statement, setStatement] = useState(candidate.statement);
  const [kind, setKind] = useState(candidate.kind);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const decide = async (decision: 'accept' | 'reject') => {
    setBusy(true);
    setError('');
    try {
      const note = decision === 'reject' ? (window.prompt('Why reject? (optional)', '') ?? '') : '';
      await reviewCandidate(candidate.id, decision === 'accept'
        ? { decision, statement, kind } : { decision, note });
      onDone();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-line-200 bg-white/60 p-3 space-y-2">
      <blockquote className="border-l-2 border-brand-300 pl-2 text-ink-600 italic">
        “{candidate.source_quote}” <span className="not-italic text-ink-500">— page {candidate.page ?? '?'}</span>
      </blockquote>
      <textarea className="input w-full text-xs" rows={2} value={statement} onChange={(e) => setStatement(e.target.value)} />
      <div className="flex flex-wrap items-center gap-2">
        <select className="input text-xs" value={kind} onChange={(e) => setKind(e.target.value as RequirementCandidate['kind'])}>
          <option value="mandatory">Mandatory</option>
          <option value="recommended">Recommended</option>
          <option value="guidance">Guidance</option>
        </select>
        <span className="text-ink-500">AI confidence {(candidate.confidence * 100).toFixed(0)}%</span>
        <span className="flex-1" />
        <button className="btn-primary btn-sm" disabled={busy} onClick={() => decide('accept')}>Accept</button>
        <button className="btn-secondary btn-sm" disabled={busy} onClick={() => decide('reject')}>Reject</button>
      </div>
      {candidate.rationale && <p className="text-ink-500">AI: {candidate.rationale}</p>}
      {error && <InlineError message={error} onDismiss={() => setError('')} />}
    </div>
  );
};
