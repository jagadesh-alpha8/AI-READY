import React, { useState } from 'react';
import { CheckCircle2, FileCheck2, Sparkles, XCircle } from 'lucide-react';

import {
  approveVersion, compareVersion, draftRequirements, ingestVersionFile, listCandidates, reviewCandidate, withdrawVersion,
} from '../../api/benchmarks';
import type { RequirementCandidate, SourceVersion, VersionComparison } from '../../api/benchmarks';
import { AIJobPanel } from './AIJobPanel';
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
  const [compareOpen, setCompareOpen] = useState(false);

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
        {version.file_uri && version.status === 'active' && (
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
        <button className="btn-secondary btn-sm" onClick={() => setCompareOpen(!compareOpen)}>
          {compareOpen ? 'Hide comparison' : 'Compare with previous version'}
        </button>
      </div>
      {compareOpen && <VersionCompare versionId={version.id} />}
      {approvable && (
        <p className="text-ink-500">Next: approve this version; AI then drafts its requirements for review.</p>
      )}

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
      {(candidate.duplicates || []).length > 0 && (
        <p className="text-warning">
          Possible duplicate of {candidate.duplicates!.map((d) => `${d.code} (${Math.round(d.similarity * 100)}% same words)`).join(', ')}
          {' '}- reject it if it says the same thing.
        </p>
      )}
      {(candidate.suggested_benchmarks || []).length > 0 && (
        <p className="text-ink-500">
          Looks related to {candidate.suggested_benchmarks!.map((b) => `${b.code} ${b.title}`).join('; ')}
          {' '}- once accepted, check the indicator fit in Requirements.
        </p>
      )}
      {error && <InlineError message={error} onDismiss={() => setError('')} />}
    </div>
  );
};

const VersionCompare: React.FC<{ versionId: string }> = ({ versionId }) => {
  const { data, loading, error, refetch } = useApiResource<VersionComparison>(() => compareVersion(versionId), [versionId]);
  if (loading) return <LoadingState message="Comparing…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data) return null;
  if (!data.base) return <p className="text-ink-500">{data.note}</p>;
  return (
    <div className="rounded-lg border border-line-200 bg-white/60 p-3 space-y-1">
      <p className="text-ink-700">
        Against <strong>{data.base.version_label}</strong> ({data.base.status}):{' '}
        {data.same_file ? 'same file (checksum identical)' : data.file_changed ? 'a different file' : 'file not compared'}
        {data.pages && ` · pages ${data.pages.before ?? '?'} → ${data.pages.after ?? '?'}`}
        {data.requirements_on_base ? ` · ${data.requirements_on_base} requirement(s) were approved on the earlier version` : ''}
      </p>
      {data.note && <p className="text-ink-500">{data.note}</p>}
      {(data.added || []).length > 0 && (
        <details open><summary className="cursor-pointer text-success">{data.added!.length} line(s) added</summary>
          <ul className="mt-1 space-y-0.5">{data.added!.map((l, i) => <li key={i} className="text-success">+ {l}</li>)}</ul>
        </details>
      )}
      {(data.removed || []).length > 0 && (
        <details><summary className="cursor-pointer text-danger">{data.removed!.length} line(s) removed</summary>
          <ul className="mt-1 space-y-0.5">{data.removed!.map((l, i) => <li key={i} className="text-danger">- {l}</li>)}</ul>
        </details>
      )}
    </div>
  );
};

const FIELD_LABEL: Record<string, string> = {
  title: 'Title', authority_name: 'Authority (shown only)', document_type: 'Document type', source_role: 'Source role',
  applies_to: 'Applies to', programme_scope: 'Programme scope', version_label: 'Version (draft version)',
  issued_on: 'Issued on (draft version)', effective_from: 'Effective from (draft version)',
};

/** AI reads the source's stored file (or official page) and suggests its details, each with the quote it came from. */
export const SourceDetailsAI: React.FC<{ sourceCode: string; hasText: boolean; onChanged: () => void }> = ({
  sourceCode, hasText, onChanged,
}) => {
  const [chosen, setChosen] = useState<string[]>([]);
  return (
    <AIJobPanel kind="source_metadata" targetId={sourceCode} title="Source details (AI)" startLabel="Suggest details from the source"
      disabled={hasText ? undefined : 'Store a file or add the official URL first; AI needs the source text.'} onChanged={onChanged}>
      {(job, act) => {
        const fields = (job.output.fields || {}) as Record<string, { value: string; quote: string; current: string | null }>;
        return (
          <div className="space-y-1">
            <table className="w-full">
              <tbody>
                {Object.entries(fields).map(([name, f]) => (
                  <tr key={name} className="border-t border-line-200 align-top">
                    <td className="py-1 pr-2">
                      {job.status === 'ready' && name !== 'authority_name' && (
                        <input type="checkbox" checked={chosen.includes(name)}
                          onChange={(e) => setChosen(e.target.checked ? [...chosen, name] : chosen.filter((c) => c !== name))} />
                      )}
                    </td>
                    <td className="py-1 pr-2 font-semibold">{FIELD_LABEL[name] || name}</td>
                    <td className="py-1 pr-2">
                      <span className="text-ink-900">{f.value}</span>
                      {f.current ? <span className="text-ink-500"> (now: {f.current})</span> : null}
                      <p className="text-ink-500 italic">“{f.quote}”</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(job.output.rejected || []).length > 0 && (
              <p className="text-ink-500">Dropped (not found in the source): {job.output.rejected.map((r: { field: string }) => r.field).join(', ')}</p>
            )}
            {job.status === 'ready' && (
              <button className="btn-primary btn-sm" disabled={!chosen.length} onClick={() => act('apply', { fields: chosen })}>
                Apply {chosen.length || ''} selected value{chosen.length === 1 ? '' : 's'}
              </button>
            )}
          </div>
        );
      }}
    </AIJobPanel>
  );
};
