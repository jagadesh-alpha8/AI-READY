import React, { useState } from 'react';

import { confirmBenchmark, listCatalogue, listEvidenceTypes, listPillars, withdrawBenchmarkConfirmation } from '../../api/benchmarks';
import type { CatalogueBenchmark, CataloguePillar, EvidenceTypeInfo, NaacCrosswalkLink } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { BenchmarkLinks } from './RequirementLinking';
import { AiBadge } from './AiBadge';

/**
 * The benchmark library: InGage AI-QIF v1.0 -- 9 criteria (shown as pillars,
 * weights out of 1000) and 36 key indicators, each a draft benchmark with
 * L3/L2/L1 and the NAAC metrics that can support it. Imported with
 * `manage.py import_aiqif`; experts confirm the levels in "Write levels".
 */

/** "30.00" -> "30" */
const w = (v: string | null | undefined) => (v == null ? null : String(Number(v)));

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
        InGage AI-QIF v1.0: the criteria below are the pillars (weights out of 1000), and each key indicator is a
        benchmark with L3 / L2 / L1. Every one is a draft until experts confirm its levels, name an owner and add
        evidence and applicability rules. NAAC evidence only supports a key indicator; it never proves AI readiness.
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
                {w(p.weight) != null && <strong className="text-ink-700">{w(p.weight)} / 1000 · </strong>}
                {p.benchmark_count} benchmarks
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
          {placeholderCount} of {data.length} benchmarks shown still use the shared L3/L2/L1 template wording.
          An expert confirms or rewrites each level (Write levels) before the benchmark can be released.
        </div>
      )}

      {loading && <LoadingState message="Loading catalogue…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && (
        <EmptyState message="No benchmarks. Import AI-QIF: python manage.py import_aiqif <AI-QIF master.xlsx> --commit" />
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
                    {b.pillar_code} {b.pillar_name} · {b.version_label}
                    {w(b.weight) != null && <> · weight {w(b.weight)} (criterion {w(b.pillar_weight) ?? '—'}) of 1000</>}
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className={`badge ${KIND_BADGE[b.benchmark_kind] || 'badge-neutral'}`}>{b.kind_label}</span>
                  <span className="badge badge-neutral">{b.status}</span>
                  <ConfirmationBadge b={b} />
                  {!b.levels_defined && <span className="badge badge-warning">levels: placeholder</span>}
                  <span className="badge badge-neutral">{b.requirement_count} requirement(s)</span>
                </div>
              </button>

              {isOpen && (
                <div className="space-y-3 text-xs">
                  <p className="text-ink-700"><strong>Capability:</strong> {b.capability}</p>
                  <p className="text-ink-700"><strong>Applies to:</strong> {b.applicability || '—'}</p>
                  <p className="text-ink-700"><strong>Source:</strong> {b.source_basis || '—'}</p>
                  {b.benchmark_kind === 'proposed' && !b.expert_owner && (
                    <p className="text-warning">InGage-proposed: needs an expert owner before release.</p>
                  )}
                  {b.status === 'draft' && <ConfirmationPanel b={b} onChanged={refetch} />}
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
                          {!lv.is_placeholder && <span className="ml-2"><AiBadge model={lv.ai_model} /></span>}
                        </p>
                        <p className={lv.is_placeholder ? 'text-ink-500 italic' : 'text-ink-700'}>{lv.definition}</p>
                        {!!lv.observable_requirements?.length && (
                          <ul className="list-disc pl-4 text-ink-500 space-y-0.5 pt-1">
                            {lv.observable_requirements.map((o) => <li key={o}>{o}</li>)}
                          </ul>
                        )}
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
                  <NaacCrosswalk links={b.naac_crosswalk || []} />
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

/** NAAC metrics whose evidence can support this key indicator -- supporting only. */
const NaacCrosswalk: React.FC<{ links: NaacCrosswalkLink[] }> = ({ links }) => {
  const [all, setAll] = useState(false);
  if (!links.length) {
    return <p className="text-ink-500"><strong className="text-ink-900">NAAC crosswalk:</strong> none (AI-specific evidence only).</p>;
  }
  const shown = all ? links : links.slice(0, 5);
  return (
    <div>
      <p className="font-bold text-ink-900 mb-1">
        NAAC crosswalk ({links.length}){' '}
        <span className="font-normal text-ink-500">supporting evidence only, never proof of AI readiness</span>
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="text-ink-500">
            <tr><th className="py-1 pr-3">Metric</th><th className="py-1 pr-3">Relationship</th><th className="py-1">NAAC requirement</th></tr>
          </thead>
          <tbody>
            {shown.map((l) => (
              <tr key={l.metric} className="border-t border-line-200 align-top">
                <td className="py-1 pr-3 font-mono whitespace-nowrap">{l.metric}</td>
                <td className="py-1 pr-3 whitespace-nowrap">
                  {l.relationship}
                  {!!l.shared_with?.length && <span className="text-ink-500"> · also {l.shared_with.join(', ')}</span>}
                </td>
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

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '');

/** Confirmed / changed since confirmed -- drafts only. */
const ConfirmationBadge: React.FC<{ b: CatalogueBenchmark }> = ({ b }) => {
  const c = b.confirmation;
  if (c?.state === 'confirmed') {
    return <span className="badge badge-success" title={`Confirmed by ${c.confirmed_by} on ${when(c.confirmed_at)} - not published`}>Confirmed</span>;
  }
  if (c?.state === 'changed') {
    return <span className="badge badge-warning" title="Edited after it was confirmed - confirm again">Changed since confirmed</span>;
  }
  return null;
};

/** Confirm the draft's content. Publishing is separate: it reaches assessments only in a published release. */
const ConfirmationPanel: React.FC<{ b: CatalogueBenchmark; onChanged: () => void }> = ({ b, onChanged }) => {
  const [note, setNote] = useState('');
  const [withdrawing, setWithdrawing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const state = b.confirmation?.state;

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg({ ok: true, text: ok });
      setNote('');
      setWithdrawing(false);
      onChanged();
    } catch (err: any) {
      setMsg({ ok: false, text: err?.response?.data?.detail || 'Could not save. Please try again.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-line-200 bg-surface p-3 space-y-2">
      <p className="text-ink-700">
        {state === 'confirmed' && <>Confirmed by <strong>{b.confirmation.confirmed_by}</strong> on {when(b.confirmation.confirmed_at)}. </>}
        {state === 'changed' && <><strong className="text-warning">Edited since it was confirmed</strong> by {b.confirmation.confirmed_by} - confirm the new content. </>}
        {state === 'none' && <>Not confirmed yet. </>}
        <span className="text-ink-500">Confirming does not publish: colleges are assessed on it only after it is in a published release (Releases tab).</span>
      </p>
      {msg && <p className={msg.ok ? 'text-success' : 'text-danger'}>{msg.text}</p>}
      {state !== 'confirmed' && (
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1 min-w-[200px] text-xs" placeholder="Note (optional)" value={note}
            onChange={(e) => setNote(e.target.value)} />
          <button className="btn-primary btn-sm" disabled={busy}
            onClick={() => run(() => confirmBenchmark(b.benchmark_code, note), `${b.benchmark_code} confirmed. It stays a draft until a release is published.`)}>
            {busy ? 'Saving…' : state === 'changed' ? 'Confirm again' : 'Confirm'}
          </button>
        </div>
      )}
      {state !== 'none' && (withdrawing ? (
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1 min-w-[200px] text-xs" placeholder="Reason (required)" value={note}
            onChange={(e) => setNote(e.target.value)} />
          <button className="btn-secondary btn-sm" disabled={busy || !note.trim()}
            onClick={() => run(() => withdrawBenchmarkConfirmation(b.benchmark_code, note), 'Confirmation withdrawn.')}>
            Withdraw confirmation
          </button>
          <button className="btn-secondary btn-sm" disabled={busy} onClick={() => { setWithdrawing(false); setNote(''); }}>Cancel</button>
        </div>
      ) : (
        <button className="text-xs text-ink-500 hover:underline" onClick={() => { setWithdrawing(true); setNote(''); setMsg(null); }}>
          Withdraw confirmation…
        </button>
      ))}
    </div>
  );
};

