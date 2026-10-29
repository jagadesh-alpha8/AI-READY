import React, { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckSquare, ArrowRight } from 'lucide-react';

import { listEvidenceAssignees } from '../../api/evidenceRequests';
import { listSprintFacts } from '../../api/facts';
import { getWorkSummary, listSprintGaps } from '../../api/gaps';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { useAuth } from '../../context/AuthContext';
import { useApiResource } from '../../hooks/useApiResource';
import type { EvidenceAssignee, Fact, Gap, WorkSummary, WorkSummaryRow } from '../../types';
import { useAccess } from '../../utils/access';
import { OwnerTaskCard } from './OwnerTaskCard';
import { buildTasks, filterTasks, isCoordinator, isMine } from './ownerTasks.ts';
import { isRealSprintId } from '../../utils/selectedSprint';

/**
 * Owner Workspace: the review work of the sprint. "My tasks" = assigned to me, or unassigned and owned by
 * my role; coordinators (Institution Admin, IQAC Coordinator, InGage staff) also get "All sprint tasks"
 * and assign them. Readiness for baseline review is always sprint-wide (GET /sprints/<id>/work-summary),
 * never just the viewer's share. Who may act on an item is the server's call (each item's `can_act`).
 */
export const ConfirmationWorkspace: React.FC = () => {
  const { step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isRealSprint = isRealSprintId(sprintId);
  const coordinator = isCoordinator(user?.role);

  const facts = useApiResource<Fact[]>(() => listSprintFacts(sprintId!), [sprintId], isRealSprint);
  const gaps = useApiResource<Gap[]>(() => listSprintGaps(sprintId!), [sprintId], isRealSprint);
  const summary = useApiResource<WorkSummary>(() => getWorkSummary(sprintId!), [sprintId], isRealSprint);
  const people = useApiResource<EvidenceAssignee[]>(() => listEvidenceAssignees(sprintId!), [sprintId],
    isRealSprint && coordinator);

  const [view, setView] = useState<'mine' | 'all'>('mine');
  const [role, setRole] = useState('all');
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [overdueOnly, setOverdueOnly] = useState(false);

  const tasks = useMemo(() => buildTasks(facts.data || [], gaps.data || []), [facts.data, gaps.data]);
  const mine = useMemo(() => (user ? tasks.filter((t) => isMine(t, { id: user.id, role: user.role })) : []), [tasks, user]);
  const shown = filterTasks(view === 'all' && coordinator ? tasks : mine, { role, unassignedOnly, overdueOnly });
  const roles = useMemo(() => [...new Set(tasks.map((t) => t.ownerRole))].sort(), [tasks]);
  const refresh = () => { facts.refetch(); gaps.refetch(); summary.refetch(); };

  const loading = facts.loading || gaps.loading;
  const error = facts.error || gaps.error;
  const s = summary.data;

  return (
    <div className="space-y-6">
      {/* Workspace Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4" data-tour="owner-workspace-header">
        <span className="badge-accent">Signed in as {user?.role?.replace(/_/g, ' ')}</span>
        <button
          data-tour="owner-proceed-btn"
          onClick={() => navigate(`/sprint/${sprintId}/score`)}
          className="btn-primary shrink-0 self-end sm:self-auto"
        >
          <span>Proceed to Live CRI Preview</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* Sprint-wide readiness: every owner role, whoever is looking. */}
      {summary.error ? <ErrorState message={summary.error} onRetry={summary.refetch} /> : s && (
        <div className="glass-card p-5 space-y-4" data-tour="owner-readiness-card">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="eyebrow">Sprint readiness for baseline review</h2>
              <p className={`text-2xl font-bold mt-1 ${s.ready_for_baseline_review ? 'text-success' : 'text-warning'}`}>
                {s.ready_for_baseline_review ? 'Ready for baseline review' : 'Not ready yet'}
              </p>
              {s.blockers.map((b) => <p key={b} className="text-xs text-ink-600">{b}</p>)}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <Metric label="Facts to review" value={s.totals.pending_facts} />
              <Metric label="Open gaps" value={s.totals.open_gaps} />
              <Metric label="Unassigned" value={s.totals.unassigned} tone={s.totals.unassigned ? 'warning' : undefined} />
              <Metric label="Overdue" value={s.totals.overdue} tone={s.totals.overdue ? 'danger' : undefined} />
            </div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <SummaryTable title="Pending work by owner role" rows={s.by_role} nameOf={(r) => r.label || '—'} />
            <SummaryTable title="Pending work by assignee" rows={s.by_assignee} nameOf={(r) => r.name || '—'} />
          </div>
        </div>
      )}

      <div className="glass-card p-5 sm:p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-2" data-tour="owner-task-filters">
          <button className={`btn-sm ${view === 'mine' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('mine')}>
            My tasks ({mine.length})
          </button>
          {coordinator && (
            <button className={`btn-sm ${view === 'all' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setView('all')}>
              All sprint tasks ({tasks.length})
            </button>
          )}
          <span className="flex-1" />
          <select className="input text-xs w-auto" value={role} onChange={(e) => setRole(e.target.value)} aria-label="Owner role">
            <option value="all">Every owner role</option>
            {roles.map((r) => <option key={r || 'none'} value={r}>{r ? r.replace(/_/g, ' ') : 'No owner role'}</option>)}
          </select>
          <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={unassignedOnly} onChange={(e) => setUnassignedOnly(e.target.checked)} /> Unassigned</label>
          <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} /> Overdue</label>
        </div>
        <p className="text-xs text-ink-500">
          {view === 'all' && coordinator
            ? 'Every open item of the sprint, assigned or not, so nothing drops out of the queue.'
            : 'Items assigned to you, and unassigned items owned by your role.'}
        </p>

        {loading ? <LoadingState message="Loading the workspace..." />
          : error ? <ErrorState message={error} onRetry={refresh} />
            : shown.length === 0 ? (
              <div className="panel-muted"><p className="text-sm text-ink-500">
                {view === 'mine' ? 'Nothing is waiting on you right now.' : 'No open items match these filters.'}
              </p></div>
            ) : (
              <div className="space-y-3" data-tour="owner-task-list">
                {shown.map((t) => (
                  <OwnerTaskCard key={t.key} task={t} sprintId={sprintId!} coordinator={coordinator}
                    people={people.data || []} onChanged={refresh} />
                ))}
              </div>
            )}
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number; tone?: 'warning' | 'danger' }> = ({ label, value, tone }) => (
  <div className="rounded-lg border border-line-200 px-3 py-2">
    <p className="text-ink-500">{label}</p>
    <p className={`text-lg font-bold tabular-nums ${tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : 'text-ink-900'}`}>{value}</p>
  </div>
);

const SummaryTable: React.FC<{ title: string; rows: WorkSummaryRow[]; nameOf: (r: WorkSummaryRow) => string }> = ({ title, rows, nameOf }) => (
  <div className="overflow-x-auto">
    <h3 className="text-xs font-bold text-ink-700 mb-1">{title}</h3>
    {rows.length === 0 ? <p className="text-xs text-ink-500">Nothing outstanding.</p> : (
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-ink-500">
            <th className="py-1 pr-2 font-semibold">Who</th><th className="py-1 px-2 font-semibold text-right">Facts</th>
            <th className="py-1 px-2 font-semibold text-right">Gaps</th><th className="py-1 px-2 font-semibold text-right">Conflicts</th>
            <th className="py-1 px-2 font-semibold text-right">Unassigned</th><th className="py-1 pl-2 font-semibold text-right">Overdue</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.role ?? ''}${r.user_id ?? ''}${nameOf(r)}`} className="border-t border-line-200">
              <td className="py-1 pr-2 text-ink-800">{nameOf(r)}</td>
              <td className="py-1 px-2 text-right tabular-nums">{r.pending_facts}</td>
              <td className="py-1 px-2 text-right tabular-nums">{r.open_gaps}</td>
              <td className="py-1 px-2 text-right tabular-nums">{r.conflicts}</td>
              <td className={`py-1 px-2 text-right tabular-nums ${r.unassigned ? 'text-warning font-semibold' : ''}`}>{r.unassigned}</td>
              <td className={`py-1 pl-2 text-right tabular-nums ${r.overdue ? 'text-danger font-semibold' : ''}`}>{r.overdue}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);
