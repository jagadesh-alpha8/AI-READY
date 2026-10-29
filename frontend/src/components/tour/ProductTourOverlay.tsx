import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock,
  Compass,
  ExternalLink,
  FastForward,
  MapPin,
  X,
} from 'lucide-react';
import type { GuideStep, GuideStepId, GuideStepStatus, MenuTourStep } from '../../types/guide';

export interface ProductTourOverlayProps {
  active: boolean;
  step: GuideStep | MenuTourStep | null;
  stepIndex: number;
  totalSteps: number;
  onNext: () => void;
  onPrev: () => void;
  onSkip: (stepId: GuideStepId | string) => Promise<void> | void;
  onExit: () => void;
  onNavigate?: (path: string) => void;
  onFinish?: () => void;
  openSidebar?: () => void;
}

const TOUR_STATUS_CONFIG: Record<
  GuideStepStatus,
  { label: string; badgeClass: string; icon: React.FC<{ className?: string }> }
> = {
  completed: {
    label: 'Completed',
    badgeClass: 'bg-success-bg text-success border-success-line',
    icon: CheckCircle2,
  },
  in_progress: {
    label: 'In progress',
    badgeClass: 'bg-info-bg text-info border-info-line',
    icon: Clock,
  },
  needs_attention: {
    label: 'Needs attention',
    badgeClass: 'bg-warning-bg text-warning border-warning-line',
    icon: AlertTriangle,
  },
  skipped: {
    label: 'Skipped',
    badgeClass: 'bg-accent-bg text-accent border-accent-line',
    icon: FastForward,
  },
  not_started: {
    label: 'Not started',
    badgeClass: 'bg-line-100 text-ink-500 border-line-200',
    icon: Clock,
  },
};

interface TargetRect {
  top: number;
  left: number;
  width: number;
  height: number;
  bottom: number;
  right: number;
}

export const ProductTourOverlay: React.FC<ProductTourOverlayProps> = ({
  active,
  step,
  stepIndex,
  totalSteps,
  onNext,
  onPrev,
  onSkip,
  onExit,
  onNavigate,
  onFinish,
  openSidebar,
}) => {
  const [rect, setRect] = useState<TargetRect | null>(null);
  const [skipping, setSkipping] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [tooltipPos, setTooltipPos] = useState<{ top: number; left: number; placement: 'right' | 'bottom' | 'top' | 'center' }>({
    top: 0,
    left: 0,
    placement: 'bottom',
  });

  // 1. Target finding & rect calculation
  useEffect(() => {
    if (!active || !step) {
      setRect(null);
      return;
    }

    let isMounted = true;

    const findTarget = () => {
      if (!step.tour_target) return null;
      let el = document.querySelector(`[data-tour="${step.tour_target}"]`);

      // If not found and it's a sidebar target, try opening mobile sidebar
      if (!el && step.tour_target.startsWith('nav-') && openSidebar) {
        openSidebar();
        el = document.querySelector(`[data-tour="${step.tour_target}"]`);
      }
      return el as HTMLElement | null;
    };

    const updatePosition = () => {
      if (!isMounted) return;
      const el = findTarget();
      if (el) {
        const clientRect = el.getBoundingClientRect();
        // Check if element has non-zero geometry and is visible
        if (clientRect.width > 0 && clientRect.height > 0) {
          setRect({
            top: clientRect.top,
            left: clientRect.left,
            width: clientRect.width,
            height: clientRect.height,
            bottom: clientRect.bottom,
            right: clientRect.right,
          });
          return;
        }
      }
      setRect(null);
    };

    // Initial update
    updatePosition();

    // Scroll into view if needed
    const el = findTarget();
    if (el) {
      try {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } catch {
        // ignore in test environments
      }
    }

    const handleScrollOrResize = () => {
      requestAnimationFrame(updatePosition);
    };

    window.addEventListener('resize', handleScrollOrResize);
    window.addEventListener('scroll', handleScrollOrResize, { capture: true, passive: true });

    // Poll briefly in case sidebar or dynamic UI is animating
    const timer = setTimeout(updatePosition, 250);

    return () => {
      isMounted = false;
      clearTimeout(timer);
      window.removeEventListener('resize', handleScrollOrResize);
      window.removeEventListener('scroll', handleScrollOrResize, { capture: true });
    };
  }, [active, step, openSidebar]);

  // 2. Tooltip positioning relative to target or center fallback
  useLayoutEffect(() => {
    if (!active || !step) return;

    const tooltipEl = tooltipRef.current;
    const tooltipWidth = tooltipEl ? tooltipEl.offsetWidth : 380;
    const tooltipHeight = tooltipEl ? tooltipEl.offsetHeight : 240;
    const pad = 14;
    const margin = 16;
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
    const vh = typeof window !== 'undefined' ? window.innerHeight : 800;

    if (!rect) {
      // Fallback: center in viewport
      setTooltipPos({
        top: Math.max(margin, Math.round((vh - tooltipHeight) / 2)),
        left: Math.max(margin, Math.round((vw - tooltipWidth) / 2)),
        placement: 'center',
      });
      return;
    }

    // Try placing to the right (ideal for sidebar navigation items on desktop)
    const canFitRight = rect.right + pad + tooltipWidth + margin <= vw;
    const isSidebarTarget = rect.left < 320 && vw >= 768;

    if (isSidebarTarget && canFitRight) {
      const topPos = Math.max(margin, Math.min(rect.top - 8, vh - tooltipHeight - margin));
      setTooltipPos({
        top: topPos,
        left: rect.right + pad,
        placement: 'right',
      });
      return;
    }

    // Try placing below the target
    const canFitBelow = rect.bottom + pad + tooltipHeight + margin <= vh;
    if (canFitBelow) {
      const leftPos = Math.max(margin, Math.min(rect.left, vw - tooltipWidth - margin));
      setTooltipPos({
        top: rect.bottom + pad,
        left: leftPos,
        placement: 'bottom',
      });
      return;
    }

    // Try placing above the target
    const canFitAbove = rect.top - pad - tooltipHeight - margin >= 0;
    if (canFitAbove) {
      const leftPos = Math.max(margin, Math.min(rect.left, vw - tooltipWidth - margin));
      setTooltipPos({
        top: rect.top - pad - tooltipHeight,
        left: leftPos,
        placement: 'top',
      });
      return;
    }

    // Otherwise place where it fits best horizontally and vertically
    setTooltipPos({
      top: Math.max(margin, Math.min(rect.top, vh - tooltipHeight - margin)),
      left: Math.max(margin, Math.min(rect.right + pad, vw - tooltipWidth - margin)),
      placement: 'bottom',
    });
  }, [active, step, rect]);

  // 3. Keyboard navigation: Escape to exit, Arrows for prev/next
  useEffect(() => {
    if (!active) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onExit();
      } else if (e.key === 'ArrowRight' && !e.altKey && !e.ctrlKey && !e.metaKey) {
        const tag = (document.activeElement?.tagName || '').toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') {
          e.preventDefault();
          if (stepIndex === totalSteps - 1 && onFinish) {
            onFinish();
          } else {
            onNext();
          }
        }
      } else if (e.key === 'ArrowLeft' && !e.altKey && !e.ctrlKey && !e.metaKey) {
        const tag = (document.activeElement?.tagName || '').toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') {
          e.preventDefault();
          onPrev();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [active, onExit, onNext, onPrev, onFinish, stepIndex, totalSteps]);

  // Focus management
  useEffect(() => {
    if (active && tooltipRef.current) {
      tooltipRef.current.focus?.();
    }
  }, [active, stepIndex]);

  if (!active || !step) return null;

  const stepStatus = step.status || 'not_started';
  const statusConfig = TOUR_STATUS_CONFIG[stepStatus] || TOUR_STATUS_CONFIG.not_started;
  const StatusIcon = statusConfig.icon;
  const isFirstStep = stepIndex === 0;
  const isLastStep = stepIndex === totalSteps - 1;

  const handleSkipClick = async () => {
    if (skipping) return;
    setSkipping(true);
    try {
      await onSkip(step.id);
    } finally {
      setSkipping(false);
    }
  };

  const handleNextOrFinish = () => {
    if (isLastStep) {
      if (onFinish) {
        onFinish();
      } else {
        onNext();
      }
    } else {
      onNext();
    }
  };

  const handleActionClick = () => {
    if (step.target_path && onNavigate) {
      onNavigate(step.target_path);
    }
  };

  // Cutout dimensions with 6px padding
  const pad = 6;
  const cutoutX = rect ? Math.max(0, rect.left - pad) : 0;
  const cutoutY = rect ? Math.max(0, rect.top - pad) : 0;
  const cutoutW = rect ? rect.width + pad * 2 : 0;
  const cutoutH = rect ? rect.height + pad * 2 : 0;

  const displayStepNumber = stepIndex + 1;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Product Tour - Step ${displayStepNumber} of ${totalSteps}: ${step.title}`}
      tabIndex={-1}
      className="fixed inset-0 z-50 overflow-hidden font-sans select-none"
    >
      {/* 4 Backdrop Rectangles surrounding the cutout opening.
          This ensures the cutout region itself has NO DOM element over it,
          allowing users to click and interact with the highlighted control natively! */}
      {rect ? (
        <>
          {/* Top rect */}
          <div
            style={{ top: 0, left: 0, width: '100%', height: `${cutoutY}px` }}
            className="fixed bg-black/50 transition-opacity"
            onClick={onExit}
            aria-hidden="true"
          />
          {/* Bottom rect */}
          <div
            style={{ top: `${cutoutY + cutoutH}px`, left: 0, width: '100%', bottom: 0 }}
            className="fixed bg-black/50 transition-opacity"
            onClick={onExit}
            aria-hidden="true"
          />
          {/* Left rect */}
          <div
            style={{ top: `${cutoutY}px`, left: 0, width: `${cutoutX}px`, height: `${cutoutH}px` }}
            className="fixed bg-black/50 transition-opacity"
            onClick={onExit}
            aria-hidden="true"
          />
          {/* Right rect */}
          <div
            style={{ top: `${cutoutY}px`, left: `${cutoutX + cutoutW}px`, right: 0, height: `${cutoutH}px` }}
            className="fixed bg-black/50 transition-opacity"
            onClick={onExit}
            aria-hidden="true"
          />
          {/* Highlight ring around cutout opening */}
          <div
            style={{
              top: `${cutoutY}px`,
              left: `${cutoutX}px`,
              width: `${cutoutW}px`,
              height: `${cutoutH}px`,
            }}
            className="fixed rounded-lg border-2 border-brand-500 pointer-events-none animate-pulse shadow-[0_0_18px_rgba(141,182,0,0.42)]"
            aria-hidden="true"
          />
        </>
      ) : (
        /* Fallback: full-screen dimmed backdrop if target is not on view */
        <div
          className="fixed inset-0 bg-black/50 transition-opacity"
          onClick={onExit}
          aria-hidden="true"
        />
      )}

      {/* Interactive Tooltip Card */}
      <div
        ref={tooltipRef}
        tabIndex={0}
        style={{
          top: `${tooltipPos.top}px`,
          left: `${tooltipPos.left}px`,
        }}
        className="absolute z-50 w-full max-w-sm sm:max-w-md bg-card text-ink-700 rounded-xl shadow-popover border border-line-200 p-4 sm:p-5 transition-all duration-200 pointer-events-auto outline-none focus:ring-2 focus:ring-brand-500/50"
      >
        {/* Header: Progress, Badge, Exit */}
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-line-200">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-brand-500/10 text-brand-700 dark:text-brand-400 flex items-center justify-center shrink-0">
              <Compass className="w-3.5 h-3.5" />
            </div>
            <span className="text-xs font-bold uppercase tracking-wider text-brand-700 dark:text-brand-400">
              Step {displayStepNumber} of {totalSteps}
            </span>
            {step.status && (
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border ${statusConfig.badgeClass}`}
              >
                <StatusIcon className="w-2.5 h-2.5" />
                {statusConfig.label}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onExit}
            aria-label="Exit tour"
            title="Exit tour (Esc)"
            className="p-1 rounded text-ink-500 hover:text-ink-900 hover:bg-line-100 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Location Indicator */}
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px] font-medium text-ink-500">
          <MapPin className="w-3 h-3 shrink-0" />
          <span className="truncate">
            {step.tour_location || 'Platform Modules'}
          </span>
          {!rect && (
            <span className="ml-auto text-[10px] text-warning font-normal">
              (Item on another view or unavailable)
            </span>
          )}
        </div>

        {/* Step Title & Purpose */}
        <div className="mt-2 space-y-1">
          <h3 className="text-sm sm:text-base font-bold text-ink-900 tracking-tight">
            {step.title}
          </h3>
          <p className="text-xs text-ink-600 leading-relaxed">
            {step.purpose}
          </p>

          {/* Special notes for provisional approval or blockers */}
          {step.id === 'baseline_approval' && (
            <div className="mt-1.5 px-2 py-1 rounded bg-info-bg border border-info-line text-[11px] text-info">
              {step.details?.is_provisional
                ? 'Baseline is currently provisional. Formal baseline approval will freeze this score.'
                : 'Baseline score formalization and locking.'}
            </div>
          )}

          {step.block_reason && (
            <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-warning-bg text-warning text-xs border border-warning-line">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>{step.block_reason}</span>
            </div>
          )}
        </div>

        {/* Controls: Prev, Skip, Action, Next / Finish */}
        <div className="mt-3.5 pt-3 border-t border-line-200 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={isFirstStep}
              onClick={onPrev}
              className={`p-1.5 rounded text-xs flex items-center gap-1 transition-colors ${
                isFirstStep
                  ? 'text-ink-400 cursor-not-allowed'
                  : 'text-ink-600 hover:text-ink-900 hover:bg-line-100'
              }`}
              title="Previous tour step (Left arrow)"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Prev</span>
            </button>

            <button
              type="button"
              disabled={skipping}
              onClick={handleSkipClick}
              className="px-2.5 py-1 rounded text-xs text-brand-700 dark:text-brand-800 hover:text-brand-800 hover:bg-brand-500/10 border border-brand-500/40 flex items-center gap-1 transition-colors"
              title="Skip this tour step only (does not change business or sprint data)"
            >
              <FastForward className="w-3 h-3" />
              <span>Skip step</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            {step.action_label && step.target_path && onNavigate && (
              <button
                type="button"
                onClick={handleActionClick}
                className="btn-secondary px-2.5 py-1 rounded text-xs font-medium flex items-center gap-1 transition-colors"
                title={`Open ${step.action_label}`}
              >
                <span>{step.action_label}</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            )}

            <button
              type="button"
              onClick={handleNextOrFinish}
              className="btn-primary px-3 py-1 rounded text-xs font-semibold flex items-center gap-1 transition-colors"
              title={isLastStep ? 'Finish product tour' : 'Next tour step (Right arrow)'}
            >
              <span>{isLastStep ? 'Finish' : 'Next'}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Note on skipping: clearly state it does not mark the underlying business task as completed */}
        <p className="mt-2 text-[10px] text-ink-500 text-center">
          Skipping advances the tour only. It does not mark the task completed or alter sprint data.
        </p>
      </div>
    </div>
  );
};
