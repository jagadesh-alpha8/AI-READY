import React, { useState } from 'react';
import { AlertTriangle, Bell, Clock, Eye, FileText, TrendingUp } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import { REMINDERS } from '../../data/workspaceDemo';
import type { ReminderType } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's Reminders page: what is waiting on
 * someone, so a sprint does not stall silently. */

type Filter = 'all' | 'critical' | 'high' | 'medium';

const TYPE_ICON: Record<ReminderType, typeof Clock> = {
  deadline: Clock,
  overdue: AlertTriangle,
  document: FileText,
  progress: TrendingUp,
  review: Eye,
};

export const Reminders: React.FC = () => {
  const [filter, setFilter] = useState<Filter>('all');

  const visible = filter === 'all' ? REMINDERS : REMINDERS.filter((r) => r.priority === filter);

  const options = (['all', 'critical', 'high', 'medium'] as Filter[]).map((id) => ({
    id,
    label: id === 'all' ? 'All' : id[0].toUpperCase() + id.slice(1),
    count: id === 'all' ? REMINDERS.length : REMINDERS.filter((r) => r.priority === id).length,
  }));

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="Nothing sends: there is no scheduled job and no email provider configured." />

      <PageHeader
        icon={Bell}
        title="Reminders"
        description="Items waiting on someone — overdue evidence, approaching deadlines, and stalled work."
      />

      <FilterPills options={options} active={filter} onChange={setFilter} />

      <div className="space-y-2">
        {visible.map((reminder) => {
          const Icon = TYPE_ICON[reminder.type];
          const isCritical = reminder.priority === 'critical';
          return (
            <div
              key={reminder.id}
              className={`glass-card p-4 flex items-start gap-3 ${
                isCritical ? 'border-danger-line bg-danger-bg/30' : ''
              }`}
            >
              <div
                className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                  isCritical
                    ? 'bg-danger-bg text-danger'
                    : reminder.priority === 'high'
                      ? 'bg-warning-bg text-warning'
                      : 'bg-info-bg text-info'
                }`}
              >
                <Icon className="w-4 h-4" />
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-900">{reminder.title}</p>
                <p className="text-xs text-ink-600 mt-0.5">{reminder.message}</p>
                <p className="text-xs text-ink-500 mt-1">Due {reminder.due}</p>
              </div>

              <div className="flex gap-1.5 shrink-0">
                <button type="button" className="btn-secondary btn-sm" disabled title="Not wired up in this demo">
                  Done
                </button>
                <button type="button" className="btn-ghost btn-sm" disabled title="Not wired up in this demo">
                  Snooze
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
