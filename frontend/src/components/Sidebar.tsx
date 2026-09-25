import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Gauge, Building2, ShieldCheck, Layers, Target, ListChecks, Bot, Bell,
  Network, ClipboardCheck, Settings, Award, BookOpen,
  FolderPlus, Upload, Activity, FileSearch, AlertCircle, CheckSquare,
  BarChart3, Lock, Sparkles, FileText, X,
} from 'lucide-react';

type LucideIcon = typeof Gauge;

/** Where a module sits in the build plan.
 *
 * - `live`   — built here, backed by the API, real data.
 * - `admin`  — an internal InGage workspace, not a client module. Badged as
 *              such because WHO it is for is the load-bearing fact; that its
 *              library is still sample data is stated on the page itself.
 * - `demo`   — UI ported from the InGage prototype, rendering sample data
 *              held in the browser. Navigable, but NOT backed by anything;
 *              every such page opens with a banner saying so.
 * - `next` / `planned` — not built at all; the link opens a design preview.
 *
 * The distinction between `live` and `demo` is the important one: both are
 * clickable and look finished, and only the label stops someone reading a
 * seeded number as an institution's real record. */
type ModuleStatus = 'live' | 'demo' | 'admin' | 'next' | 'planned';

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
  /** Who a module is for, when it is not everyone. Rendered as a small label
   * so an internal-only screen is identifiable from the menu. */
  audience?: string;
  /** Sub-steps, always rendered beneath the module — nothing here collapses. */
  children?: NavChild[];
  /** Caption shown above the children when expanded. */
  childrenCaption?: string;
}

interface NavGroup {
  heading: string;
  modules: NavModule[];
}

/**
 * The platform's module list, matching the approved product plan.
 *
 * Dashboard, Institution DNA and AI Readiness Audit are built. AI Readiness
 * Audit owns the ten-step discovery sprint that used to be the whole sidebar.
 * Evidence Intelligence is the next module in the plan, so it is labelled
 * distinctly from the ones queued behind it.
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
      status: 'live',
      to: '/institution-dna',
    },
    {
      key: 'ai-readiness-audit',
      label: 'AI Readiness Audit',
      icon: ShieldCheck,
      status: 'live',
      childrenCaption: 'Sprint steps',
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
    { key: 'evidence-intelligence', label: 'Evidence Intelligence', icon: Layers, status: 'live', to: '/evidence' },
    {
      key: 'cri-benchmark-intelligence',
      label: 'CRI & Benchmark Intelligence',
      icon: Award,
      status: 'live',
      to: '/cri-benchmark',
    },
    {
      key: 'benchmark-studio',
      label: 'Benchmark Studio',
      icon: BookOpen,
      status: 'admin',
      to: '/benchmark-studio',
    },
    { key: 'transformation-plan', label: 'Transformation Plan', icon: Target, status: 'live', to: '/transformation-plan' },
    { key: 'goals-tasks', label: 'Goals & Tasks', icon: ListChecks, status: 'demo', to: '/goals-tasks' },
    { key: 'ai-chatbot', label: 'AI Copilot', icon: Bot, status: 'demo', to: '/ai-chatbot' },
    { key: 'reminders', label: 'Reminders', icon: Bell, status: 'demo', to: '/reminders' },
    { key: 'compliance-mapping', label: 'Compliance Mapping', icon: Network, status: 'demo', to: '/compliance' },
    { key: 'uat-readiness', label: 'UAT Readiness', icon: ClipboardCheck, status: 'demo', to: '/uat-readiness' },
    // No prototype screen exists for this one, so it keeps its design preview.
    { key: 'admin-settings', label: 'Admin / Settings', icon: Settings, status: 'planned' },
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
  // One group. The Project Status Dashboard is deliberately NOT here: it
  // reports on how much of the product plan exists, which makes it a report
  // about the app rather than a part of it. It lives on its own route
  // (/status-dashboard), reached by URL rather than by this menu.
  const groups: NavGroup[] = [
    { heading: 'Platform Modules', modules: buildModules(sprintId) },
  ];
  const { pathname } = useLocation();

  // Only used to highlight the parent module while one of its steps is open.
  // Nothing collapses: every menu entry stays visible at all times.
  const onAuditRoute = pathname.startsWith('/sprint');

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
        className={`bg-card border-r border-line-200 p-4 flex flex-col
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

          {groups.map((group) => (
          <div key={group.heading}>
            <h2 className="text-[11px] font-bold text-ink-500 uppercase tracking-wide px-3 mb-3">
              {group.heading}
            </h2>

            <nav className="space-y-1">
              {group.modules.map((module) => {
                const Icon = module.icon;

                // --- Ported prototype screen running on sample data. Reads as
                // a real module because it is one — but the data behind it is
                // not, so the row is marked and the page opens with a banner.
                if (module.status === 'demo' || module.status === 'admin') {
                  const isAdmin = module.status === 'admin';
                  return (
                    <NavLink
                      key={module.key}
                      to={module.to!}
                      onClick={onClose}
                      title={
                        isAdmin
                          ? 'InGage internal administration — not a client module'
                          : 'Ported from the InGage prototype — renders sample data, not a real record'
                      }
                      className={({ isActive }) =>
                        `${ROW_BASE} ${
                          isActive
                            ? 'bg-brand-50 text-brand-800 border-brand-500 font-semibold'
                            : 'text-ink-600 border-transparent hover:text-ink-900 hover:bg-surface'
                        }`
                      }
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="min-w-0 leading-snug">
                        {module.label}
                        {module.audience && (
                          <span className="block text-[10px] font-semibold uppercase tracking-wide text-ink-500/70 mt-0.5">
                            {module.audience}
                          </span>
                        )}
                      </span>
                      <span
                        className={`ml-auto shrink-0 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border ${
                          isAdmin
                            ? 'bg-danger-bg text-danger border-danger-line'
                            : 'bg-info-bg text-info border-info-line'
                        }`}
                      >
                        {isAdmin ? 'Admin' : 'Demo'}
                      </span>
                      <span className="sr-only">
                        {isAdmin
                          ? 'InGage internal administration. Not for client users.'
                          : 'Sample data, not connected to a real institution.'}
                      </span>
                    </NavLink>
                  );
                }

                // --- Not built: shown so the full platform shape stays
                // visible, but inert. No route, no hover affordance, and
                // `aria-disabled` so a screen reader announces it as
                // unavailable rather than reading it as a link that is simply
                // hard to activate.
                if (module.status !== 'live') {
                  return (
                    <div
                      key={module.key}
                      aria-disabled="true"
                      title="Not built yet"
                      className={`${ROW_BASE} border-transparent text-ink-500/50 cursor-not-allowed select-none`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      {/* Wraps rather than truncates: the longest labels do
                          not fit one line at this width, and a half-shown
                          label is worse than a two-line one. */}
                      <span className="min-w-0 leading-snug">
                        {module.label}
                        {module.audience && (
                          <span className="block text-[10px] font-semibold uppercase tracking-wide text-ink-500/60 mt-0.5">
                            {module.audience}
                          </span>
                        )}
                      </span>
                      <span className="sr-only">Not built yet. Unavailable.</span>
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
                // The module row is a heading, not a control: it owns no route
                // of its own, and its steps are always listed below it.
                return (
                  <div key={module.key}>
                    <div
                      className={`${ROW_BASE} select-none ${
                        onAuditRoute
                          ? 'bg-brand-50 text-brand-800 border-brand-500 font-semibold'
                          : 'text-ink-900 border-transparent font-semibold'
                      }`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="truncate">{module.label}</span>
                    </div>

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
                  </div>
                );
              })}
            </nav>

          </div>
          ))}
        </div>
      </aside>
    </>
  );
};
