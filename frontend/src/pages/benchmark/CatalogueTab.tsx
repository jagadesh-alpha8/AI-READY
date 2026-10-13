import React, { useState } from 'react';

import { listCatalogue, listEvidenceTypes, listPillars } from '../../api/benchmarks';
import type { CatalogueBenchmark, CataloguePillar, EvidenceTypeInfo } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { BenchmarkLinks } from './RequirementLinking';

/**
 * The real benchmark catalogue (stage 3.1): 10 pillars, 60 benchmarks and 12
 * evidence types imported from the Source Pack. Read-only for now -- linking
 * requirements (3.2) and writing real L3/L2/L1 levels (3.3) come next.
 */

const KIND_BADGE: Record<string, string> = {
  mandatory: 'badge-brand',
  guidance: 'badge-neutral',
  recommended: 'badge-neutral',
  proposed: 'badge-warning',
};

export const CatalogueTab: React.FC<{ onEditLevels?: (code: string) => void }> = ({ onEditLevels }) => {
  const [pillar, setPillar] = useState('');
  const [kind, setKind] = useState('');
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const pillars = useApiResource<CataloguePillar[]>(() => listPillars(), []);
  const evidence = useApiResource<EvidenceTypeInfo[]>(() => listEvidenceTypes(), []);
  const { data, loading, error, refetch } = useApiResource<CatalogueBenchmark[]>(
    () => listCatalogue({ pillar: pillar || undefined, kind: kind || undefined, q: query || undefined }),
    [pillar, kind, query],
  );
  const evidenceName = (code: string) => evidence.data?.find((e) => e.code === code)?.name || code;
  const placeholderCount = (data || []).filter((b) => !b.levels_defined).length;

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        The benchmark catalogue from the Source Pack. Every benchmark is a draft: it needs linked requirements,
        real L3/L2/L1 definitions and (for InGage-proposed ones) an expert owner before it can be released.
      </p>

      {pillars.data && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {pillars.data.map((p) => (
            <button
              key={p.code}
              onClick={() => setPillar(pillar === p.code ? '' : p.code)}
              className={`glass-card p-3 text-left text-xs space-y-1 ${pillar === p.code ? 'ring-2 ring-brand-500' : ''}`}
              title={p.coverage}
            >
              <p className="font-mono text-ink-500">{p.code}</p>
              <p className="font-bold text-ink-900 leading-snug">{p.name}</p>
              <p className="text-ink-500">
                {p.benchmark_count} benchmarks · {p.mandatory_count} mandatory · {p.proposed_count} proposed
              </p>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input className="input flex-1 min-w-[200px]" placeholder="Search code, title or source"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All kinds</option>
          <option value="mandatory">Mandatory / authoritative</option>
          <option value="guidance">Guidance-backed</option>
          <option value="proposed">InGage proposed</option>
        </select>
        {pillar && <button className="btn-secondary btn-sm" onClick={() => setPillar('')}>Clear pillar {pillar}</button>}
      </div>

      {data && placeholderCount > 0 && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-xs text-ink-700">
          {placeholderCount} of {data.length} benchmarks shown still have the Source Pack's generic placeholder
          L3/L2/L1 text. Real level definitions are expert work (stage 3.3) - nothing is scored against them yet.
        </div>
      )}

      {loading && <LoadingState message="Loading catalogue…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && (
        <EmptyState message="No benchmarks. Import the catalogue: python manage.py import_benchmark_catalogue <Source Pack.xlsx> --commit" />
      )}

      <div className="space-y-2">
        {(data || []).map((b) => {
          const isOpen = open === b.benchmark_code;
          return (
            <div key={b.id} className="glass-card p-4 space-y-2">
              <button className="w-full text-left flex items-start justify-between gap-3 flex-wrap"
                onClick={() => setOpen(isOpen ? null : b.benchmark_code)}>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-ink-900">
                    <span className="font-mono text-ink-500 mr-2">{b.benchmark_code}</span>{b.title}
                  </h3>
                  <p className="text-xs text-ink-500 mt-0.5">
                    {b.pillar_code} {b.pillar_name} · source basis: {b.source_basis || '—'}
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className={`badge ${KIND_BADGE[b.benchmark_kind] || 'badge-neutral'}`}>{b.kind_label}</span>
                  <span className="badge badge-neutral">{b.status}</span>
                  {!b.levels_defined && <span className="badge badge-warning">levels: placeholder</span>}
                  <span className="badge badge-neutral">{b.requirement_count} requirement(s)</span>
                </div>
              </button>

              {isOpen && (
                <div className="space-y-3 text-xs">
                  <p className="text-ink-700"><strong>Capability:</strong> {b.capability}</p>
                  <p className="text-ink-700"><strong>Applies to:</strong> {b.applicability || '—'}</p>
                  {b.benchmark_kind === 'proposed' && !b.expert_owner && (
                    <p className="text-warning">InGage-proposed: needs an expert owner before release.</p>
                  )}
                  {onEditLevels && (
                    <button className="btn-secondary btn-sm" onClick={() => onEditLevels(b.benchmark_code)}>
                      {b.levels_defined ? 'Edit levels' : 'Write L3 / L2 / L1'}
                    </button>
                  )}
                  <div className="grid md:grid-cols-3 gap-2">
                    {b.maturity_levels.map((lv) => (
                      <div key={lv.level} className="rounded-lg border border-line-200 bg-surface p-3 space-y-1">
                        <p className="font-bold text-ink-900">
                          {lv.level_label}
                          {lv.is_placeholder && <span className="badge badge-warning ml-2">placeholder</span>}
                        </p>
                        <p className={lv.is_placeholder ? 'text-ink-500 italic' : 'text-ink-700'}>{lv.definition}</p>
                      </div>
                    ))}
                  </div>
                  <div>
                    <p className="font-bold text-ink-900 mb-1">Evidence types</p>
                    <div className="flex flex-wrap gap-1.5">
                      {b.evidence_types.map((code) => (
                        <span key={code} className="badge badge-neutral" title={evidenceName(code)}>
                          {code} {evidenceName(code)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <p className="text-ink-500">Scoring: {b.scoring_dimensions || '—'} · {b.activation_status}</p>
                  <BenchmarkLinks benchmarkCode={b.benchmark_code} editable={b.status === 'draft'} onChanged={refetch} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
