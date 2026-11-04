import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Pill, Stat } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { addTask, getPlan, updateInitiative, updateTask } from '../services/assessments';
import type { ImprovementPlan, PlanInitiative, PlanStatus, Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { date, initials } from '../utils/format';

const STATUSES: PlanStatus[] = ['planned', 'active', 'blocked', 'complete'];
const today = () => new Date().toISOString().slice(0, 10);

export function GoalsTasks() {
  return <RequireSprint>{(sprint) => <GoalsBody sprint={sprint} />}</RequireSprint>;
}

/** Programme → goal (initiative) → task → closure evidence. Completing a task never changes the CRI by itself. */
function GoalsBody({ sprint }: { sprint: Sprint }) {
  const { can, role } = useAccess();
  const { cycleId } = useCycle(sprint.institution_id);
  const plan = useResource<ImprovementPlan>(() => getPlan(cycleId), `plan:${cycleId}`, !!cycleId);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState<PlanInitiative | null>(null);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const editable = can('facts.review') && !!role; // the server lets staff and the college (not viewers) edit

  if (!cycleId) return <><PageHeading page="goals" /><Empty title="No transformation plan yet" action={<PageLink to="plan">Transformation plan</PageLink>}>Goals come from the plan generated after a finalized assessment.</Empty></>;
  if (plan.loading) return <Loading label="Loading goals and tasks…" />;
  if (plan.error) return <ErrorState error={plan.error} onRetry={() => void plan.refetch()} />;

  const items = plan.data!.gaps.flatMap((g) => g.initiatives.map((i) => ({ gap: g, i })));
  const tasks = items.flatMap(({ i }) => i.tasks);
  const overdue = tasks.filter((t) => t.status !== 'complete' && t.due_date && t.due_date < today()).length;
  const closed = plan.data!.gaps.filter((g) => g.status === 'closed' || g.status === 'validated').length;

  const save = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(null);
    try { await fn(); await plan.refetch(); setMsg({ tone: 'success', text: ok }); } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
  };

  return (
    <>
      <PageHeading page="goals" />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Notice tone="info">Completing a task does not change the CRI. Verified closure evidence and a reassessment do.</Notice>
      <div className="stat-grid">
        <Stat label="Active goals" value={items.filter(({ i }) => i.status !== 'complete').length} note={`${items.length} in the plan`} />
        <Stat label="Tasks complete" value={`${plan.data!.summary.tasks_done} / ${plan.data!.summary.tasks}`} note={plan.data!.summary.tasks ? `${Math.round((plan.data!.summary.tasks_done / plan.data!.summary.tasks) * 100)}% delivered` : 'No tasks yet'} />
        <Stat label="Overdue" value={overdue} note="Past due, not complete" />
        <Stat label="Closure evidence" value={`${closed} / ${plan.data!.gaps.length}`} note="Gaps validated with evidence" />
      </div>
      {items.length === 0 ? <Empty title="No goals in the plan yet" /> : (
        <div className="action-list">
          {items.map(({ gap, i }, idx) => (
            <article key={i.id} className="action-row-wrap">
              <div className="action-row">
                <span>G{idx + 1}</span>
                <button className="action-title" aria-expanded={open === i.id} onClick={() => setOpen(open === i.id ? null : i.id)}>
                  <strong>{i.title}</strong>
                  <small>{gap.benchmark_code} · closure evidence: {i.expected_evidence || gap.closing_evidence_title || 'to be defined'}</small>
                </button>
                <span className="owner"><i>{initials(i.owner || '?')}</i>{i.owner || 'Unassigned'}</span>
                <span className="due">Due {date(i.target_date)}</span>
                {editable ? (
                  <select aria-label={`Status of ${i.title}`} value={i.status} onChange={(e) => void save(() => updateInitiative(i.id, { status: e.target.value as PlanStatus }), 'Goal updated.')}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                ) : <Pill status={i.status} label={i.status_label} />}
              </div>
              {open === i.id && (
                <div className="task-list">
                  {i.tasks.length === 0 && <p className="muted">No tasks yet.</p>}
                  {i.tasks.map((t) => (
                    <div key={t.id} className="task-row">
                      <span><b>{t.title}</b><small className="cell-sub">Owner {t.owner || '—'} · due {date(t.due_date)}{t.evidence_due && ` · evidence: ${t.evidence_due}`}</small></span>
                      {editable ? (
                        <select aria-label={`Status of ${t.title}`} value={t.status} onChange={(e) => void save(() => updateTask(t.id, { status: e.target.value as PlanStatus }), 'Task updated.')}>
                          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      ) : <Pill status={t.status} label={t.status_label} />}
                    </div>
                  ))}
                  {editable && <button className="secondary-button" onClick={() => setAdding(i)}>Add task</button>}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      {adding && (
        <ActionDialog
          title={`Add task to "${adding.title}"`}
          fields={[{ name: 'title', label: 'Action', required: true }, { name: 'owner', label: 'Owner' }, { name: 'due_date', label: 'Due date', type: 'date' }]}
          confirmLabel="Add task"
          onSubmit={async (v) => {
            await addTask(adding.id, { title: v.title, owner: v.owner || undefined, due_date: v.due_date || undefined });
            await plan.refetch();
            setOpen(adding.id);
            setMsg({ tone: 'success', text: 'Task added.' });
          }}
          onClose={() => setAdding(null)}
        />
      )}
    </>
  );
}
