import React from 'react';
import { ClipboardCheck } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { PageHeader } from '../../components/PageHeader';
import { UAT_ITEMS } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's UAT page: the checklist a client signs
 * off before an engagement is called complete. */

const RISK_BADGE = {
  low: 'badge-success',
  medium: 'badge-warning',
  high: 'badge-danger',
} as const;

export const UatReadiness: React.FC = () => {
  const ready = UAT_ITEMS.filter((i) => i.status === 'ready').length;
  const total = UAT_ITEMS.length;
  const pct = Math.round((ready / total) * 100);

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="The checklist is the prototype's; sign-off is not recorded anywhere." />

      <PageHeader
        icon={ClipboardCheck}
        title="UAT Readiness"
        description="What the client accepts before the engagement is called done — and what still carries risk."
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Metric label="Ready" value={ready} tone="success" />
        <Metric label="In progress" value={total - ready} tone="warning" />
        <Metric label="Completion" value={`${pct}%`} />
      </div>

      <div className="table-shell">
        <table className="table-base">
          <thead>
            <tr>
              <th>Module</th>
              <th>Item</th>
              <th>Status</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {UAT_ITEMS.map((item) => (
              <tr key={`${item.module}-${item.item}`}>
                <td className="text-ink-600 whitespace-nowrap">{item.module}</td>
                <td className="font-medium text-ink-900">{item.item}</td>
                <td>
                  <span className={`badge ${item.status === 'ready' ? 'badge-success' : 'badge-warning'}`}>
                    {item.status === 'ready' ? 'Ready' : 'In progress'}
                  </span>
                </td>
                <td>
                  <span className={`badge ${RISK_BADGE[item.risk]}`}>{item.risk}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Metric: React.FC<{
  label: string;
  value: number | string;
  tone?: 'default' | 'success' | 'warning';
}> = ({ label, value, tone = 'default' }) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p
      className={`text-2xl font-bold mt-1 tabular-nums ${
        tone === 'success' ? 'text-success' : tone === 'warning' ? 'text-warning' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
  </div>
);
