import React, { useState } from 'react';
import { CheckCircle2, ListChecks, Plus, Target } from 'lucide-react';

import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import {
  addTask, generatePlan, getCycleBenchmark, getPlan, updateGap, updateInitiative, updateTask, validateGap,
} from '../../api/assessments';
import type { ImprovementPlan, PlanGap, PlanInitiative, PlanStatus, PlanTask } from '../../api/assessments';

/**
 * Stage 6: the improvement plan of a finalized assessment. Staff generate it
 * (typed gaps from the frozen scores, an initiative per gap from the
 * benchmark's template or its unmet evidence requests) and decide on gaps; the
 * college runs the initiatives and tasks. A gap is only "validated" by linking
 * accepted evidence for the same benchmark, and only a validated gap closes.
 */

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'badge-danger', high: 'badge-warning', medium: 'badge-brand', low: 'badge-neutral',
};
const GAP_STATUS_BADGE: Record<string, string> = {
  open: 'badge-warning', planned: 'badge-neutral', in_progress: 'badge-brand', validated: 'badge-success', closed: 'badge-success',
};
const PLAN_STATUSES: PlanStatus[] = ['planned', 'active', 'blocked', 'complete'];

export const PlanPanel: React.FC<{ cycleId: string; staff: boolean; canEdit: boolean }> = ({ cycleId, staff, canEdit }) => {
  const plan = useApiResource<ImprovementPlan>(() => getPlan(cycleId), [cycleId]);
  const [err, setErr] = useState('');

  if (plan.loading) return <LoadingState message="Loading improvement plan…" />;
  if (plan.error || !plan.data) return <ErrorState message={plan.error || 'Not found'} onRetry={plan.refetch} />;
  const p = plan.data;

  return (
    <div className="rounded-lg border border-line-200 bg-surface p-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Target className="w-4 h-4 text-brand-800" />
        <p className="font-bold text-ink-900 flex-1">Improvement plan</p>
        {p.has_plan && (
          <span className="text-ink-500">
            {p.summary.open} of {p.summary.gaps} gaps open{p.summary.critical_open ? ` (${p.summary.critical_open} critical)` : ''}
            {' · '}{p.summary.tasks_done}/{p.summary.tasks} tasks done
          </span>
        )}
      </div>
      {!p.has_plan && (
        <div className="space-y-2">
          <p className="text-ink-500">
            No plan yet. Generating one turns every shortfall in the scorecard into a typed gap (capability, compliance,
            evidence, outcome) with an initiative and tasks, due by severity.
          </p>
          {staff && (
            <button className="btn-primary btn-sm" onClick={async () => {
              setErr('');
              try { await generatePlan(cycleId); plan.refetch(); } catch (e) { setErr(getErrorMessage(e)); }
            }}><ListChecks className="w-3.5 h-3.5" /> Generate the improvement plan</button>
          )}
        </div>
      )}
      {p.gaps.map((g) => <GapCard key={g.id} cycleId={cycleId} g={g} staff={staff} canEdit={canEdit} onChanged={plan.refetch} />)}
      {p.has_plan && p.gaps.length === 0 && <p className="text-ink-500">No gaps: every benchmark met its target.</p>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const GapCard: React.FC<{ cycleId: string; g: PlanGap; staff: boolean; canEdit: boolean; onChanged: () => void }> = (
  { cycleId, g, staff, canEdit, onChanged },
) => {
  const [open, setOpen] = useState(g.status !== 'closed');
  const [err, setErr] = useState('');
  const [validating, setValidating] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setErr('');
    try { await fn(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="glass-card p-3 space-y-2">
      <button className="w-full text-left flex items-center gap-2 flex-wrap" onClick={() => setOpen(!open)}>
        <span className={`badge ${SEVERITY_BADGE[g.severity]}`}>{g.severity_label}</span>
        <span className="badge badge-neutral">{g.type_label}</span>
        <span className="font-mono text-ink-500">{g.benchmark_code}</span>
        <span className="text-ink-900 flex-1 min-w-0">{g.description}</span>
        <span className={`badge ${GAP_STATUS_BADGE[g.status]}`}>{g.status_label}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-line-200 pt-2">
          {g.root_cause && <p className="text-ink-500">Why: {g.root_cause}</p>}
          {g.closing_evidence_title && (
            <p className="text-success">
              Validated by “{g.closing_evidence_title}” — {g.validated_by}{g.validation_note ? `: ${g.validation_note}` : ''}
            </p>
          )}
          {staff && !['validated', 'closed'].includes(g.status) && (
            <div className="flex flex-wrap gap-2 items-center">
              <select className="input text-xs w-auto" value={g.status}
                onChange={(e) => run(() => updateGap(g.id, { status: e.target.value as PlanGap['status'] }))}>
                <option value="open">Open</option>
                <option value="planned">Planned</option>
                <option value="in_progress">In progress</option>
              </select>
              {!validating && (
                <button className="btn-secondary btn-sm" onClick={() => setValidating(true)}>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Validate with accepted evidence
                </button>
              )}
            </div>
          )}
          {validating && <ValidateForm cycleId={cycleId} g={g} onDone={() => { setValidating(false); onChanged(); }} onCancel={() => setValidating(false)} />}
          {staff && g.status === 'validated' && (
            <button className="btn-primary btn-sm" onClick={() => run(() => updateGap(g.id, { status: 'closed' }))}>Close gap</button>
          )}
          {g.initiatives.map((i) => <InitiativeCard key={i.id} i={i} canEdit={canEdit} onChanged={onChanged} />)}
          {err && <InlineError message={err} onDismiss={() => setErr('')} />}
        </div>
      )}
    </div>
  );
};

const ValidateForm: React.FC<{ cycleId: string; g: PlanGap; onDone: () => void; onCancel: () => void }> = (
  { cycleId, g, onDone, onCancel },
) => {
  // Accepted evidence for this benchmark in this assessment; evidence from a later
  // re-assessment can be linked through the API as well.
  const detail = useApiResource(() => getCycleBenchmark(cycleId, g.benchmark_code), [cycleId, g.benchmark_code]);
  const [item, setItem] = useState('');
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const accepted = (detail.data?.requests || []).flatMap((r) => r.items).filter((x) => x.status === 'accepted');
  return (
    <div className="rounded-lg border border-line-200 p-2 space-y-2">
      <select className="input text-xs" value={item} onChange={(e) => setItem(e.target.value)}>
        <option value="">Choose accepted evidence…</option>
        {accepted.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
      </select>
      <input className="input text-xs" placeholder="How does this evidence show the gap is closed?" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex gap-2">
        <button className="btn-primary btn-sm" disabled={!item || !note.trim()} onClick={async () => {
          setErr('');
          try { await validateGap(g.id, { evidence_item: item, note }); onDone(); } catch (e) { setErr(getErrorMessage(e)); }
        }}>Validate</button>
        <button className="btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {accepted.length === 0 && !detail.loading && <p className="text-ink-500">No accepted evidence for {g.benchmark_code} in this assessment yet.</p>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const InitiativeCard: React.FC<{ i: PlanInitiative; canEdit: boolean; onChanged: () => void }> = ({ i, canEdit, onChanged }) => {
  const [newTask, setNewTask] = useState('');
  const [err, setErr] = useState('');
  const run = async (fn: () => Promise<unknown>) => {
    setErr('');
    try { await fn(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <div className="rounded-lg border border-line-200 bg-surface p-2 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-bold text-ink-900 flex-1 min-w-0">{i.title}</span>
        {i.from_template && <span className="badge badge-brand">expert template</span>}
        {canEdit ? (
          <>
            <input className="input text-xs w-40" placeholder="Owner" defaultValue={i.owner}
              onBlur={(e) => e.target.value !== i.owner && run(() => updateInitiative(i.id, { owner: e.target.value }))} />
            <input className="input text-xs w-36" type="date" defaultValue={i.target_date || ''}
              onBlur={(e) => e.target.value !== (i.target_date || '') && run(() => updateInitiative(i.id, { target_date: e.target.value }))} />
            <select className="input text-xs w-auto" value={i.status} onChange={(e) => run(() => updateInitiative(i.id, { status: e.target.value as PlanStatus }))}>
              {PLAN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </>
        ) : <span className="text-ink-500">{i.owner || 'no owner'} · due {i.target_date || '—'} · {i.status_label}</span>}
      </div>
      {i.description && i.description !== i.title && <p className="text-ink-600">{i.description}</p>}
      {i.expected_evidence && <p className="text-ink-500">Evidence expected: {i.expected_evidence}</p>}
      {i.expected_outcome && <p className="text-ink-500">Outcome expected: {i.expected_outcome}</p>}
      <div className="space-y-1">
        {i.tasks.map((t) => <TaskRow key={t.id} t={t} canEdit={canEdit} onChanged={onChanged} />)}
      </div>
      {canEdit && (
        <div className="flex gap-2">
          <input className="input text-xs flex-1" placeholder="Add a task" value={newTask} onChange={(e) => setNewTask(e.target.value)} />
          <button className="btn-secondary btn-sm" disabled={!newTask.trim()} onClick={() => run(async () => { await addTask(i.id, { title: newTask }); setNewTask(''); })}>
            <Plus className="w-3.5 h-3.5" /> Add
          </button>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const TaskRow: React.FC<{ t: PlanTask; canEdit: boolean; onChanged: () => void }> = ({ t, canEdit, onChanged }) => {
  const [err, setErr] = useState('');
  const run = async (fn: () => Promise<unknown>) => {
    setErr('');
    try { await fn(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className={`flex-1 min-w-0 ${t.status === 'complete' ? 'line-through text-ink-400' : 'text-ink-700'}`}>• {t.title}</span>
      {canEdit ? (
        <>
          <input className="input text-xs w-36" placeholder="Owner" defaultValue={t.owner}
            onBlur={(e) => e.target.value !== t.owner && run(() => updateTask(t.id, { owner: e.target.value }))} />
          <input className="input text-xs w-36" type="date" defaultValue={t.due_date || ''}
            onBlur={(e) => e.target.value !== (t.due_date || '') && run(() => updateTask(t.id, { due_date: e.target.value }))} />
          <select className="input text-xs w-auto" value={t.status} onChange={(e) => run(() => updateTask(t.id, { status: e.target.value as PlanStatus }))}>
            {PLAN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </>
      ) : <span className="text-ink-500">{t.owner || '—'} · {t.due_date || '—'} · {t.status_label}</span>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};
