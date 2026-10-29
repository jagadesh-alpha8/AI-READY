import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Compass,
  FastForward,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-react';
import type { GuideStep, GuideStepStatus } from '../../types/guide';

export interface OnboardingGuideCardProps {
  step: GuideStep | null;
  totalSteps: number;
  completedCount: number;
  skippedCount: number;
  isDismissed: boolean;
  loading?: boolean;
  onStartTour?: () => void;
  onSkip: (stepId: GuideStep['id']) => Promise<void>;
  onUnskip?: (stepId: GuideStep['id']) => Promise<void>;
  onDismiss: () => void;
  onOpenDrawer: () => void;
  onReset?: () => void;
}

export const STATUS_CONFIG: Record<
  GuideStepStatus,
  { label: string; badgeClass: string; icon: React.FC<{ className?: string }> }
> = {
  completed: {
    label: 'Completed',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800',
    icon: CheckCircle2,
  },
  in_progress: {
    label: 'In progress',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-400 dark:border-blue-800',
    icon: Clock,
  },
  needs_attention: {
    label: 'Needs attention',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800',
    icon: AlertTriangle,
  },
  skipped: {
    label: 'Skipped',
    badgeClass: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/40 dark:text-purple-400 dark:border-purple-800',
    icon: FastForward,
  },
  not_started: {
    label: 'Not started',
    badgeClass: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
    icon: Clock,
  },
};

export const OnboardingGuideCard: React.FC<OnboardingGuideCardProps> = ({
  step,
  totalSteps,
  completedCount,
  skippedCount,
  isDismissed,
  loading = false,
  onStartTour,
  onSkip,
  onUnskip,
  onDismiss,
  onOpenDrawer,
  onReset,
}) => {
  const navigate = useNavigate();

  if (isDismissed) {
    return null;
  }

  // Never show completion while loading or if data is missing
  if (loading) {
    return null;
  }

  // If no current active step, only show completed summary if actually completed or skipped
  if (!step) {
    const isFinished = totalSteps > 0 && completedCount + skippedCount >= totalSteps;
    if (!isFinished) {
      return null;
    }

    return (
      <div className="mb-6 rounded-xl border border-line-200 bg-card p-4 sm:p-5 shadow-sm transition-all">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 text-emerald-600 flex items-center justify-center shrink-0">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  Workflow Guide
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400">
                  {completedCount}/{totalSteps} Completed
                </span>
              </div>
              <h3 className="text-base font-bold text-ink-900 mt-0.5">
                {skippedCount > 0
                  ? `Workflow Walkthrough Finished (${skippedCount} step${skippedCount > 1 ? 's' : ''} skipped)`
                  : 'All 11 Platform Steps Completed!'}
              </h3>
              <p className="text-xs sm:text-sm text-ink-500 mt-1 max-w-2xl">
                {skippedCount > 0
                  ? 'You skipped some steps during this walkthrough. You can resume any skipped step at any time or review the full checklist.'
                  : 'Your AI Readiness Audit discovery cycle is fully set up. You can view the live CRI, review recommendations, or export reports.'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
            {onStartTour && (
              <button
                type="button"
                onClick={onStartTour}
                className="btn-secondary text-xs flex items-center gap-1.5"
                title="Start Product Tour"
              >
                <Sparkles className="w-3.5 h-3.5 text-brand-600" />
                Product Tour
              </button>
            )}
            {skippedCount > 0 && onReset && (
              <button
                type="button"
                onClick={onReset}
                className="btn-secondary text-xs flex items-center gap-1.5"
                title="Restart workflow guide"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Restart Guide
              </button>
            )}
            <button
              type="button"
              onClick={onOpenDrawer}
              className="btn-primary text-xs flex items-center gap-1.5"
            >
              View All Steps
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss guide"
              className="btn-icon text-ink-500 hover:text-ink-900"
              title="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[step.status] || STATUS_CONFIG.not_started;
  const StatusIcon = statusConfig.icon;
  const isSkipped = step.status === 'skipped';
  const isCompleted = step.status === 'completed';

  return (
    <div
      aria-label="Onboarding Workflow Guide"
      className="mb-6 rounded-xl border border-line-200 bg-card p-4 sm:p-5 shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-line-200">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-md bg-brand-500/10 text-brand-600 dark:text-brand-400 flex items-center justify-center shrink-0">
            <Compass className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-ink-500">
                Step {step.number} of {totalSteps}
              </span>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border ${statusConfig.badgeClass}`}
              >
                <StatusIcon className="w-3 h-3" />
                {statusConfig.label}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {onStartTour && (
            <button
              type="button"
              onClick={onStartTour}
              className="btn-secondary text-xs flex items-center gap-1.5 px-2.5 py-1 text-brand-700 dark:text-brand-300 border-brand-200 dark:border-brand-800"
              title="Start Product Tour"
            >
              <Sparkles className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
              <span>Product Tour</span>
            </button>
          )}
          <button
            type="button"
            onClick={onOpenDrawer}
            className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline px-2 py-1"
          >
            View all steps ({completedCount}/{totalSteps})
          </button>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss guide card"
            className="btn-icon text-ink-500 hover:text-ink-900"
            title="Dismiss guide card"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="mt-3.5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1 min-w-0 flex-1">
          <h3 className="text-sm sm:text-base font-bold text-ink-900 tracking-tight">
            {step.number}. {step.title}
          </h3>
          <p className="text-xs sm:text-sm text-ink-500 leading-relaxed max-w-3xl">
            {step.purpose}
          </p>

          {step.block_reason && (
            <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 text-xs border border-amber-200 dark:border-amber-800/60">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>{step.block_reason}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0 self-start md:self-center">
          {!isCompleted && (
            <>
              {isSkipped ? (
                onUnskip && (
                  <button
                    type="button"
                    onClick={() => onUnskip(step.id)}
                    className="btn-secondary text-xs px-3 py-1.5"
                  >
                    Resume this step
                  </button>
                )
              ) : (
                <button
                  type="button"
                  onClick={() => onSkip(step.id)}
                  className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1 text-ink-500 hover:text-ink-900"
                  title="Skip this step for now"
                >
                  <FastForward className="w-3.5 h-3.5" />
                  Skip this step
                </button>
              )}
            </>
          )}

          <button
            type="button"
            onClick={() => navigate(step.target_path)}
            className="btn-primary text-xs px-3.5 py-1.5 flex items-center gap-1.5"
          >
            <span>{step.action_label}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

