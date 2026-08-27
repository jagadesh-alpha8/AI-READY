import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, FolderPlus, Upload, Activity,
  FileSearch, AlertCircle, CheckSquare, BarChart3,
  Sparkles, FileText, Lock, X,
} from 'lucide-react';

export const Sidebar: React.FC<{
  activeSprintId?: string;
  open?: boolean;
  onClose?: () => void;
}> = ({ activeSprintId, open = false, onClose }) => {
  const sprintId = activeSprintId || 'demo-sprint-id';

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, exact: true },
    { to: `/sprint/setup`, label: '1. Sprint Setup', icon: FolderPlus },
    { to: `/sprint/${sprintId}/upload`, label: '2. Upload Data Pack', icon: Upload },
    { to: `/sprint/${sprintId}/monitor`, label: '3. AI Processing Monitor', icon: Activity },
    { to: `/sprint/${sprintId}/facts`, label: '4. Extracted Facts Review', icon: FileSearch },
    { to: `/sprint/${sprintId}/gaps`, label: '5. Gap Dashboard', icon: AlertCircle },
    { to: `/sprint/${sprintId}/confirmation`, label: '6. Owner Workspace', icon: CheckSquare },
    { to: `/sprint/${sprintId}/score`, label: '7. Live CRI Preview', icon: BarChart3 },
    { to: `/sprint/${sprintId}/approval`, label: '8. Baseline Approval', icon: Lock },
    { to: `/sprint/${sprintId}/recommendations`, label: '9. Recommendations', icon: Sparkles },
    { to: `/sprint/${sprintId}/report`, label: '10. Report & Export', icon: FileText },
  ];

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
              Sprint Steps (24-48h)
            </h2>
            <nav className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    onClick={onClose}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors border-l-2 ${
                        isActive
                          ? 'bg-brand-50 text-brand-800 border-brand-500 font-semibold'
                          : 'text-ink-600 border-transparent hover:text-ink-900 hover:bg-surface'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
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
