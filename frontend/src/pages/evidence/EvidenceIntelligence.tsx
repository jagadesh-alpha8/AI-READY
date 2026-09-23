import React, { useMemo, useState } from 'react';
import { FileStack, FileText, Upload } from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import { EVIDENCE_DOCS } from '../../data/workspaceDemo';
import type { EvidenceStatus } from '../../data/workspaceDemo';

/** Ported from the InGage prototype's Evidence page. Every document the
 * institution needs, what state it is in, and what is missing entirely. */

type Filter = EvidenceStatus | 'all';

const STATUS_BADGE: Record<EvidenceStatus, string> = {
  verified: 'badge-success',
  uploaded: 'badge-info',
  under_review: 'badge-warning',
  incomplete: 'badge-warning',
  missing: 'badge-danger',
};

const STATUS_LABEL: Record<EvidenceStatus, string> = {
  verified: 'Verified',
  uploaded: 'Uploaded',
  under_review: 'Under review',
  incomplete: 'Incomplete',
  missing: 'Missing',
};

const FILTERS: Filter[] = ['all', 'verified', 'uploaded', 'under_review', 'incomplete', 'missing'];

export const EvidenceIntelligence: React.FC = () => {
  const [filter, setFilter] = useState<Filter>('all');

  const options = useMemo(
    () =>
      FILTERS.map((id) => ({
        id,
        label: id === 'all' ? 'All' : STATUS_LABEL[id],
        count: id === 'all' ? EVIDENCE_DOCS.length : EVIDENCE_DOCS.filter((d) => d.status === id).length,
      })),
    [],
  );

  const visible = filter === 'all' ? EVIDENCE_DOCS : EVIDENCE_DOCS.filter((d) => d.status === filter);
  const missing = EVIDENCE_DOCS.filter((d) => d.status === 'missing').length;

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="Uploading is not wired up — the real upload path is Sprint step 2." />

      <PageHeader
        icon={FileStack}
        title="Evidence Intelligence"
        description="Every document the assessment needs, its verification state, and what is still missing."
        actions={
          <button type="button" className="btn-secondary btn-sm" disabled title="Not wired up in this demo">
            <Upload className="w-3.5 h-3.5" />
            <span>Upload</span>
          </button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Metric label="Documents tracked" value={EVIDENCE_DOCS.length} />
        <Metric label="Verified" value={EVIDENCE_DOCS.filter((d) => d.status === 'verified').length} />
        <Metric label="Missing entirely" value={missing} tone={missing > 0 ? 'danger' : 'default'} />
      </div>

      <FilterPills options={options} active={filter} onChange={setFilter} />

      <div className="space-y-2">
        {visible.map((doc) => (
          <div key={doc.id} className="glass-card p-4 flex items-center gap-4">
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                doc.status === 'missing'
                  ? 'bg-danger-bg text-danger'
                  : doc.status === 'verified'
                    ? 'bg-success-bg text-success'
                    : 'bg-info-bg text-info'
              }`}
            >
              <FileText className="w-[18px] h-[18px]" />
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink-900 truncate">{doc.title}</p>
              <p className="text-xs text-ink-500">
                {doc.dept} · {doc.type}
              </p>
              {doc.issues && (
                <p className="text-xs text-warning mt-0.5">{doc.issues.join(' · ')}</p>
              )}
            </div>

            {doc.score > 0 && (
              <div className="text-right hidden sm:block shrink-0">
                <p className="text-sm font-bold text-ink-900 tabular-nums">{doc.score}%</p>
                <p className="text-[10px] text-ink-500">complete</p>
              </div>
            )}

            <span className={`badge ${STATUS_BADGE[doc.status]} shrink-0`}>{STATUS_LABEL[doc.status]}</span>
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
