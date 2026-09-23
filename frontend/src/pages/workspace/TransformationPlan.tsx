import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Target } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { PageHeader } from '../../components/PageHeader';
import { PLAN_PHASES, PLAN_TARGET } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's Transformation Plan page: the audit's
 * findings sequenced into dated phases, each phase holding the initiatives
 * that close it, with an accountable owner and a success metric. */

const PRIORITY_BADGE = {
  critical: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
} as const;

const PRIORITY_DOT = {
  critical: 'bg-danger-solid',
  high: 'bg-warning',
  medium: 'bg-info',
} as const;

export const TransformationPlan: React.FC = () => {
  // The in-progress phase opens by default — it is the one being worked.
  const [expanded, setExpanded] = useState<string | null>(
    PLAN_PHASES.find((p) => p.status === 'in_progress')?.name ?? null,
  );

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="The plan is sample content; nothing here is generated from your sprint data yet." />

      <PageHeader
        icon={Target}
        title="Transformation Plan"
        description="The audit's findings, sequenced into dated phases with an owner and a success metric for each initiative."
      />

      <div className="glass-card p-6 bg-gradient-to-br from-brand-50 to-card">
        <h2 className="text-lg font-bold text-ink-900">{PLAN_TARGET.headline}</h2>
        <p className="text-sm text-ink-600 mt-1">{PLAN_TARGET.target}</p>
        <p className="text-xs text-ink-500 mt-1">{PLAN_TARGET.derivedFrom}</p>
      </div>

      <div className="space-y-3">
        {PLAN_PHASES.map((phase, index) => {
          const isOpen = expanded === phase.name;
          return (
            <div key={phase.name} className="glass-card overflow-hidden">
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : phase.name)}
                aria-expanded={isOpen}
                className="w-full flex items-center gap-4 p-4 text-left hover:bg-surface transition-colors"
              >
                <span
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
                    phase.status === 'in_progress'
                      ? 'bg-brand-500 text-on-brand'
                      : 'bg-line-200 text-ink-600'
                  }`}
                >
                  {index + 1}
                </span>

                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-bold text-ink-900">{phase.name}</span>
                  <span className="block text-xs text-ink-500">
                    {phase.period} · {phase.initiatives.length} initiatives
                  </span>
                </span>

                <span className={`badge ${phase.status === 'in_progress' ? 'badge-info' : 'badge-neutral'} shrink-0`}>
                  {phase.status === 'in_progress' ? 'In progress' : 'Not started'}
                </span>

                {isOpen
                  ? <ChevronUp className="w-4 h-4 text-ink-500 shrink-0" />
                  : <ChevronDown className="w-4 h-4 text-ink-500 shrink-0" />}
              </button>

              {isOpen && (
                <div className="border-t border-line-200 p-4 space-y-2">
                  {phase.initiatives.map((initiative) => (
                    <div
                      key={initiative.title}
                      className="flex items-center gap-3 p-3 rounded-lg bg-surface border border-line-200"
                    >
                      <span
                        className={`w-2 h-2 rounded-full shrink-0 ${PRIORITY_DOT[initiative.priority]}`}
                        aria-hidden="true"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-ink-900">{initiative.title}</p>
                        <p className="text-xs text-ink-500">
                          {initiative.owner} · {initiative.metric}
                        </p>
                      </div>
                      <span className={`badge ${PRIORITY_BADGE[initiative.priority]} shrink-0`}>
                        {initiative.priority}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
