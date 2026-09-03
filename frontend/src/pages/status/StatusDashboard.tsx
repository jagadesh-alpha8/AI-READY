import React from 'react';
import {
  Gauge, Building2, ShieldCheck, Layers, Target, ListChecks, Bot, Bell,
  Network, ClipboardCheck, Settings, CalendarDays, PieChart, AlertTriangle,
} from 'lucide-react';

type LucideIcon = typeof Gauge;
type PlanStatus = 'live' | 'next' | 'planned';

interface PlanModule {
  label: string;
  icon: LucideIcon;
  status: PlanStatus;
  note: string;
}

/**
 * The build-status snapshot behind this page. Mirrors the module list in
 * `Sidebar.tsx` (the approved product plan) plus a depth read-out of the one
 * module that's actually live. This is a manually maintained engineering
 * snapshot, not a live metric endpoint -- there is nothing in the backend
 * that computes "% complete", so update the numbers here by hand when the
 * build state moves, the same way the plan list in Sidebar.tsx is hand-kept.
 */
const REPORT_DATE = 'September 3, 2026';

const PLAN_MODULES: PlanModule[] = [
  { label: 'Dashboard', icon: Gauge, status: 'live', note: 'Cross-sprint summary metrics. Fully working.' },
  { label: 'Institution DNA', icon: Building2, status: 'live', note: 'Profile, leadership, departments, IT systems.' },
  { label: 'AI Readiness Audit', icon: ShieldCheck, status: 'live', note: 'The 10-step discovery-sprint engine — see below.' },
  { label: 'Evidence Intelligence', icon: Layers, status: 'next', note: 'Next in the build queue. No code yet.' },
  { label: 'Transformation Plan', icon: Target, status: 'planned', note: 'Not started.' },
  { label: 'Goals & Tasks', icon: ListChecks, status: 'planned', note: 'Not started.' },
  { label: 'AI Copilot', icon: Bot, status: 'planned', note: 'Not started.' },
  { label: 'Reminders', icon: Bell, status: 'planned', note: 'Not started.' },
  { label: 'Compliance Mapping', icon: Network, status: 'planned', note: 'Not started.' },
  { label: 'UAT Readiness', icon: ClipboardCheck, status: 'planned', note: 'Not started.' },
  { label: 'Admin / Settings', icon: Settings, status: 'planned', note: 'Not started.' },
  { label: 'Build Timeline', icon: CalendarDays, status: 'planned', note: 'Not started.' },
  { label: 'Status Dashboard', icon: PieChart, status: 'live', note: 'This page.' },
];

const AUDIT_STEPS: { label: string; pct: number; note: string }[] = [
  { label: '1. Sprint Setup', pct: 100, note: 'Full lifecycle state machine.' },
  { label: '2. Upload Data Pack', pct: 90, note: 'Manual + Google Drive import; one known checklist bug.' },
  { label: '3. AI Processing Monitor', pct: 75, note: 'Digital PDFs reliable; no OCR for scans yet.' },
  { label: '4. Extracted Facts Review', pct: 100, note: 'Confirm / correct / reject, full history.' },
  { label: '5. Gap Dashboard', pct: 90, note: '5 automated gap types + AI conflict checks.' },
  { label: '6. Owner Workspace', pct: 95, note: 'Role owners resolve assigned facts & gaps.' },
  { label: '7. Live CRI Preview', pct: 100, note: '8-pillar score, deterministic & explainable.' },
  { label: '8. Baseline Approval', pct: 100, note: 'Consultant sign-off locks the score.' },
  { label: '9. Recommendations', pct: 90, note: '3 generators; consultant-editable.' },
  { label: '10. Report & Export', pct: 100, note: 'Versioned PDF / DOCX report.' },
];

const OPS_READINESS: { label: string; pct: number; note: string }[] = [
  { label: 'Production Security Hardening', pct: 40, note: 'Placeholder secret keys, demo credentials, no HTTPS, no rate-limiting.' },
  { label: 'Automated Testing & QA', pct: 70, note: '481 backend tests; zero frontend tests.' },
  { label: 'Deployment & Infrastructure', pct: 80, note: 'Docker + CI/CD live; no monitoring or backups yet.' },
];

const ACTIVITY: { date: string; title: string; desc: string }[] = [
  { date: 'Sep 3', title: 'Institution DNA module', desc: 'Profile, leadership, departments, IT systems & digital-maturity rating.' },
  { date: 'Sep 2', title: 'Navigation rebuilt', desc: 'Menu restructured around the 12-module product plan.' },
  { date: 'Sep 1', title: 'Google Drive import', desc: "Added to the AI Readiness Audit's upload step." },
  { date: 'Aug 28', title: 'CI/CD pipeline', desc: 'Automated build → registry → cloud VM deploy.' },
  { date: 'Aug 27', title: 'Initial platform build', desc: 'AI Readiness Audit engine end to end, plus dashboard.' },
];

const BUILD_QUEUE = [
  'Evidence Intelligence', 'Transformation Plan', 'Goals & Tasks', 'AI Copilot',
  'Reminders', 'Compliance Mapping', 'UAT Readiness', 'Admin / Settings', 'Build Timeline',
];

function depthTone(pct: number): { bar: string; text: string; badge: string } {
  if (pct >= 90) return { bar: 'bg-success-solid', text: 'text-success', badge: 'badge-success' };
  if (pct >= 70) return { bar: 'bg-warning-solid', text: 'text-warning', badge: 'badge-warning' };
  return { bar: 'bg-danger-solid', text: 'text-danger', badge: 'badge-danger' };
}

const PLAN_BADGE: Record<PlanStatus, string> = {
  live: 'badge-brand',
  next: 'badge-warning',
  planned: 'badge-neutral',
};
const PLAN_LABEL: Record<PlanStatus, string> = { live: 'Live', next: 'Next', planned: 'Planned' };

function ProgressBar({ pct }: { pct: number }) {
  const tone = depthTone(pct);
  return (
    <div className="w-full bg-line-200 h-1.5 rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export const StatusDashboard: React.FC = () => {
  const liveCount = PLAN_MODULES.filter((m) => m.status === 'live').length;
  const planPct = Math.round((liveCount / PLAN_MODULES.length) * 100);
  const auditPct = Math.round(AUDIT_STEPS.reduce((s, x) => s + x.pct, 0) / AUDIT_STEPS.length);

  return (
    <div className="space-y-6">
      {/* Header banner */}
      <div className="glass-card p-6 sm:p-8 bg-gradient-to-br from-brand-50 to-card">
        <span className="text-xs font-bold uppercase tracking-wide text-brand-800">Engineering status report</span>
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-900 tracking-tight mt-1 text-balance">
          Project Status Dashboard
        </h1>
        <p className="text-sm text-ink-600 mt-1.5 max-w-2xl">
          Built against the approved 12-module product plan, taken directly from the app's own navigation menu.
          Report date: {REPORT_DATE}.
        </p>
      </div>

      {/* Headline metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Modules live</span>
            <PieChart className="w-4 h-4 text-brand-800" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">
            {liveCount} <span className="text-sm text-ink-500 font-normal">/ {PLAN_MODULES.length}</span>
          </p>
          <span className="text-xs text-brand-800 mt-1 inline-block font-medium">Approved product plan</span>
        </div>

        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Plan coverage</span>
            <Gauge className="w-4 h-4 text-info" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{planPct}%</p>
          <span className="text-xs text-info mt-1 inline-block font-medium">9 modules not started</span>
        </div>

        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Flagship module depth</span>
            <ShieldCheck className="w-4 h-4 text-success" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{auditPct}%</p>
          <span className="text-xs text-success mt-1 inline-block font-medium">AI Readiness Audit · 481 backend tests</span>
        </div>
      </div>

      <div className="panel-muted text-left px-5 py-4">
        <p className="text-sm text-ink-700">
          <span className="font-semibold text-ink-900">Reading this dashboard: </span>
          "Plan coverage" counts modules in the approved 12-module roadmap — most are simply not started yet.
          "Flagship module depth" is a different question: of the one module that IS built (the discovery-sprint
          engine), how solid is it. Both numbers are real; neither substitutes for the other.
        </p>
      </div>

      {/* Product plan grid */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Product plan — all {PLAN_MODULES.length} modules</h2>
          <span className="text-xs text-ink-500">Order and status as maintained in the navigation menu</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PLAN_MODULES.map((m) => {
            const Icon = m.icon;
            return (
              <div
                key={m.label}
                className={`rounded-lg border border-line-200 p-4 flex flex-col gap-2 ${m.status === 'planned' ? 'opacity-70' : ''}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-ink-900 font-semibold text-sm">
                    <Icon className="w-4 h-4 text-ink-500 shrink-0" />
                    <span className="truncate">{m.label}</span>
                  </div>
                  <span className={PLAN_BADGE[m.status]}>{PLAN_LABEL[m.status]}</span>
                </div>
                <p className="text-xs text-ink-500">{m.note}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Inside the AI Readiness Audit */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Inside the AI Readiness Audit — step by step</h2>
          <span className="text-xs text-ink-500">The one module that's fully built</span>
        </div>
        <div className="table-shell">
          <table className="table-base">
            <thead>
              <tr>
                <th>Step</th>
                <th className="w-40">Depth</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {AUDIT_STEPS.map((s) => {
                const tone = depthTone(s.pct);
                return (
                  <tr key={s.label}>
                    <td className="font-medium text-ink-900 whitespace-nowrap">{s.label}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        <ProgressBar pct={s.pct} />
                        <span className={`font-mono text-xs font-semibold tabular-nums ${tone.text}`}>{s.pct}%</span>
                      </div>
                    </td>
                    <td className="text-ink-600">{s.note}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Operational readiness */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Operational readiness</h2>
          <span className="text-xs text-ink-500">Cross-cutting — applies once modules go live</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {OPS_READINESS.map((o) => {
            const tone = depthTone(o.pct);
            return (
              <div key={o.label} className="rounded-lg border border-line-200 p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ink-900">{o.label}</span>
                  <span className={`font-mono text-sm font-bold tabular-nums ${tone.text}`}>{o.pct}%</span>
                </div>
                <ProgressBar pct={o.pct} />
                <p className="text-xs text-ink-500">{o.note}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Activity + build queue */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card p-5 sm:p-6">
          <h2 className="eyebrow mb-4">Recent activity</h2>
          <ul className="space-y-4">
            {ACTIVITY.map((a, i) => (
              <li key={a.title} className="relative pl-5">
                <span className={`absolute left-0 top-1.5 w-2 h-2 rounded-full ${i === 0 ? 'bg-brand-500' : 'bg-line-300'}`} />
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-brand-800">{a.date}</span>
                  {i === 0 && <span className="badge-brand">Today</span>}
                </div>
                <p className="text-sm font-semibold text-ink-900 mt-0.5">{a.title}</p>
                <p className="text-xs text-ink-500">{a.desc}</p>
              </li>
            ))}
          </ul>
        </div>

        <div className="glass-card p-5 sm:p-6">
          <h2 className="eyebrow mb-4">Build queue — what's next</h2>
          <ul className="space-y-1.5">
            {BUILD_QUEUE.map((name, i) => (
              <li
                key={name}
                className={`flex items-center gap-3 text-sm px-3 py-2 rounded-lg ${i === 0 ? 'bg-brand-50 text-brand-800 font-semibold' : 'text-ink-700'}`}
              >
                <span className="font-mono text-xs text-ink-500 w-5 shrink-0">{i === 0 ? '→' : String(i + 1).padStart(2, '0')}</span>
                <span>{name}{i === 0 ? ' — next up' : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Risks */}
      <div className="rounded-xl border border-warning-line bg-warning-bg p-5 sm:p-6 flex gap-4 items-start">
        <div className="shrink-0 w-9 h-9 rounded-lg bg-card border border-line-200 flex items-center justify-center text-warning">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div>
          <h2 className="font-bold text-ink-900 text-sm mb-2">Before real institution data goes live</h2>
          <ul className="list-disc pl-5 space-y-1 text-sm text-ink-700">
            <li>Production <b className="text-danger">security hardening</b> is the top open item — placeholder secret keys, demo login credentials, no HTTPS, no login rate-limiting.</li>
            <li>A naming mismatch means some <b className="text-danger">Google Drive imports</b> aren't credited against the required-documents checklist.</li>
            <li>Scanned/photographed documents aren't readable yet — <b className="text-danger">no OCR</b> backend, only born-digital PDFs.</li>
          </ul>
        </div>
      </div>

      <p className="text-xs text-ink-400 text-center pb-2">
        Compiled from the approved product-module plan in Sidebar.tsx, cross-checked against a code-level audit and commit history. Maintained by hand — update the numbers above as the build moves.
      </p>
    </div>
  );
};
