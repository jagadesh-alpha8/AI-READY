import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, CheckCircle2, Circle, Clock, Info, ListChecks,
} from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { listSprintGaps } from '../../api/gaps';
import { listSprintFacts } from '../../api/facts';
import { listRecommendations } from '../../api/recommendations';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { FilterPills, PageHeader, TabStrip } from '../../components/PageHeader';
import type { Fact, Gap, Recommendation, RecommendationPriority, Sprint } from '../../types';
import { useAccess } from '../../utils/access';

/**
 * Goals & Tasks — who owes what, derived from the audit's own work items.
 *
 * ⚠ This module has NO BACKEND. There is no Task model, no Goal model and no
 * endpoint; `apps/` has twelve Django apps and none of them is one of these.
 * So rather than seed a convincing task list nobody can act on, this page
 * derives the real outstanding work from records that DO exist and that
 * already carry an owner role:
 *
 *   Tasks — open gaps, and extracted facts still awaiting confirmation
 *   Goals — the recommendations the audit generated
 *
 * That makes every row real and actionable *somewhere* — each links to the
 * screen that actually resolves it. What it cannot do is create a task,
 * assign one to a named person, or set a due date: all three need storage
 * that does not exist. The page says so rather than implying otherwise.
 */

type Tab = 'tasks' | 'goals';

interface WorkItem {
  id: string;
  title: string;
  detail: string;
  ownerRole: string;
  pillar: string;
  priority: RecommendationPriority;
  source: 'gap' | 'fact';
  impact: number;
  inProgress: boolean;
}

const PRIORITY_BADGE: Record<RecommendationPriority, string> = {
  blocking: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
  optional: 'badge-neutral',
};

const PRIORITY_RANK: RecommendationPriority[] = ['blocking', 'high', 'medium', 'optional'];

const UNASSIGNED = 'Unassigned';

function humanRole(role: string): string {
  if (!role) return UNASSIGNED;
  return role.replace(/_/g, ' ').toLowerCase();
}

/** How many items one role's list shows before it asks you to use the real
 * workspace. A processed sprint carries hundreds; a wall of them is not a
 * work queue, it is a scroll. */
const PER_ROLE_LIMIT = 25;

export const GoalsTasks: React.FC = () => {
  const { can, canSee } = useAccess();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('tasks');
  const [sprintId, setSprintId] = useState('');
  const [role, setRole] = useState<string>('all');

  const { data: sprints, loading: sprintsLoading, error: sprintsError, refetch: refetchSprints } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = sprintId || sprints?.[0]?.id || '';

  const { data: gaps, loading: gapsLoading, error: gapsError, refetch: refetchGaps } =
    useApiResource<Gap[]>(() => listSprintGaps(activeSprintId), [activeSprintId], !!activeSprintId);

  const { data: facts } = useApiResource<Fact[]>(
    () => listSprintFacts(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  const { data: recommendations } = useApiResource<Recommendation[]>(
    () => listRecommendations(activeSprintId), [activeSprintId], !!activeSprintId,
  );

  /** Every outstanding item, from the two record types that carry owners. */
  const tasks = useMemo<WorkItem[]>(() => {
    const fromGaps = (gaps ?? [])
      .filter((g) => g.status === 'open' || g.status === 'in_progress')
      .map<WorkItem>((g) => ({
        id: `gap-${g.id}`,
        title: g.title,
        detail: g.description || `${g.gap_type.replace(/_/g, ' ')} gap`,
        ownerRole: g.owner_role || '',
        pillar: g.pillar_label || g.pillar,
        priority: g.priority,
        source: 'gap',
        impact: g.score_impact || 0,
        inProgress: g.status === 'in_progress',
      }));

    const fromFacts = (facts ?? [])
      .filter((f) => f.status === 'extracted')
      .map<WorkItem>((f) => ({
        id: `fact-${f.id}`,
        title: `Confirm "${f.field_name || f.field_key}"`,
        detail: 'Extracted from a document but not yet confirmed by its owner.',
        ownerRole: f.owner_role || '',
        pillar: f.pillar_label || f.pillar,
        priority: 'medium',
        source: 'fact',
        impact: 0,
        inProgress: false,
      }));

    return [...fromGaps, ...fromFacts].sort(
      (a, b) => PRIORITY_RANK.indexOf(a.priority) - PRIORITY_RANK.indexOf(b.priority),
    );
  }, [gaps, facts]);

  const roles = useMemo(() => {
    const counts = new Map<string, number>();
    tasks.forEach((t) => {
      const key = t.ownerRole || UNASSIGNED;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [tasks]);

  const visibleTasks = role === 'all' ? tasks : tasks.filter((t) => (t.ownerRole || UNASSIGNED) === role);
  const shown = visibleTasks.slice(0, PER_ROLE_LIMIT);
  const hidden = visibleTasks.length - shown.length;

  const goals = useMemo(
    () => (recommendations ?? []).filter((r) => r.status !== 'hidden'),
    [recommendations],
  );

  if (sprintsLoading) return <LoadingState message="Loading sprints…" />;
  if (sprintsError) return <ErrorState message={sprintsError} onRetry={refetchSprints} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={ListChecks}
          title="Goals & Tasks"
          description="Who owes what — the outstanding work from the audit, by the role that owns it."
        />
        <EmptyState
          message="No sprints yet. Work items come from a discovery sprint's gaps and facts."
          action={can('sprint.manage') ? { label: 'Start a sprint', onClick: () => navigate('/sprint/setup') } : undefined}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={ListChecks}
        title="Goals & Tasks"
        description="Who owes what — the outstanding work from the audit, by the role that owns it."
      />

      <div className="glass-card p-4">
        <label className="label" htmlFor="work-sprint">Sprint</label>
        <select
          id="work-sprint"
          value={activeSprintId}
          onChange={(e) => { setSprintId(e.target.value); setRole('all'); }}
          className="input"
        >
          {sprints.map((s) => (
            <option key={s.id} value={s.id}>
              {s.institution_name || s.name || 'Institution'} · {s.sprint_code} ({s.status.replace(/_/g, ' ')})
            </option>
          ))}
        </select>
      </div>

      {/* The limitation, stated once and plainly. */}
      <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600 min-w-0">
          <strong className="text-info">Read-only view. </strong>
          These are the audit's real outstanding items, grouped by the role that owns them. Creating
          a task, assigning one to a named person or setting a due date needs a tasks backend, which
          does not exist yet — every row here links to the screen that actually resolves it.
        </p>
      </div>

      {gapsError && <ErrorState message={gapsError} onRetry={refetchGaps} />}
      {gapsLoading && <LoadingState message="Loading work items…" />}

      {!gapsLoading && !gapsError && (
        <>
          <TabStrip
            tabs={[
              { id: 'tasks', label: 'Tasks', count: tasks.length },
              { id: 'goals', label: 'Goals', count: goals.length },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === 'tasks' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <Metric label="Outstanding" value={tasks.length} />
                <Metric
                  label="Blocking"
                  value={tasks.filter((t) => t.priority === 'blocking').length}
                  tone="danger"
                />
                <Metric label="In progress" value={tasks.filter((t) => t.inProgress).length} />
                <Metric label="Roles involved" value={roles.length} />
              </div>

              {tasks.length === 0 ? (
                <EmptyState message="Nothing outstanding on this sprint." />
              ) : (
                <>
                  <FilterPills
                    options={[
                      { id: 'all', label: 'Everyone', count: tasks.length },
                      ...roles.map(([r, count]) => ({ id: r, label: humanRole(r), count })),
                    ]}
                    active={role}
                    onChange={setRole}
                  />

                  <div className="space-y-2">
                    {shown.map((item) => (
                      <div key={item.id} className="glass-card p-4 flex items-start gap-3">
                        {item.inProgress
                          ? <Clock className="w-4 h-4 text-info shrink-0 mt-0.5" />
                          : <Circle className="w-4 h-4 text-ink-500/50 shrink-0 mt-0.5" />}

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-ink-900">{item.title}</p>
                          {/* Gap descriptions are full explanatory paragraphs —
                              rendered whole they made each row 504px tall and
                              the page 15,000px. Two lines is enough to
                              recognise the item; the workspace has the rest. */}
                          <p className="text-xs text-ink-600 mt-0.5 line-clamp-2">{item.detail}</p>
                          <p className="text-xs text-ink-500 mt-1">
                            {[humanRole(item.ownerRole), item.pillar, item.source === 'gap' ? 'gap' : 'fact review']
                              .filter(Boolean).join(' · ')}
                          </p>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          {item.impact > 0 && (
                            <span className="badge badge-warning">−{item.impact.toFixed(1)}</span>
                          )}
                          <span className={`badge ${PRIORITY_BADGE[item.priority]}`}>{item.priority}</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {hidden > 0 && (
                    <p className="text-sm text-ink-500">
                      Showing {shown.length} of {visibleTasks.length}. The rest are in the workspaces
                      below, where they can be filtered and resolved.
                    </p>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {canSee('sprint-confirmation') && (
                      <button
                        type="button"
                        onClick={() => navigate(`/sprint/${activeSprintId}/confirmation`)}
                        className="btn-secondary btn-sm"
                      >
                        <span>Owner workspace</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => navigate(`/sprint/${activeSprintId}/gaps`)}
                      className="btn-ghost btn-sm"
                    >
                      <span>Gap dashboard</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(`/sprint/${activeSprintId}/facts`)}
                      className="btn-ghost btn-sm"
                    >
                      <span>Facts review</span>
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === 'goals' && <Goals goals={goals} sprintId={activeSprintId} />}
        </>
      )}
    </div>
  );
};

// ===== GOALS =====
const Goals: React.FC<{ goals: Recommendation[]; sprintId: string }> = ({ goals, sprintId }) => {
  const navigate = useNavigate();

  if (goals.length === 0) {
    return (
      <EmptyState
        message="No goals yet. They come from the audit's recommendations — generate those first."
        action={{
          label: 'Open recommendations',
          onClick: () => navigate(`/sprint/${sprintId}/recommendations`),
        }}
      />
    );
  }

  const completed = goals.filter((g) => g.status === 'completed').length;
  const accepted = goals.filter((g) => g.status === 'accepted' || g.status === 'edited').length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <Metric label="Goals" value={goals.length} />
        <Metric label="Accepted" value={accepted} />
        <Metric label="Completed" value={completed} tone={completed > 0 ? 'success' : 'default'} />
      </div>

      <div className="space-y-2">
        {goals.map((goal) => (
          <div key={goal.id} className="glass-card p-4 flex items-start gap-3">
            {goal.status === 'completed'
              ? <CheckCircle2 className="w-4 h-4 text-success shrink-0 mt-0.5" />
              : <Circle className="w-4 h-4 text-ink-500/50 shrink-0 mt-0.5" />}

            <div className="flex-1 min-w-0">
              <p
                className={`text-sm font-semibold ${
                  goal.status === 'completed' ? 'text-ink-500 line-through' : 'text-ink-900'
                }`}
              >
                {goal.title}
              </p>
              <p className="text-xs text-ink-500 mt-1">
                {[
                  goal.pillar_label,
                  goal.owner_role ? humanRole(goal.owner_role) : '',
                  goal.timeline,
                  goal.status,
                ].filter(Boolean).join(' · ')}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {goal.expected_cri_lift > 0 && (
                <span className="badge badge-success">+{goal.expected_cri_lift.toFixed(1)}</span>
              )}
              <span className={`badge ${PRIORITY_BADGE[goal.priority]}`}>{goal.priority}</span>
            </div>
          </div>
        ))}
      </div>

      <p className="text-sm text-ink-500 flex items-start gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        A goal has no progress percentage here because nothing measures one — the audit tracks a
        recommendation's status, not how far through it an institution is.
      </p>

      <button
        type="button"
        onClick={() => navigate(`/sprint/${sprintId}/recommendations`)}
        className="btn-secondary btn-sm"
      >
        <span>Edit in the recommendations workspace</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

const Metric: React.FC<{
  label: string;
  value: number;
  tone?: 'default' | 'danger' | 'success';
}> = ({ label, value, tone = 'default' }) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p
      className={`text-2xl font-bold mt-1 tabular-nums ${
        tone === 'danger' ? 'text-danger' : tone === 'success' ? 'text-success' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);
