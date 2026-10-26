import React from 'react';
import { Link } from 'react-router-dom';

import { getProvenance } from '../../api/benchmarks';
import type { IndicatorOrigin, IndicatorProvenance, SourceReferenceRow } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { studioHref } from './studioNav';

/**
 * One indicator's origin and source mappings (Benchmark Library), read-only.
 * - Origin: where the indicator came from -- for AI-QIF, the manager-provided workbook, sheet and row.
 * - Source mappings: Source Library documents, only where the workbook (or an earlier reviewed link) maps them:
 *   source, version, page, exact quote, relationship. Nothing is inferred; with none, "Source mapping not provided."
 */

const day = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString() : '');

const originLine = (o: IndicatorOrigin) => {
  if (o.type === 'framework_import') {
    return [o.workbook, o.sheet && `sheet “${o.sheet}”`, o.row && `row ${o.row}`, o.framework_version,
      o.imported_at && `imported ${day(o.imported_at)}`].filter(Boolean).join(' · ');
  }
  if (o.type === 'candidate') return `Earlier benchmark candidate “${o.candidate_title}”`;
  if (o.type === 'manual') return [o.description, o.reference].filter(Boolean).join(' · ');
  return o.label;
};

export const OriginSources: React.FC<{ benchmarkCode: string }> = ({ benchmarkCode }) => {
  const { data, loading, error, refetch } = useApiResource<IndicatorProvenance>(
    () => getProvenance(benchmarkCode), [benchmarkCode],
  );
  if (loading) return <LoadingState message="Loading sources…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (!data) return null;
  const refs = data.source_references;
  return (
    <section className="space-y-2" aria-label="Origin and sources">
      <p className="text-ink-700"><strong>Origin:</strong> {originLine(data.origin)}</p>
      <div className="space-y-1.5">
        <p className="font-bold text-ink-900">Source mappings{refs.length ? ` (${refs.length})` : ''}</p>
        {refs.length === 0 && <p className="text-ink-700">Source mapping not provided.</p>}
        {refs.map((r) => <MappingRow key={r.requirement_code} r={r} />)}
      </div>
    </section>
  );
};

const MappingRow: React.FC<{ r: SourceReferenceRow }> = ({ r }) => (
  <div className="rounded-lg border border-line-200 bg-surface p-2 space-y-0.5">
    <p className="text-ink-900">
      <Link className="font-mono text-brand-700 hover:underline" to={studioHref({ tab: 'sources', source: r.source_code })}>
        {r.source_code}
      </Link>
      {r.source_title ? ` ${r.source_title}` : ''}
      <span className="text-ink-500"> · version {r.source_version} · page {r.page ?? 'not given'} · {r.relationship_label || r.relationship}</span>
    </p>
    <p className="italic text-ink-700">“{r.source_quote}”</p>
  </div>
);
