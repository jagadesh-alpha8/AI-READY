import React, { useEffect, useMemo, useState } from 'react';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { Link, useSearchParams } from 'react-router-dom';
import { FileCheck2 } from 'lucide-react';

import { downloadDocument, listSprintDocuments } from '../../api/documents';
import {
  assignEvidenceRequest, commentOnEvidenceRequest, getEvidenceRequest, listEvidenceAssignees, listEvidenceRequests,
  reviewEvidenceRequest, submitEvidence,
} from '../../api/evidenceRequests';
import type { EvidenceDecision, EvidenceRequestFilters } from '../../api/evidenceRequests';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import { useAuth } from '../../context/AuthContext';
import { useApiResource } from '../../hooks/useApiResource';
import type {
  EvidenceAssignee, EvidenceLink, EvidenceRequest, EvidenceRequestDetail, SprintDocument,
} from '../../types';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';

/**
 * Evidence requests: request -> assignment -> evidence -> a reviewer's explicit decision. Also the
 * in-app task list ("Assigned to me"). Nothing here confirms a fact by itself; the CRI changes only when
 * an accepted decision is followed by a CRI recalculation.
 */
type View = 'mine' | 'review' | 'open' | 'overdue' | 'resolved' | 'all';

const VIEWS: { id: View; label: string; filters: EvidenceRequestFilters }[] = [
  { id: 'mine', label: 'Assigned to me', filters: { assigned_to: 'me', unresolved: true } },
  { id: 'review', label: 'Awaiting review', filters: { status: 'submitted,ready_for_review' } },
  { id: 'open', label: 'Open / returned', filters: { status: 'open,returned' } },
  { id: 'overdue', label: 'Overdue', filters: { overdue: true } },
  { id: 'resolved', label: 'Resolved', filters: { status: 'accepted,accepted_corrected,withdrawn' } },
  { id: 'all', label: 'All', filters: {} },
];

const ASSIGN_ROLES = ['super_admin', 'consultant', 'institution_admin', 'iqac_coordinator'];
const UNRESOLVED = ['open', 'submitted', 'processing', 'ready_for_review', 'returned'];

export const statusBadge = (status: string, overdue = false) => {
  if (overdue) return 'badge-danger';
  switch (status) {
    case 'accepted':
    case 'accepted_corrected': return 'badge-success';
    case 'ready_for_review': return 'badge-success';
    case 'submitted':
    case 'processing': return 'badge-info';
    case 'returned': return 'badge-warning';
    case 'withdrawn': return 'badge-neutral';
    default: return 'badge-brand';
  }
};

const fmt = (v: unknown) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '—'));

export const EvidenceRequests: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<View>((params.get('view') as View) || 'mine');
  const selectedId = params.get('id') || '';
  // Scope: the sprint selected in the header by default; ?sprint=all for every sprint the user may see;
  // ?sprint=<id> for one sprint (e.g. a link from that sprint's Facts Review). The server checks access.
  const { sprintId: selectedSprintId, sprint: selectedSprint, sprints } = useSelectedSprint();
  const sprintParam = params.get('sprint');
  const scope = sprintParam === 'all' ? 'all' : (sprintParam || selectedSprintId || 'all');
  const scopedSprint = scope === 'all' ? null
    : (sprints || []).find((s) => s.id === scope) || (scope === selectedSprintId ? selectedSprint : null);
  const setScope = (value: string) => {
    const next = new URLSearchParams(params);
    next.set('sprint', value);
    next.delete('id');
    setParams(next);
  };
  const filters = { ...VIEWS.find((v) => v.id === view)!.filters, sprint: scope };

  const { data, loading, error, refetch } = useApiResource<EvidenceRequest[]>(
    () => listEvidenceRequests(filters), [view, scope],
  );
  const rows = data || [];
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('id', id);
    setParams(next);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={FileCheck2}
        title="Evidence Requests"
        description="Evidence asked for behind specific facts: who provides it, what was submitted, and the reviewer's decision."
      />
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold text-ink-700">Showing requests for</span>
        {scope === 'all' ? (
          <span className="badge-brand">All sprints you can access</span>
        ) : (
          <span className="badge-brand">
            {scopedSprint ? `${scopedSprint.name} · ${scopedSprint.sprint_code}` : 'the selected sprint'}
          </span>
        )}
        {scope !== 'all' && <button className="btn-secondary btn-sm" onClick={() => setScope('all')}>All sprints</button>}
        {scope === 'all' && selectedSprintId && (
          <button className="btn-secondary btn-sm" onClick={() => setScope(selectedSprintId)}>
            Only {selectedSprint ? selectedSprint.sprint_code : 'the selected sprint'}
          </button>
        )}
        {scope === 'all' && !selectedSprintId && (
          <span className="text-ink-500">Select a sprint in the header to see just that sprint.</span>
        )}
      </div>
      <FilterPills options={VIEWS.map(({ id, label }) => ({ id, label }))} active={view} onChange={setView} />

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-5">
        <div className="xl:col-span-2 space-y-2">
          {loading ? <LoadingState message="Loading requests..." />
            : error ? <ErrorState message={error} onRetry={refetch} />
              : rows.length === 0 ? <EmptyState message="Nothing here." />
                : rows.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => select(r.id)}
                    className={`w-full text-left glass-card p-3 border ${r.id === selectedId ? 'border-brand-500' : 'border-transparent'}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-bold text-ink-900">{r.fact_field_name}</span>
                      <span className={statusBadge(r.status, r.overdue)}>{r.overdue ? 'Overdue' : r.status_label}</span>
                    </div>
                    <p className="text-xs text-ink-600 mt-1 line-clamp-2">{r.description}</p>
                    <p className="text-[11px] text-ink-500 mt-1">
                      <span className="font-semibold text-ink-700">{r.sprint_name} · {r.sprint_code}</span>
                      {' '}· {r.assigned_to_name ? `Assigned to ${r.assigned_to_name}` : 'Not assigned'}
                      {r.due_date ? ` · due ${r.due_date}` : ''} · {r.evidence_count} submission{r.evidence_count === 1 ? '' : 's'}
                    </p>
                  </button>
                ))}
        </div>
        <div className="xl:col-span-3">
          {selectedId ? <RequestDetail id={selectedId} onChanged={refetch} />
            : <EmptyState message="Choose a request to see its evidence and history." />}
        </div>
      </div>
    </div>
  );
};

const RequestDetail: React.FC<{ id: string; onChanged: () => void }> = ({ id, onChanged }) => {
  const { user } = useAuth();
  const { can } = useAccess();
  const { data: loaded, loading, error, refetch } = useApiResource<EvidenceRequestDetail>(
    () => getEvidenceRequest(id), [id],
  );
  const [detail, setDetail] = useState<EvidenceRequestDetail | null>(null);
  useEffect(() => setDetail(loaded), [loaded]);
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);

  if (loading && !detail) return <LoadingState message="Loading request..." />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!detail) return null;

  const unresolved = UNRESOLVED.includes(detail.status);
  const isAssignee = !!user && detail.assigned_to === user.id;
  const canAssign = !!user && (ASSIGN_ROLES.includes(user.role) || detail.requested_by === user.id);
  const run = async (fn: () => Promise<{ data: EvidenceRequestDetail }>) => {
    setBusy(true);
    setActionError('');
    try {
      const res = await fn();
      setDetail(res.data);
      onChanged();
      return true;
    } catch (err) {
      setActionError(getErrorMessage(err, 'The action failed.'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="glass-card p-5 space-y-5">
      <div>
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-bold text-ink-900">{detail.fact_field_name}</h2>
          <span className={statusBadge(detail.status, detail.overdue)}>
            {detail.overdue ? `Overdue · ${detail.status_label}` : detail.status_label}
          </span>
        </div>
        <p className="text-xs text-ink-500 mt-1">
          {detail.institution_name} · <strong>{detail.sprint_name} · {detail.sprint_code}</strong> · value <span className="font-mono">{fmt(detail.fact_value)}</span>
          {' '}· fact status {detail.fact_status.replace(/_/g, ' ')}
          {detail.fact_source_page ? ` · currently cited ${detail.fact_source_page}` : ''}
        </p>
        <div className="text-sm text-ink-800 mt-3 space-y-1">
          <p><strong>Evidence needed:</strong> {detail.evidence_needed || detail.description}</p>
          <p><strong>Why:</strong> {detail.reason || detail.description}</p>
        </div>
        <p className="text-xs text-ink-500 mt-2">
          Requested by {detail.requested_by_name || '—'} · responsible role {detail.responsible_role || '—'} ·{' '}
          {detail.assigned_to_name ? <>assigned to <strong>{detail.assigned_to_name}</strong></> : <strong className="text-warning">not assigned</strong>}
          {detail.due_date ? ` · due ${detail.due_date}` : ''}
        </p>
        {!unresolved && (
          <p className="text-xs text-ink-700 mt-2">
            {detail.status_label} by {detail.resolved_by_name || '—'}
            {detail.resolved_at ? ` on ${new Date(detail.resolved_at).toLocaleString()}` : ''}
            {detail.resolution_note ? `: “${detail.resolution_note}”` : ''}
          </p>
        )}
      </div>

      {detail.fact_gaps.length > 0 && (
        <section className="text-xs space-y-1">
          <h3 className="eyebrow">Gaps on this fact</h3>
          {detail.fact_gaps.map((g) => (
            <p key={g.id} className="text-ink-700">
              <Link to={`/sprint/${detail.sprint}/gaps`} className="font-semibold text-brand-800 hover:underline">
                {g.gap_type_label}
              </Link>
              {' '}· {g.status.replace(/_/g, ' ')}
              {g.gap_type === 'low_confidence' && (g.status === 'open' || g.status === 'in_progress')
                && unresolved && ' · closes when a reviewer accepts the evidence below'}
              {g.status === 'resolved' && g.resolution ? ` · “${g.resolution}”` : ''}
            </p>
          ))}
        </section>
      )}

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {unresolved && canAssign && (
        <AssignForm sprintId={detail.sprint} current={detail.assigned_to} busy={busy}
          onAssign={(person, note) => run(() => assignEvidenceRequest(detail.id, person, note))} />
      )}

      <section className="space-y-2">
        <h3 className="eyebrow">Submitted evidence ({detail.evidence.length})</h3>
        {detail.evidence.length === 0 && <p className="text-xs text-ink-500">Nothing submitted yet.</p>}
        {detail.evidence.map((link) => (
          <EvidenceCard key={link.id} link={link} detail={detail} busy={busy}
            canDecide={unresolved && can('facts.review') && link.status === 'submitted' && link.submitted_by !== user?.id}
            onDecide={(decision, body) => run(() => reviewEvidenceRequest(detail.id, { decision, evidence_id: link.id, ...body }))} />
        ))}
      </section>

      {detail.suggested_facts.length > 0 && (
        <section className="space-y-1">
          <h3 className="eyebrow">Facts extracted from the evidence that look relevant</h3>
          <p className="text-[11px] text-ink-500">Suggestions only: none of these is confirmed or copied onto the fact.</p>
          {detail.suggested_facts.map((s) => (
            <div key={s.id} className="text-xs border border-line-200 rounded-lg p-2">
              <span className="badge-neutral mr-1">{s.why}</span>
              <strong>{s.field_name}</strong> = <span className="font-mono">{fmt(s.value)}</span>
              {s.source_page && <> · page {s.source_page}</>}
              {s.source_snippet && <p className="text-ink-500 mt-0.5 italic">“{s.source_snippet}”</p>}
            </div>
          ))}
        </section>
      )}

      {unresolved && isAssignee && (
        <SubmitForm sprintId={detail.sprint} busy={busy}
          onSubmit={(body) => run(() => submitEvidence(detail.id, body))} />
      )}
      {unresolved && !isAssignee && !detail.assigned_to && (
        <p className="text-xs text-warning">Evidence can be submitted once the request is assigned to someone.</p>
      )}

      {unresolved && can('facts.review') && (
        <WithdrawForm busy={busy}
          onWithdraw={(reason) => run(() => reviewEvidenceRequest(detail.id, { decision: 'withdraw', reason }))} />
      )}

      <section className="space-y-2">
        <h3 className="eyebrow">History</h3>
        <ol className="space-y-1.5">
          {detail.events.map((e) => (
            <li key={e.id} className="text-xs text-ink-700">
              <span className="text-ink-500">{new Date(e.created_at).toLocaleString()}</span> · <strong>{e.action_label}</strong>
              {' '}by {e.user_name || 'System'}
              {e.action === 'assigned' && e.data?.to ? ` → ${(e.data.to as { name: string }).name}` : ''}
              {e.data?.document ? ` · ${String(e.data.document)}` : ''}
              {e.data?.outcome ? ` · ${String(e.data.outcome)} (${Math.round(Number(e.data.confidence || 0) * 100)}% confidence)` : ''}
              {e.data?.summary ? ` · ${String(e.data.summary)}` : ''}
              {e.note ? `: “${e.note}”` : ''}
            </li>
          ))}
        </ol>
        {can('documents.contribute') && (
          <CommentForm busy={busy} onComment={(note) => run(() => commentOnEvidenceRequest(detail.id, note))} />
        )}
      </section>
    </div>
  );
};

const AssignForm: React.FC<{
  sprintId: string; current: string | null; busy: boolean;
  onAssign: (person: string, note: string) => Promise<boolean>;
}> = ({ sprintId, current, busy, onAssign }) => {
  const { data } = useApiResource<EvidenceAssignee[]>(() => listEvidenceAssignees(sprintId), [sprintId]);
  const [person, setPerson] = useState('');
  const [note, setNote] = useState('');
  return (
    <div className="flex flex-wrap items-end gap-2 text-xs">
      <label className="font-semibold text-ink-700">
        {current ? 'Reassign to' : 'Assign to'}
        <select className="input mt-1" value={person} onChange={(e) => setPerson(e.target.value)}>
          <option value="">Choose a person</option>
          {(data || []).filter((p) => p.id !== current).map((p) => (
            <option key={p.id} value={p.id}>{p.name} · {p.role.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </label>
      <input className="input flex-1 min-w-[140px]" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn-secondary btn-sm" disabled={busy || !person}
        onClick={async () => { if (await onAssign(person, note)) { setPerson(''); setNote(''); } }}>
        {current ? 'Reassign' : 'Assign'}
      </button>
    </div>
  );
};

const EvidenceCard: React.FC<{
  link: EvidenceLink; detail: EvidenceRequestDetail; busy: boolean; canDecide: boolean;
  onDecide: (decision: EvidenceDecision, body: Record<string, unknown>) => Promise<boolean>;
}> = ({ link, detail, busy, canDecide, onDecide }) => {
  const [mode, setMode] = useState<'' | 'accept' | 'accept_corrected' | 'return' | 'reject'>('');
  const [page, setPage] = useState(link.analysis_page_number?.toString() || link.source_page);
  const [snippet, setSnippet] = useState(link.analysis_quote || link.source_snippet);
  const [value, setValue] = useState(fmt(link.analysis_suggested_value ?? detail.fact_value));
  const [reason, setReason] = useState('');
  const fromThisDoc = useMemo(() => link.document
    ? detail.suggested_facts.filter((s) => s.document === link.document) : [], [detail, link]);

  const decide = () => {
    const body: Record<string, unknown> = { reason };
    if (mode === 'accept' || mode === 'accept_corrected') {
      body.source_page = page;
      body.source_snippet = snippet;
    }
    if (mode === 'accept_corrected') {
      const n = Number(value);
      body.corrected_value = value.trim() !== '' && !Number.isNaN(n) ? n : value;
    }
    return onDecide(mode as EvidenceDecision, body);
  };

  return (
    <div className="border border-line-200 rounded-lg p-3 text-xs space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          {link.document ? (
            <button className="font-semibold text-brand-800 hover:underline"
              onClick={() => downloadDocument(link.document!, link.document_filename)}>{link.document_filename}</button>
          ) : <strong>{link.document_filename}</strong>}
          <span className="text-ink-500">
            {link.document ? ` · ${link.uploaded_for_request ? 'uploaded for this request' : 'existing sprint document'}` : ' · pasted text'}
            {link.page_count ? ` · ${link.page_count} pages` : ''}{link.document_status ? ` · document ${link.document_status}` : ''}
          </span>
          <p className="text-ink-500">Submitted by {link.submitted_by_name} on {new Date(link.created_at).toLocaleString()}</p>
        </div>
        <span className={statusBadge(link.status === 'accepted' ? 'accepted' : link.status === 'submitted'
          ? (link.analysis_status === 'ready' ? 'ready_for_review' : link.analysis_status === 'processing' ? 'processing' : 'submitted')
          : 'returned')}>
          {link.status === 'accepted' ? 'Accepted' : link.status === 'returned' ? 'Returned'
            : link.status === 'rejected' ? 'Rejected' : link.analysis_status === 'ready' ? 'Ready for review'
              : link.analysis_status === 'processing' ? 'Processing' : link.analysis_status === 'failed' ? 'Analysis failed' : 'Submitted'}
        </span>
      </div>
      {(link.source_page || link.source_snippet) && (
        <p className="text-ink-700">{link.source_page && `Page ${link.source_page}`}{link.source_snippet && ` · “${link.source_snippet}”`}</p>
      )}
      {link.note && <p className="text-ink-600">Note: {link.note}</p>}
      {link.source_context && <p className="text-ink-600"><strong>Source/context:</strong> {link.source_context}</p>}
      {link.submitted_text && (
        <details className="rounded border border-line-200 p-2">
          <summary className="cursor-pointer font-semibold">View submitted text</summary>
          <p className="mt-2 whitespace-pre-wrap text-ink-700">{link.submitted_text}</p>
        </details>
      )}
      {link.analysis_status === 'processing' && <p className="text-ink-600">AI is checking this evidence against the requested fact…</p>}
      {link.analysis_status === 'failed' && (
        <p className="text-danger">AI assessment failed: {link.analysis_error || 'Check the source and resubmit evidence.'}</p>
      )}
      {link.analysis_status === 'ready' && (
        <div className="rounded-lg border border-brand-500/30 p-3 space-y-1">
          <p><strong>AI assessment (advisory):</strong> <span className="badge-neutral">{link.analysis_outcome.replace(/_/g, ' ')}</span>
            {link.analysis_confidence !== null && ` · ${Math.round(link.analysis_confidence * 100)}% confidence`}</p>
          <p>{link.analysis_summary}</p>
          {link.analysis_quote && <blockquote className="border-l-2 border-brand-500 pl-2 italic">“{link.analysis_quote}”</blockquote>}
          <p className="text-ink-500">
            {link.analysis_document_reference || link.document_filename}
            {link.analysis_page_number ? ` · page ${link.analysis_page_number}` : ''}
            {link.analysis_suggested_value !== null && link.analysis_suggested_value !== undefined
              ? ` · suggested value: ${fmt(link.analysis_suggested_value)}` : ''}
          </p>
          <p className="text-[11px] text-ink-500">AI never confirms the fact. A different authorized reviewer must decide.</p>
        </div>
      )}
      {link.status !== 'submitted' && (
        <p className="text-ink-600">{link.status === 'accepted' ? 'Accepted' : link.status === 'returned' ? 'Returned' : 'Rejected'} by {link.reviewed_by_name}
          {link.review_reason ? `: “${link.review_reason}”` : ''}</p>
      )}

      {canDecide && (
        <div className="space-y-2 pt-1 border-t border-line-200">
          <div className="flex flex-wrap gap-1.5">
            <button className={`btn-sm ${mode === 'accept' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('accept')}>Accept &amp; confirm fact</button>
            <button className={`btn-sm ${mode === 'accept_corrected' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('accept_corrected')}>Accept with correction</button>
            <button className={`btn-sm ${mode === 'return' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('return')}>Return for more evidence</button>
            <button className={`btn-sm ${mode === 'reject' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('reject')}>Reject evidence</button>
          </div>
          {(mode === 'accept' || mode === 'accept_corrected') && (
            <>
              <p className="text-ink-500">The fact's citation will use this submission and the page and quote below.</p>
              {fromThisDoc.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {fromThisDoc.map((s) => (
                    <button key={s.id} className="btn-secondary btn-sm" onClick={() => { setPage(s.source_page); setSnippet(s.source_snippet); }}>
                      Use citation of “{s.field_name}” (p. {s.source_page || '?'})
                    </button>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                <input className="input" placeholder="Page" value={page} onChange={(e) => setPage(e.target.value)} />
                <input className="input sm:col-span-3" placeholder="Snippet" value={snippet} onChange={(e) => setSnippet(e.target.value)} />
              </div>
              {mode === 'accept_corrected' && (
                <label className="block font-semibold text-ink-700">Corrected value
                  <input className="input mt-1 w-full" value={value} onChange={(e) => setValue(e.target.value)} />
                </label>
              )}
            </>
          )}
          {mode && (
            <div className="flex gap-2">
              <input className="input flex-1" placeholder={mode === 'return' ? 'What is missing? (required)'
                : mode === 'reject' ? 'Why does this not qualify? (required)' : 'Note (optional)'}
                value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="btn-primary btn-sm" disabled={busy || ((mode === 'reject' || mode === 'return') && !reason.trim())}
                onClick={async () => { if (await decide()) setMode(''); }}>Save decision</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const SubmitForm: React.FC<{
  sprintId: string; busy: boolean;
  onSubmit: (body: Parameters<typeof submitEvidence>[1]) => Promise<boolean>;
}> = ({ sprintId, busy, onSubmit }) => {
  const { data: docs } = useApiResource<SprintDocument[]>(() => listSprintDocuments(sprintId), [sprintId]);
  const [mode, setMode] = useState<'upload' | 'existing' | 'text'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState('');
  const [text, setText] = useState('');
  const [context, setContext] = useState('');
  const [page, setPage] = useState('');
  const [snippet, setSnippet] = useState('');
  const [note, setNote] = useState('');
  const ready = mode === 'upload' ? !!file : mode === 'existing' ? !!documentId : !!text.trim() && !!context.trim();
  return (
    <section className="space-y-2 border border-brand-500/30 rounded-lg p-3 text-xs">
      <h3 className="eyebrow">Submit evidence</h3>
      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'upload'} onChange={() => setMode('upload')} /> Upload a new document</label>
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'existing'} onChange={() => setMode('existing')} /> Use a document already in this sprint</label>
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'text'} onChange={() => setMode('text')} /> Paste evidence text</label>
      </div>
      {mode === 'upload' ? (
        <div>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <p className="text-ink-500 mt-1">The document will use the normal OCR and extraction pipeline. Any other facts remain separate review suggestions.</p>
        </div>
      ) : mode === 'existing' ? (
        <select className="input w-full" value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
          <option value="">Choose a document</option>
          {(docs || []).map((d) => <option key={d.id} value={d.id}>{d.original_filename || d.title}</option>)}
        </select>
      ) : (
        <div className="space-y-2">
          <textarea className="input w-full min-h-[120px]" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Paste the exact evidence text here" />
          <input className="input w-full" value={context} onChange={(e) => setContext(e.target.value)}
            placeholder="Source or context, e.g. signed HR register, dated 15 June 2026" />
        </div>
      )}
      {mode !== 'text' && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
          <input className="input" placeholder="Page (optional)" value={page} onChange={(e) => setPage(e.target.value)} />
          <input className="input sm:col-span-3" placeholder="Quote the line that shows it (optional)" value={snippet} onChange={(e) => setSnippet(e.target.value)} />
        </div>
      )}
      <input className="input w-full" placeholder="Note for the reviewer (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn-primary btn-sm" disabled={busy || !ready}
        onClick={async () => {
          const body = mode === 'upload' ? { file, source_page: page, source_snippet: snippet, note }
            : mode === 'existing' ? { document_id: documentId, source_page: page, source_snippet: snippet, note }
              : { submitted_text: text, source_context: context, note };
          const ok = await onSubmit(body);
          if (ok) { setFile(null); setDocumentId(''); setText(''); setContext(''); setPage(''); setSnippet(''); setNote(''); }
        }}>
        {busy ? 'Submitting...' : 'Submit evidence'}
      </button>
    </section>
  );
};

const WithdrawForm: React.FC<{ busy: boolean; onWithdraw: (reason: string) => Promise<boolean> }> = ({ busy, onWithdraw }) => {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  if (!open) {
    return <button className="text-xs font-semibold text-danger hover:underline" onClick={() => setOpen(true)}>Withdraw this request…</button>;
  }
  return (
    <div className="flex gap-2 text-xs">
      <input className="input flex-1" placeholder="Why is it withdrawn? (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <button className="btn-secondary btn-sm" disabled={busy || !reason.trim()} onClick={() => onWithdraw(reason)}>Withdraw</button>
      <button className="btn-secondary btn-sm" onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
};

const CommentForm: React.FC<{ busy: boolean; onComment: (note: string) => Promise<boolean> }> = ({ busy, onComment }) => {
  const [note, setNote] = useState('');
  return (
    <div className="flex gap-2 text-xs">
      <input className="input flex-1" placeholder="Add a comment" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn-secondary btn-sm" disabled={busy || !note.trim()}
        onClick={async () => { if (await onComment(note)) setNote(''); }}>Comment</button>
    </div>
  );
};
