import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';

import { assignFact, confirmFact, correctFact, getFact, rejectFact } from '../../api/facts';
import { assignGap, getGap, markGapUnavailable, resolveGap, skipGap } from '../../api/gaps';
import { InlineError } from '../../components/ApiStates';
import type { EvidenceAssignee, Fact, Gap } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { ConflictComparisonDialog } from '../gaps/ConflictComparison';
import { GapSnippetCell } from '../gaps/GapSnippetCell';
import { LowConfidenceGapPanel } from '../gaps/LowConfidenceGapPanel';
import { RequestEvidenceModal } from './RequestEvidenceModal';
import { eligibleAssignees } from './ownerTasks.ts';
import type { OwnerTask } from './ownerTasks.ts';

const fmt = (v: unknown) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '—'));
const GAP_LABEL: Record<string, string> = {
  unconfirmed_fact: 'Needs confirmation', low_confidence: 'Low confidence', conflict: 'Conflict',
  missing_document: 'Missing document', stale_data: 'Stale data',
};

/**
 * One task of the Owner Workspace: what it is and where it comes from (snippet, page, document), who owns
 * it, who it is assigned to and by when, its evidence request, its history -- and the actions the current
 * user may take. When they may not, it says who may (the server's own reason).
 */
export const OwnerTaskCard: React.FC<{
  task: OwnerTask;
  sprintId: string;
  coordinator: boolean;
  people: EvidenceAssignee[];
  onChanged: () => void;
}> = ({ task, sprintId, coordinator, people, onChanged }) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [mode, setMode] = useState<'' | 'correct' | 'reject' | 'close' | 'assign'>('');
  const [text, setText] = useState('');
  const [assignee, setAssignee] = useState(task.assignedTo || '');
  const [due, setDue] = useState(task.dueDate || '');
  const [history, setHistory] = useState<Fact['review_history'] | Gap['events'] | null>(null);
  const [panel, setPanel] = useState<'' | 'evidence' | 'compare' | 'lowconf'>('');
  const f = task.fact;
  const g = task.gap;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr('');
    try {
      await fn();
      setMode('');
      setText('');
      onChanged();
    } catch (e) {
      setErr(getErrorMessage(e, 'The action failed.'));
    } finally {
      setBusy(false);
    }
  };
  const toggleHistory = async () => {
    if (history) { setHistory(null); return; }
    try {
      setHistory(f ? (await getFact(f.id)).data.review_history || [] : (await getGap(g!.id)).data.events || []);
    } catch (e) { setErr(getErrorMessage(e, 'Could not load the history.')); }
  };

  const openRequest = f?.open_evidence_request || (g?.evidence_request && ['open', 'submitted', 'returned'].includes(g.evidence_request.status) ? g.evidence_request : null);
  const title = f ? `${f.field_name}: ${fmt(f.value_json)}` : g!.title;
  const statusLabel = (task.status || '').replace(/_/g, ' ');

  return (
    <div className="p-4 bg-surface rounded-xl border border-line-200 space-y-2 text-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="text-[11px] font-bold uppercase tracking-wide text-brand-800">
            {f ? `Fact · ${f.pillar_label || f.pillar || 'no pillar'}` : `Gap · ${GAP_LABEL[g!.gap_type] || g!.gap_type}`}
          </span>
          <p className="text-sm font-bold text-ink-900 mt-0.5 break-words">{title}</p>
        </div>
        <span className={task.status === 'needs_replacement' ? 'badge-danger' : 'badge-neutral'}>{statusLabel}</span>
      </div>

      <p className="text-ink-600">
        Owner role <strong>{task.ownerLabel}</strong>
        {' · '}{task.assignedTo ? <>assigned to <strong>{task.assignedName}</strong></> : <span className="text-warning font-semibold">unassigned</span>}
        {task.dueDate && <> · <span className={task.overdue ? 'text-danger font-semibold' : ''}>due {task.dueDate}{task.overdue ? ' (overdue)' : ''}</span></>}
      </p>

      {f ? (
        <p className="text-ink-600 italic break-words">
          {f.source_snippet ? `“${f.source_snippet}”` : 'No snippet recorded'}
          <span className="not-italic text-ink-500"> · {f.source_page ? `page ${f.source_page}` : 'page not recorded'}
            {f.source_document_filename ? ` · ${f.source_document_filename}` : ''}
            {` · confidence ${(f.confidence * 100).toFixed(0)}%`}</span>
        </p>
      ) : (
        <GapSnippetCell gap={g!} />
      )}

      {openRequest && (
        <p className="text-ink-700">
          Evidence request:{' '}
          <Link to={`/evidence-requests?view=all&id=${openRequest.id}`} className="font-semibold text-accent hover:underline">
            {openRequest.status_label}{openRequest.assigned_to_name ? ` · ${openRequest.assigned_to_name}` : ' · not assigned'}
          </Link>
        </p>
      )}

      {task.canAct === false && (
        <p className="flex items-start gap-1.5 text-ink-600 bg-line-200/40 rounded-lg px-2 py-1.5">
          <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {task.blockedReason}
        </p>
      )}

      {err && <InlineError message={err} onDismiss={() => setErr('')} />}

      <div className="flex flex-wrap gap-1.5">
        {task.canAct && f && !f.open_evidence_request && (
          <>
            <button className="btn-primary btn-sm" disabled={busy} onClick={() => run(() => confirmFact(f.id, 'Confirmed in the Owner Workspace'))}>Confirm</button>
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => { setMode('correct'); setText(fmt(f.value_json)); }}>Correct</button>
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => { setMode('reject'); setText(''); }}>Reject</button>
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => setPanel('evidence')}>Request evidence</button>
          </>
        )}
        {task.canAct && f?.open_evidence_request && (
          <span className="text-ink-500">Decide it on its evidence request.</span>
        )}
        {task.canAct && g && g.gap_type === 'low_confidence' && g.source_fact_id && (
          <button className="btn-primary btn-sm" onClick={() => setPanel('lowconf')}>Review fact</button>
        )}
        {g && g.gap_type === 'conflict' && (
          <button className="btn-secondary btn-sm" onClick={() => setPanel('compare')}>Compare sources</button>
        )}
        {task.canAct && g && g.gap_type !== 'low_confidence' && (
          <>
            <button className="btn-primary btn-sm" disabled={busy || !!g.resolve_blocked_reason}
              title={g.resolve_blocked_reason || undefined}
              onClick={() => run(() => resolveGap(g.id, 'Resolved in the Owner Workspace'))}>Resolve</button>
            <button className="btn-secondary btn-sm" disabled={busy || !!g.close_blocked_reason}
              title={g.close_blocked_reason || undefined}
              onClick={() => { setMode('close'); setText(''); }}>
              {g.gap_type === 'conflict' ? 'Close as unresolved' : 'Skip / not available'}
            </button>
          </>
        )}
        {(g?.gap_type === 'missing_document' || g?.gap_type === 'stale_data') && (
          <Link className="btn-secondary btn-sm" to={`/sprint/${sprintId}/upload`}>Upload Data Pack</Link>
        )}
        {coordinator && (
          <button className="btn-secondary btn-sm" disabled={busy} onClick={() => setMode(mode === 'assign' ? '' : 'assign')}>
            {task.assignedTo ? 'Reassign' : 'Assign'}
          </button>
        )}
        <button className="btn-secondary btn-sm" onClick={toggleHistory}>{history ? 'Hide history' : 'History'}</button>
      </div>

      {task.canAct && g?.resolve_blocked_reason && g.gap_type !== 'low_confidence' && (
        <p className="text-[11px] text-ink-500">{g.resolve_blocked_reason}</p>
      )}

      {mode === 'correct' && f && (
        <div className="flex gap-2">
          <input className="input flex-1" value={text} onChange={(e) => setText(e.target.value)} aria-label="Corrected value" />
          <button className="btn-primary btn-sm" disabled={busy || !text.trim()} onClick={() => {
            const n = Number(text);
            return run(() => correctFact(f.id, text.trim() !== '' && !Number.isNaN(n) ? n : text));
          }}>Save correction</button>
        </div>
      )}
      {(mode === 'reject' || mode === 'close') && (
        <div className="flex gap-2">
          <input className="input flex-1" value={text} onChange={(e) => setText(e.target.value)}
            placeholder={mode === 'reject' ? 'Why is the value wrong? (required)' : 'Why is it closed without a fix? (required)'} />
          <button className="btn-primary btn-sm" disabled={busy || !text.trim()} onClick={() => run(() => (
            mode === 'reject' ? rejectFact(f!.id, text.trim())
              : g!.gap_type === 'missing_document' ? markGapUnavailable(g!.id, text.trim())
                : skipGap(g!.id, g!.gap_type === 'conflict' ? `Closed unresolved: ${text.trim()}` : text.trim())))}>
            {mode === 'reject' ? 'Reject fact' : 'Close gap'}
          </button>
        </div>
      )}
      {mode === 'assign' && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="font-semibold text-ink-700">Assign to
            <select className="input mt-1" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Nobody (unassigned)</option>
              {eligibleAssignees(task, people).map((p) => (
                <option key={p.id} value={p.id}>{p.name} · {p.role.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </label>
          <label className="font-semibold text-ink-700">Due
            <input type="date" className="input mt-1" value={due} min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setDue(e.target.value)} />
          </label>
          <button className="btn-primary btn-sm" disabled={busy} onClick={() => run(() => {
            const body = { assigned_to: assignee || null, due_date: due || null };
            return f ? assignFact(f.id, body) : assignGap(g!.id, body);
          })}>Save</button>
          {eligibleAssignees(task, people).length === 0 && (
            <span className="text-warning">Nobody in this college can take it yet (it needs the {task.ownerLabel} or an Institution Admin).</span>
          )}
        </div>
      )}

      {history && (
        <ol className="border-t border-line-200 pt-2 space-y-1">
          {history.length === 0 && <li className="text-ink-500">No history yet.</li>}
          {history.map((h) => {
            const e = h as { id: string; action: string; action_label?: string; user_name?: string; reason?: string; note?: string; created_at: string };
            return (
              <li key={e.id} className="text-ink-700">
                <span className="text-ink-500">{new Date(e.created_at).toLocaleString()}</span> · <strong>{e.action_label || e.action.replace(/_/g, ' ')}</strong>
                {e.user_name ? ` by ${e.user_name}` : ''}{(e.reason || e.note) ? `: “${e.reason || e.note}”` : ''}
              </li>
            );
          })}
        </ol>
      )}

      {panel === 'evidence' && f && (
        <RequestEvidenceModal fact={f} onClose={() => setPanel('')} onCreated={() => { setPanel(''); onChanged(); }} />
      )}
      {panel === 'compare' && g && <ConflictComparisonDialog gap={g} onClose={() => setPanel('')} />}
      {panel === 'lowconf' && g && <LowConfidenceGapPanel gap={g} onClose={() => setPanel('')} onChanged={onChanged} />}
    </div>
  );
};
