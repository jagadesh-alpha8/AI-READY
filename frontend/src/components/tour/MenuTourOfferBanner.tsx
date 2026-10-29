import React, { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { useMenuTour } from '../../context/MenuTourContext';
import { MENU_TOURS } from './menuTours';
import type { MenuKey } from '../../utils/access';

export const MenuTourOfferBanner: React.FC = () => {
  const { currentMenuKey, isOfferVisible, startTour, tourActive } = useMenuTour();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const prevMenuKeyRef = useRef<MenuKey | null>(null);

  // When user navigates to another menu/page, show that page's expanded invitation automatically.
  // Re-rendering the same page does not reopen the banner repeatedly.
  useEffect(() => {
    if (!currentMenuKey) {
      prevMenuKeyRef.current = null;
      return;
    }

    if (currentMenuKey !== prevMenuKeyRef.current) {
      prevMenuKeyRef.current = currentMenuKey;
      setIsCollapsed(false);
    }
  }, [currentMenuKey]);

  if (!currentMenuKey || !isOfferVisible(currentMenuKey) || tourActive) {
    return null;
  }

  const tourConfig = MENU_TOURS[currentMenuKey];
  if (!tourConfig) return null;

  // When collapsed: show small persistent tour icon/pill
  if (isCollapsed) {
    return (
      <div className="mb-3 flex items-center">
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          data-tour="tour-invitation-collapsed"
          className="group inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-brand-500/30 bg-card hover:bg-brand-50/50 dark:hover:bg-brand-950/40 text-brand-700 dark:text-brand-300 text-xs font-medium shadow-xs transition-all cursor-pointer"
          title={`Reopen tour invitation for ${tourConfig.menuTitle}`}
          aria-label={`Reopen tour invitation for ${tourConfig.menuTitle}`}
        >
          <div className="w-5 h-5 rounded-full bg-brand-500/15 flex items-center justify-center shrink-0">
            <Sparkles className="w-3 h-3 text-brand-600 dark:text-brand-400 group-hover:scale-110 transition-transform" />
          </div>
          <span className="font-semibold text-xs text-ink-900">Take Tour</span>
          <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-surface border border-line-200 text-ink-500">
            {tourConfig.steps.length} steps
          </span>
        </button>
      </div>
    );
  }

  // Expanded state: full invitation banner
  return (
    <div
      key={currentMenuKey}
      role="region"
      aria-label={`Tour invitation for ${tourConfig.menuTitle}`}
      className="glass-card p-3 sm:p-4 mb-4 border-l-4 border-l-brand-500 bg-gradient-to-r from-brand-50/50 via-card to-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs rounded-xl transition-all tour-ring-run"
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-9 h-9 rounded-xl bg-brand-500/15 border border-brand-500/30 text-brand-700 dark:text-brand-300 flex items-center justify-center shrink-0">
          <Sparkles className="w-4 h-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <h2 className="text-sm font-bold text-ink-900 tracking-tight">
              Welcome to {tourConfig.menuTitle}
            </h2>
            <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-surface border border-line-200 text-ink-500">
              {tourConfig.steps.length} steps
            </span>
          </div>
          <p className="text-xs text-ink-600 truncate mt-0.5 max-w-2xl">
            {tourConfig.menuPurpose} Take a quick tour to explore key controls on this page.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
        <button
          type="button"
          onClick={() => startTour(currentMenuKey)}
          className="btn-primary text-xs py-1.5 px-3.5 rounded-full flex items-center gap-1.5 font-semibold shadow-xs"
          title={`Take a tour of ${tourConfig.menuTitle} controls`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Take Tour</span>
        </button>

        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          className="text-xs font-medium text-ink-500 hover:text-ink-900 px-2 py-1.5 transition-colors cursor-pointer"
          title="Collapse invitation for this page"
          aria-label="Collapse tour invitation"
        >
          <span>Not now</span>
        </button>
      </div>
    </div>
  );
};

/**
 * Contextual replay button inside the page for users to trigger the tour on demand.
 */
export const TakeTourButton: React.FC<{
  className?: string;
  variant?: 'primary' | 'secondary' | 'ghost';
  label?: string;
}> = ({ className = '', variant = 'secondary', label = 'Take Tour' }) => {
  const { currentMenuKey, startTour, isTourAvailable } = useMenuTour();

  if (!currentMenuKey || !isTourAvailable(currentMenuKey)) {
    return null;
  }

  const baseCls =
    variant === 'primary' ? 'btn-primary' : variant === 'ghost' ? 'btn-ghost' : 'btn-secondary';

  return (
    <button
      type="button"
      onClick={() => startTour(currentMenuKey)}
      className={`${baseCls} text-xs py-1.5 px-2.5 flex items-center gap-1.5 ${className}`}
      title="Take a tour of this page's controls"
      aria-label="Take a tour of this page's controls"
    >
      <Sparkles className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
      <span className="font-semibold">{label}</span>
    </button>
  );
};

