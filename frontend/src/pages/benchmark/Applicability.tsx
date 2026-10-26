import React, { useState } from 'react';

import { listPreviewColleges, previewApplicability } from '../../api/benchmarks';
import type { ApplicabilityPreview, ApplicabilityResult, PreviewCollege } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';

/**
 * Applicability Preview (read-only): pick a college; every indicator's result and reason comes from the
 * catalogue's applicability rules and that college's SAVED benchmark profile (the one Benchmark Assessment uses).
 * A college without a saved profile shows that, and nothing else -- no profile is guessed or typed in here.
 * An indicator with no rules shows "requires review", never "applies".
 */

export const RESULT_BADGE: Record<ApplicabilityResult, string> = {
  applies: 'badge-success',
  does_not_apply: 'badge-neutral',
  optional: 'badge-brand',
  requires_review: 'badge-warning',
};
const RESULT_LABEL: Record<ApplicabilityResult, string> = {
  applies: 'Applies', does_not_apply: 'Does not apply', optional: 'Optional', requires_review: 'Requires review',
};

export const ApplicabilityPreviewTab: React.FC = () => {
  const colleges = useApiResource<PreviewCollege[]>(() => listPreviewColleges(), []);
  const [college, setCollege] = useState('');
  const preview = useApiResource<ApplicabilityPreview | null>(
    () => (college ? previewApplicability(college) : Promise.resolve({ data: null })), [college],
  );
  const [filter, setFilter] = useState<ApplicabilityResult | ''>('');

  if (colleges.loading) return <LoadingState message="Loading colleges…" />;
  if (colleges.error || !colleges.data) return <ErrorState message={colleges.error || 'Failed'} onRetry={colleges.refetch} />;
  const result = preview.data;
  const rows = (result?.benchmarks || []).filter((b) => !filter || b.result === filter);

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Which indicators apply to a college, from its saved benchmark profile. Nothing is saved or changed here.
      </p>
      <label className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
        College
        <select className="input text-sm min-w-[240px]" value={college} onChange={(e) => { setCollege(e.target.value); setFilter(''); }}>
          <option value="">Choose a college…</option>
          {colleges.data.map((c) => (
            <option key={c.id} value={c.id}>{c.name}{c.has_profile ? '' : ' (no saved profile)'}</option>
          ))}
        </select>
      </label>
      {colleges.data.length === 0 && <EmptyState message="No colleges yet." />}

      {preview.loading && college && <LoadingState message="Checking applicability…" />}
      {preview.error && <ErrorState message={preview.error} onRetry={preview.refetch} />}
      {result && !result.profile && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-sm text-ink-700">{result.detail}</div>
      )}
      {result?.profile && (
        <>
          <p className="text-xs text-ink-500">
            Saved profile: {result.profile.institution_type}
            {result.profile.autonomous_status ? ` · ${result.profile.autonomous_status}` : ''}
            {' · '}programmes: {result.profile.programme_types.join(', ') || 'none'}
            {' · '}approvals: {result.profile.approval_bodies.join(', ') || 'none'} · {result.profile.jurisdiction}
          </p>
          <div className="flex flex-wrap gap-2 text-xs">
            <button className={`badge ${filter === '' ? 'badge-brand' : 'badge-neutral'}`} onClick={() => setFilter('')}>
              All {result.benchmarks.length}
            </button>
            {(Object.keys(RESULT_LABEL) as ApplicabilityResult[]).map((r) => (
              <button key={r} className={`badge ${filter === r ? 'badge-brand' : RESULT_BADGE[r]}`} onClick={() => setFilter(r)}>
                {RESULT_LABEL[r]}: {result.counts[r] || 0}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            {rows.map((b) => (
              <div key={b.benchmark_code} className="glass-card p-3 flex items-start gap-2 text-xs">
                <span className={`badge ${RESULT_BADGE[b.result]}`}>{RESULT_LABEL[b.result]}</span>
                <div className="min-w-0">
                  <p className="text-ink-900"><span className="font-mono text-ink-500 mr-1">{b.benchmark_code}</span>{b.title}</p>
                  <p className="text-ink-500">{b.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
