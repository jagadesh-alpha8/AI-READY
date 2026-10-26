import React, { useEffect, useRef, useState } from 'react';

import { listCatalogue, listPillars } from '../../api/benchmarks';
import type { CatalogueBenchmark, CataloguePillar, NaacCrosswalkLink } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { OriginSources } from './OriginSources';
import { useStudioParam } from './studioNav';

/**
 * The benchmark library, read-only: InGage AI-QIF v1.0 from the manager-provided workbook -- 9 criteria (weights
 * out of 1000) and 36 key indicators. Each indicator opens to its capability, L3/L2/L1, origin, source mappings
 * and NAAC crosswalk. It changes only through the controlled workbook import (`manage.py import_aiqif`).
 */

/** "30.00" -> "30" */
const w = (v: string | null | undefined) => (v == null ? null : String(Number(v)));

export const CatalogueTab: React.FC = () => {
  const [pillar, setPillar] = useState('');
  const [query, setQuery] = useState('');
  // ?code= (e.g. from a source) opens that indicator.
  const [linked] = useStudioParam('code');
  const [open, setOpen] = useState<string | null>(linked || null);
  useEffect(() => { if (linked) setOpen(linked); }, [linked]);
  const scrolledTo = useRef('');

  const pillars = useApiResource<CataloguePillar[]>(() => listPillars(), []);
  const { data, loading, error, refetch } = useApiResource<CatalogueBenchmark[]>(
    () => listCatalogue({ pillar: pillar || undefined, q: query || undefined }), [pillar, query],
  );

  return (
    <div className="space-y-4">
      {pillars.data && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {pillars.data.map((p) => (
            <button
              key={p.code}
              onClick={() => setPillar(pillar === p.code ? '' : p.code)}
              className={`glass-card p-3 text-left text-xs space-y-1 ${pillar === p.code ? 'ring-2 ring-brand-500' : ''}`}
            >
              <p className="font-mono text-ink-500">{p.code}</p>
              <p className="font-bold text-ink-900 leading-snug">{p.name}</p>
              <p className="text-ink-500">
                {w(p.weight) != null && <strong className="text-ink-700">{w(p.weight)} / 1000 · </strong>}
                {p.benchmark_count} indicators
              </p>
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input className="input flex-1 min-w-[200px]" placeholder="Search code or title"
          value={query} onChange={(e) => setQuery(e.target.value)} />
        {pillar && <button className="btn-secondary btn-sm" onClick={() => setPillar('')}>Clear {pillar}</button>}
      </div>

      {loading && <LoadingState message="Loading catalogue…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && <EmptyState message="No indicators match." />}

      <div className="space-y-2">
        {(data || []).map((b, i) => {
          const isOpen = open === b.benchmark_code;
          return (
            <div key={b.id} id={`benchmark-${b.benchmark_code}`} className="glass-card p-4 space-y-2"
              ref={(el) => {
                if (el && isOpen && linked === b.benchmark_code && scrolledTo.current !== linked) {
                  scrolledTo.current = linked;
                  el.scrollIntoView({ block: 'start' });
                }
              }}>
              <button className="w-full text-left" onClick={() => setOpen(isOpen ? null : b.benchmark_code)}
                aria-expanded={isOpen}>
                <h3 className="text-sm font-bold text-ink-900">
                  <span className="tabular-nums text-ink-500 mr-2">{i + 1}.</span>
                  <span className="font-mono text-ink-500 mr-2">{b.benchmark_code}</span>{b.title}
                </h3>
                <p className="text-xs text-ink-500 mt-0.5">
                  {b.pillar_code} {b.pillar_name}
                  {w(b.weight) != null && <> · weight {w(b.weight)} / 1000</>}
                </p>
              </button>

              {isOpen && (
                <div className="space-y-3 text-xs">
                  <p className="text-ink-700"><strong>Capability:</strong> {b.capability}</p>
                  <div className="grid md:grid-cols-3 gap-2">
                    {b.maturity_levels.map((lv) => (
                      <div key={lv.level} className="rounded-lg border border-line-200 bg-surface p-3 space-y-1">
                        <p className="font-bold text-ink-900">{lv.level_label}</p>
                        <p className="text-ink-700">{lv.definition}</p>
                      </div>
                    ))}
                  </div>
                  <OriginSources benchmarkCode={b.benchmark_code} />
                  <NaacCrosswalk links={b.naac_crosswalk || []} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** NAAC metrics the workbook's crosswalk sheet maps to this key indicator. */
const NaacCrosswalk: React.FC<{ links: NaacCrosswalkLink[] }> = ({ links }) => {
  const [all, setAll] = useState(false);
  if (!links.length) return <p className="text-ink-500"><strong className="text-ink-900">NAAC crosswalk:</strong> none</p>;
  const shown = all ? links : links.slice(0, 5);
  return (
    <div>
      <p className="font-bold text-ink-900 mb-1">NAAC crosswalk ({links.length})</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="text-ink-500">
            <tr><th className="py-1 pr-3">Metric</th><th className="py-1 pr-3">Relationship</th><th className="py-1">NAAC requirement</th></tr>
          </thead>
          <tbody>
            {shown.map((l) => (
              <tr key={l.metric} className="border-t border-line-200 align-top">
                <td className="py-1 pr-3 font-mono whitespace-nowrap">{l.metric}</td>
                <td className="py-1 pr-3 whitespace-nowrap">{l.relationship}</td>
                <td className="py-1 text-ink-700">{l.requirement}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {links.length > 5 && (
        <button className="btn-secondary btn-sm mt-1" onClick={() => setAll(!all)}>
          {all ? 'Show fewer' : `Show all ${links.length}`}
        </button>
      )}
    </div>
  );
};
