import React, { useState } from 'react';
import { Network } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import { COMPLIANCE_FRAMEWORKS, COMPLIANCE_ROWS, MAPPING_STATUS_LABELS } from '../../data/workspaceDemo';
import type { MappingStatus } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's Compliance page: the institution's
 * evidence mapped onto the accreditation frameworks it is already assessed
 * against — NAAC, NBA, NIRF, NEP — plus InGage's own AI framework. */

type Filter = 'all' | (typeof COMPLIANCE_FRAMEWORKS)[number];

const STATUS_BADGE: Record<MappingStatus, string> = {
  not_started: 'badge-neutral',
  evidence_missing: 'badge-danger',
  partially_mapped: 'badge-warning',
  mapped: 'badge-info',
  verified: 'badge-success',
};

/** Confidence is a percentage, so it gets a colour band rather than a badge —
 * the number is the point, not the category. */
function confidenceTone(value: number): string {
  if (value >= 60) return 'text-success';
  if (value >= 40) return 'text-warning';
  return 'text-danger';
}

export const ComplianceMapping: React.FC = () => {
  const [filter, setFilter] = useState<Filter>('all');

  const visible = filter === 'all' ? COMPLIANCE_ROWS : COMPLIANCE_ROWS.filter((m) => m.framework === filter);

  const options: { id: Filter; label: string; count?: number }[] = [
    { id: 'all', label: 'All frameworks', count: COMPLIANCE_ROWS.length },
    ...COMPLIANCE_FRAMEWORKS.map((f) => ({
      id: f as Filter,
      label: f.replace(/_/g, ' '),
      count: COMPLIANCE_ROWS.filter((m) => m.framework === f).length,
    })),
  ];

  const unmapped = COMPLIANCE_ROWS.filter(
    (m) => m.status === 'not_started' || m.status === 'evidence_missing',
  ).length;

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="The criteria lists are samples — no official framework has been loaded." />

      <PageHeader
        icon={Network}
        title="Compliance Mapping"
        description="Which accreditation criteria the institution's evidence already supports, and which have nothing behind them."
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Metric label="Criteria tracked" value={COMPLIANCE_ROWS.length} />
        <Metric label="Frameworks" value={COMPLIANCE_FRAMEWORKS.length} />
        <Metric label="Missing or not started" value={unmapped} tone="danger" />
      </div>

      <FilterPills options={options} active={filter} onChange={setFilter} />

      <div className="space-y-2">
        {visible.map((row) => (
          <div key={row.id} className="glass-card p-4 flex items-center gap-4">
            <div className="w-11 h-10 rounded-lg bg-accent-bg text-accent flex items-center justify-center text-[11px] font-bold shrink-0">
              {row.framework.slice(0, 4).replace('_', '')}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink-900 truncate">{row.criterion}</p>
              <p className="text-xs text-ink-500">
                {row.framework.replace(/_/g, ' ')} · {row.gaps} gap{row.gaps === 1 ? '' : 's'}
              </p>
            </div>

            <div className="text-right hidden sm:block shrink-0">
              <p className={`text-sm font-bold tabular-nums ${confidenceTone(row.confidence)}`}>
                {row.confidence}%
              </p>
              <p className="text-[10px] text-ink-500">confidence</p>
            </div>

            <span className={`badge ${STATUS_BADGE[row.status]} shrink-0`}>
              {MAPPING_STATUS_LABELS[row.status]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number; tone?: 'default' | 'danger' }> = ({
  label, value, tone = 'default',
}) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p className={`text-2xl font-bold mt-1 tabular-nums ${tone === 'danger' ? 'text-danger' : 'text-ink-900'}`}>
      {value}
    </p>
  </div>
);
