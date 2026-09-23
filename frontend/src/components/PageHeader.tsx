import React from 'react';
import type { LucideIcon } from 'lucide-react';

/** The header every module page opens with: icon tile, title, one line of
 * context, and optional actions on the right. Shared so the ported modules
 * sit visually alongside the ones built here rather than looking imported. */
export const PageHeader: React.FC<{
  icon: LucideIcon;
  title: string;
  description: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
}> = ({ icon: Icon, title, description, badge, actions }) => (
  <div className="flex flex-col sm:flex-row sm:items-center gap-3">
    <div className="flex items-start gap-3 min-w-0 flex-1">
      <div className="p-2.5 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-800 shrink-0">
        <Icon className="w-6 h-6" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-xl sm:text-2xl font-bold text-ink-900">{title}</h1>
          {badge}
        </div>
        <p className="text-sm text-ink-500 mt-0.5">{description}</p>
      </div>
    </div>
    {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
  </div>
);

/** Horizontal tab strip used by the two multi-view benchmark pages. */
export const TabStrip = <T extends string>({
  tabs, active, onChange,
}: {
  tabs: { id: T; label: string; icon?: LucideIcon; count?: number }[];
  active: T;
  onChange: (id: T) => void;
}) => (
  <div className="flex gap-2 overflow-x-auto pb-1">
    {tabs.map((tab) => {
      const Icon = tab.icon;
      const isActive = active === tab.id;
      return (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          aria-current={isActive ? 'page' : undefined}
          className={`${isActive ? 'btn-primary' : 'btn-secondary'} btn-sm shrink-0`}
        >
          {Icon && <Icon className="w-3.5 h-3.5" />}
          <span>{tab.label}</span>
          {tab.count !== undefined && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums ${
                isActive ? 'bg-black/15' : 'bg-line-300 text-ink-700'
              }`}
            >
              {tab.count}
            </span>
          )}
        </button>
      );
    })}
  </div>
);

/** Filter pills — the "All / verified / missing (n)" row several ported
 * screens use. */
export const FilterPills = <T extends string>({
  options, active, onChange,
}: {
  options: { id: T; label: string; count?: number }[];
  active: T;
  onChange: (id: T) => void;
}) => (
  <div className="flex flex-wrap gap-2">
    {options.map((option) => {
      const isActive = active === option.id;
      return (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          aria-pressed={isActive}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
            isActive
              ? 'bg-brand-500/15 text-brand-800 border-brand-500/40'
              : 'bg-card text-ink-600 border-line-200 hover:bg-surface'
          }`}
        >
          {option.label}
          {option.count !== undefined && <span className="ml-1.5 tabular-nums opacity-70">{option.count}</span>}
        </button>
      );
    })}
  </div>
);
