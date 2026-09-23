import React, { useState } from 'react';
import { CheckCircle2, Circle, Clock, ListChecks } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { FilterPills, PageHeader, TabStrip } from '../../components/PageHeader';
import { GOALS, TASKS } from '../../data/workspaceDemo';
import type { TaskStatus } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's Goals & Tasks page: the working layer
 * beneath the transformation plan — goals with progress, tasks with owners. */

type View = 'tasks' | 'goals';
type Filter = TaskStatus | 'all';

const PRIORITY_BADGE = {
  critical: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
} as const;

const STATUS_LABEL: Record<TaskStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  completed: 'Completed',
};

const StatusIcon: React.FC<{ status: TaskStatus }> = ({ status }) => {
  if (status === 'completed') return <CheckCircle2 className="w-4 h-4 text-success shrink-0" />;
  if (status === 'in_progress') return <Clock className="w-4 h-4 text-info shrink-0" />;
  return <Circle className="w-4 h-4 text-ink-500/50 shrink-0" />;
};

export const GoalsTasks: React.FC = () => {
  const [view, setView] = useState<View>('tasks');
  const [filter, setFilter] = useState<Filter>('all');

  const visibleTasks = filter === 'all' ? TASKS : TASKS.filter((t) => t.status === filter);

  const filterOptions = (['all', 'not_started', 'in_progress', 'completed'] as Filter[]).map((id) => ({
    id,
    label: id === 'all' ? 'All' : STATUS_LABEL[id],
    count: id === 'all' ? TASKS.length : TASKS.filter((t) => t.status === id).length,
  }));

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="Tasks are not assignable yet — nothing saves." />

      <PageHeader
        icon={ListChecks}
        title="Goals & Tasks"
        description="Goals carry progress; tasks carry an owner and a due date. The execution layer under the plan."
      />

      <TabStrip
        tabs={[
          { id: 'tasks', label: 'Tasks', count: TASKS.length },
          { id: 'goals', label: 'Goals', count: GOALS.length },
        ]}
        active={view}
        onChange={setView}
      />

      {view === 'tasks' && (
        <div className="space-y-4">
          <FilterPills options={filterOptions} active={filter} onChange={setFilter} />

          <div className="space-y-2">
            {visibleTasks.map((task) => (
              <div key={task.id} className="glass-card p-4 flex items-center gap-3">
                <StatusIcon status={task.status} />
                <div className="flex-1 min-w-0">
                  <p
                    className={`text-sm font-medium ${
                      task.status === 'completed' ? 'text-ink-500 line-through' : 'text-ink-900'
                    }`}
                  >
                    {task.title}
                  </p>
                  <p className="text-xs text-ink-500">
                    {task.owner} · {task.dept} · due {task.due}
                  </p>
                </div>
                <span className={`badge ${PRIORITY_BADGE[task.priority]} shrink-0`}>{task.priority}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {view === 'goals' && (
        <div className="space-y-3">
          {GOALS.map((goal) => (
            <div key={goal.id} className="glass-card p-4 space-y-2.5">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold text-ink-900 min-w-0">{goal.title}</p>
                <span className={`badge ${PRIORITY_BADGE[goal.priority]} shrink-0`}>{goal.priority}</span>
              </div>
              <p className="text-xs text-ink-500">
                {goal.owner} · due {goal.due}
              </p>
              <div className="flex items-center gap-3">
                <div
                  className="flex-1 h-2 rounded-full bg-line-200 overflow-hidden"
                  role="progressbar"
                  aria-valuenow={goal.progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${goal.title} progress`}
                >
                  <div
                    className={`h-full rounded-full ${
                      goal.progress >= 50 ? 'bg-success' : goal.progress >= 25 ? 'bg-info' : 'bg-warning'
                    }`}
                    style={{ width: `${goal.progress}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-ink-600 tabular-nums shrink-0">{goal.progress}%</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
