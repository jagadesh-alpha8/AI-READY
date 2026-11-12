import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Compass,
  FastForward,
  RotateCcw,
  Sparkles,
  Undo2,
  X,
} from 'lucide-react';
import type { GuideStep } from '../../types/guide';
import { STATUS_CONFIG } from './OnboardingGuideCard';

export interface OnboardingGuideDrawerProps {
  open: boolean;
  onClose: () => void;
  steps: GuideStep[];
  currentStepId: string | null;
  completedCount: number;
  skippedCount: number;
  totalSteps: number;
  onStartTour?: (stepIndex?: number) => void;
  onSkip: (stepId: GuideStep['id']) => Promise<void>;
  onUnskip: (stepId: GuideStep['id']) => Promise<void>;
  onReset: () => Promise<void>;
  onSelectStep?: (stepId: GuideStep['id']) => void;
}

export const OnboardingGuideDrawer: React.FC<OnboardingGuideDrawerProps> = ({
  open,
  onClose,
  steps,
  currentStepId,
  completedCount,
  skippedCount,
  totalSteps,
  onStartTour,
  onSkip,
  onUnskip,
  onReset,
  onSelectStep,
}) => {
  const navigate = useNavigate();

  // Handle escape key
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const percentComplete = Math.round((completedCount / (totalSteps || 1)) * 100);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="guide-drawer-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs transition-opacity"
    >
      <div
        className="w-full max-w-2xl bg-card border-l border-line-200 shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-200"
      >
        {/* Header */}
        <div className="p-4 sm:p-6 border-b border-line-200 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-brand-500/10 text-brand-600 dark:text-brand-400 flex items-center justify-center shrink-0">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <h2 id="guide-drawer-title" className="text-base sm:text-lg font-bold text-ink-900 leading-tight">
                AI Readiness Platform Guide
              </h2>
              <p className="text-xs text-ink-500 mt-0.5">
                Assessment workflow from setup to report export
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close guide"
            className="btn-icon text-ink-500 hover:text-ink-900 -mr-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress Bar & Summary */}
        <div className="px-4 sm:px-6 py-3.5 bg-surface border-b border-line-200">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="font-semibold text-ink-900">
              {completedCount} of {totalSteps} Steps Completed ({percentComplete}%)
            </span>
            {skippedCount > 0 && (
              <span className="text-purple-600 dark:text-purple-400 font-medium">
                {skippedCount} Skipped
              </span>
            )}
          </div>
          <div className="w-full h-2 rounded-full bg-line-200 overflow-hidden flex">
            <div
              className="bg-emerald-500 transition-all duration-300"
              style={{ width: `${percentComplete}%` }}
            />
            {skippedCount > 0 && (
              <div
                className="bg-purple-400 transition-all duration-300"
                style={{ width: `${Math.round((skippedCount / (totalSteps || 1)) * 100)}%` }}
              />
            )}
          </div>
          <p className="text-[11px] text-ink-500 mt-2">
            Progress is derived exclusively from verified platform records and audit completion.
            Viewing or skipping product tours does not alter this progress.
          </p>
        </div>

        {/* Steps List */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3">
          {steps.map((st) => {
            const isCurrent = st.id === currentStepId;
            const isCompleted = st.status === 'completed';
            const isSkipped = st.status === 'skipped';
            const statusConfig = STATUS_CONFIG[st.status] || STATUS_CONFIG.not_started;
            const StatusIcon = statusConfig.icon;

            return (
              <div
                key={st.id}
                className={`rounded-lg border p-3.5 sm:p-4 transition-all ${
                  isCurrent
                    ? 'border-brand-500 bg-brand-50/20 dark:bg-brand-950/20 shadow-xs'
                    : 'border-line-200 bg-card hover:border-line-300'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 mt-0.5 ${
                        isCompleted
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                          : isCurrent
                          ? 'bg-brand-500 text-white'
                          : 'bg-surface text-ink-500 border border-line-200'
                      }`}
                    >
                      {st.number}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-bold text-ink-900 leading-snug">
                          {st.title}
                        </h4>
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border ${statusConfig.badgeClass}`}
                        >
                          <StatusIcon className="w-2.5 h-2.5" />
                          {statusConfig.label}
                        </span>
                        {isCurrent && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-brand-500 text-white">
                            Current
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-ink-500 mt-1 leading-relaxed">
                        {st.purpose}
                      </p>

                      {st.block_reason && (
                        <div className="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 text-xs border border-amber-200 dark:border-amber-800/60">
                          <AlertTriangle className="w-3 h-3 shrink-0" />
                          <span>{st.block_reason}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row items-end sm:items-center gap-1.5 shrink-0 self-start sm:self-center">
                    {!isCompleted && (
                      <>
                        {isSkipped ? (
                          <button
                            type="button"
                            onClick={() => onUnskip(st.id)}
                            className="btn-secondary text-[11px] px-2.5 py-1 flex items-center gap-1"
                            title="Resume this skipped step"
                          >
                            <Undo2 className="w-3 h-3" />
                            Resume
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => onSkip(st.id)}
                            className="btn-secondary text-[11px] px-2.5 py-1 text-ink-500 hover:text-ink-900 flex items-center gap-1"
                            title="Skip this step"
                          >
                            <FastForward className="w-3 h-3" />
                            Skip
                          </button>
                        )}
                      </>
                    )}

                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        if (onSelectStep) onSelectStep(st.id);
                        navigate(st.target_path);
                      }}
                      className="btn-primary text-[11px] px-3 py-1 flex items-center gap-1"
                    >
                      <span>{st.action_label}</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="p-4 sm:p-5 border-t border-line-200 bg-surface flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onReset}
              className="btn-secondary text-xs flex items-center gap-1.5"
              title="Reset skips and dismissed state"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Restart Guide
            </button>
            {onStartTour && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onStartTour();
                }}
                className="btn-secondary text-xs flex items-center gap-1.5 text-brand-700 dark:text-brand-300 border-brand-200 dark:border-brand-800"
                title="Start Product Tour"
              >
                <Sparkles className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
                Product Tour
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="btn-primary text-xs px-4"
          >
            Close Guide
          </button>
        </div>
      </div>
    </div>
  );
};

