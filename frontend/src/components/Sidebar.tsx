import React, { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Gauge, Building2, ShieldCheck, Layers, Target, ListChecks, Bot, Bell,
  Network, ClipboardCheck, Settings, CalendarDays,
  FolderPlus, Upload, Activity, FileSearch, AlertCircle, CheckSquare,
  BarChart3, Lock, Sparkles, FileText,
  ChevronDown, ChevronRight, X,
} from 'lucide-react';

type LucideIcon = typeof Gauge;

/** Where a module sits in the build plan. Only `live` modules are navigable;
 * the rest are shown so the full platform shape stays visible, but they are
 * inert rather than dead links. */
type ModuleStatus = 'live' | 'next' | 'planned';

interface NavChild {
  to: string;
  label: string;
  icon: LucideIcon;
}

interface NavModule {
  key: string;
  label: string;
  icon: LucideIcon;
  status: ModuleStatus;
  /** Direct route — only for a live module with no children. */
  to?: string;
  exact?: boolean;
  /** Sub-steps. A module with children expands instead of navigating. */
  children?: NavChild[];
  /** Caption shown above the children when expanded. */
  childrenCaption?: string;
}

/**
 * The platform's module list, matching the approved product plan.
 *
 * Only Dashboard and AI Readiness Audit are built. AI Readiness Audit owns the
 * ten-step discovery sprint that used to be the whole sidebar. Evidence
 * Intelligence is the next module in the plan, so it is labelled distinctly
 * from the ones queued behind it.
 *
 * No notification badges are rendered here. The plan mock shows counts against
 * three modules, but nothing in this app produces them yet, and a hardcoded
 * number would read as real data — the same "never fabricate a value" stance
 * the extraction and scoring layers take.
 */
function buildModules(sprintId: string): NavModule[] {
  return [
    {
      key: 'dashboard',
      label: 'Dashboard',
      icon: Gauge,
      status: 'live',
      to: '/dashboard',
      exact: true,
    },
    {
      key: 'institution-dna',
      label: 'Institution DNA',
      icon: Building2,
      status: 'planned',
    },
    {
      key: 'ai-readiness-audit',
      label: 'AI Readiness Audit',
      icon: ShieldCheck,
      status: 'live',
      childrenCaption: 'Sprint steps · 24–48h',
      children: [
        { to: '/sprint/setup', label: '1. Sprint Setup', icon: FolderPlus },
        { to: `/sprint/${sprintId}/upload`, label: '2. Upload Data Pack', icon: Upload },
        { to: `/sprint/${sprintId}/monitor`, label: '3. AI Processing Monitor', icon: Activity },
        { to: `/sprint/${sprintId}/facts`, label: '4. Extracted Facts Review', icon: FileSearch },
        { to: `/sprint/${sprintId}/gaps`, label: '5. Gap Dashboard', icon: AlertCircle },
        { to: `/sprint/${sprintId}/confirmation`, label: '6. Owner Workspace', icon: CheckSquare },
        { to: `/sprint/${sprintId}/score`, label: '7. Live CRI Preview', icon: BarChart3 },
        { to: `/sprint/${sprintId}/approval`, label: '8. Baseline Approval', icon: Lock },
        { to: `/sprint/${sprintId}/recommendations`, label: '9. Recommendations', icon: Sparkles },
        { to: `/sprint/${sprintId}/report`, label: '10. Report & Export', icon: FileText },
      ],
    },
    { key: 'evidence-intelligence', label: 'Evidence Intelligence', icon: Layers, status: 'next' },
    { key: 'transformation-plan', label: 'Transformation Plan', icon: Target, status: 'planned' },
    { key: 'goals-tasks', label: 'Goals & Tasks', icon: ListChecks, status: 'planned' },
    { key: 'ai-copilot', label: 'AI Copilot', icon: Bot, status: 'planned' },
    { key: 'reminders', label: 'Reminders', icon: Bell, status: 'planned' },
    { key: 'compliance-mapping', label: 'Compliance Mapping', icon: Network, status: 'planned' },
    { key: 'uat-readiness', label: 'UAT Readiness', icon: ClipboardCheck, status: 'planned' },
    { key: 'admin-settings', label: 'Admin / Settings', icon: Settings, status: 'planned' },
    { key: 'build-timeline', label: 'Build Timeline', icon: CalendarDays, status: 'planned' },
  ];
}

const ROW_BASE =
  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors border-l-2 text-left';

export const Sidebar: React.FC<{
  activeSprintId?: string;
  open?: boolean;
  onClose?: () => void;
}> = ({ activeSprintId, open = false, onClose }) => {
  const sprintId = activeSprintId || 'demo-sprint-id';
  const modules = buildModules(sprintId);
  const { pathname } = useLocation();

  // The audit group opens itself whenever the current route is one of its
  // steps, so a deep link or a redirect never lands the user on a screen whose
  // menu entry is collapsed out of sight.
  const onAuditRoute = pathname.startsWith('/sprint');
  const [expanded, setExpanded] = useState<string | null>(
    onAuditRoute ? 'ai-readiness-audit' : null,
  );

  useEffect(() => {
    if (onAuditRoute) {
      setExpanded('ai-readiness-audit');
    }
  }, [onAuditRoute]);

  return (
    <>
      {/* Scrim: mobile/tablet only, while the drawer is open */}
      {open && (
        <div
          className="fixed inset-0 bg-ink-900/40 z-40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`bg-card border-r border-line-200 p-4 flex flex-col justify-between
          fixed inset-y-0 left-0 z-50 w-72 transition-transform duration-200 ease-out overflow-y-auto
          ${open ? 'translate-x-0' : '-translate-x-full'}
          lg:translate-x-0 lg:static lg:z-0 lg:w-64 lg:shrink-0 lg:min-h-[calc(100vh-57px)]`}
      >
        <div className="space-y-6">
          <div className="flex items-center justify-between lg:hidden mb-2">
            <span className="text-sm font-bold text-ink-900">Navigation</span>
            <button type="button" onClick={onClose} className="btn-icon" aria-label="Close navigation menu">
              <X className="w-5 h-5" />
            </button>
          </div>

          <div>
            <h2 className="text-[11px] font-bold text-ink-500 uppercase tracking-wide px-3 mb-3">
              Platform Modules
            </h2>

            <nav className="space-y-1">
              {modules.map((module) => {
                const Icon = module.icon;

                // --- Not built yet: visible, labelled, and deliberately inert.
                if (module.status !== 'live') {
                  return (
                    <div
                      key={module.key}
                      aria-disabled="true"
                      title={
                        module.status === 'next'
                          ? 'Next module in the build plan'
                          : 'Planned — not built yet'
                      }
                      className={`${ROW_BASE} border-transparent text-ink-500/60 cursor-not-allowed select-none`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="truncate">{module.label}</span>
                      {/* Only the next module up is marked, and with a dot
                          rather than a word: badging all ten planned modules
                          added no information, and a text badge cost enough
                          width to truncate the longest labels. */}
                      {module.status === 'next' && (
                        <>
                          <span
                            className="ml-auto shrink-0 w-2 h-2 rounded-full bg-accent"
                            aria-hidden="true"
                          />
                          <span className="sr-only">Next module in the build plan</span>
                        </>
                      )}
                    </div>
                  );
                }

                // --- Live leaf module (Dashboard).
                if (!module.children) {
                  return (
                    <NavLink
                      key={module.key}
                      to={module.to!}
                      end={module.exact}
                      onClick={onClose}
                      className={({ isActive }) =>
                        `${ROW_BASE} ${
                          isActive
                            ? 'bg-brand-50 text-brand-800 border-brand-500 font-semibold'
                            : 'text-ink-600 border-transparent hover:text-ink-900 hover:bg-surface'
                        }`
                      }
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="truncate">{module.label}</span>
                    </NavLink>
                  );
                }

                // --- Live module with sub-steps (AI Readiness Audit).
                const isOpen = expanded === module.key;
                return (
                  <div key={module.key}>
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : module.key)}
                      aria-expanded={isOpen}
                      className={`${ROW_BASE} ${
                        onAuditRoute
                          ? 'bg-brand-50 text-brand-800 border-brand-500 font-semibold'
                          : 'text-ink-600 border-transparent hover:text-ink-900 hover:bg-surface'
                      }`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="truncate">{module.label}</span>
                      {isOpen ? (
                        <ChevronDown className="w-4 h-4 shrink-0 ml-auto" />
                      ) : (
                        <ChevronRight className="w-4 h-4 shrink-0 ml-auto" />
                      )}
                    </button>

                    {isOpen && (
                      <div className="mt-1 ml-4 pl-3 border-l border-line-200 space-y-0.5">
                        {module.childrenCaption && (
                          <p className="text-[10px] font-bold text-ink-500 uppercase tracking-wide px-2 pt-1 pb-1.5">
                            {module.childrenCaption}
                          </p>
                        )}
                        {module.children.map((child) => {
                          const ChildIcon = child.icon;
                          return (
                            <NavLink
                              key={child.to}
                              to={child.to}
                              onClick={onClose}
                              className={({ isActive }) =>
                                `flex items-center gap-2.5 px-2 py-2 rounded-lg text-[13px] font-medium transition-colors ${
                                  isActive
                                    ? 'bg-brand-50 text-brand-800 font-semibold'
                                    : 'text-ink-600 hover:text-ink-900 hover:bg-surface'
                                }`
                              }
                            >
                              <ChildIcon className="w-3.5 h-3.5 shrink-0" />
                              <span className="truncate">{child.label}</span>
                            </NavLink>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </nav>
          </div>
        </div>

        <div className="p-3 bg-surface rounded-xl border border-line-200 text-xs">
          <p className="font-semibold text-ink-900">Target Completion</p>
          <p className="text-ink-500 mt-0.5">24-48 Hours Fast-Track Discovery</p>
          <div className="w-full bg-line-200 h-1.5 rounded-full mt-2 overflow-hidden">
            <div className="bg-brand-500 h-full w-2/3 rounded-full"></div>
          </div>
        </div>
      </aside>
    </>
  );
};
