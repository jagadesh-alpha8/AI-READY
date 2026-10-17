import React, { useMemo, useState } from 'react';
import { Download } from 'lucide-react';

import { getPlatformAIUsage } from '../../api/extraction';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import type { PlatformAIUsage } from '../../types';

/**
 * Admin / Settings -> AI Usage & Billing (super admin and InGage consultant).
 *
 * Real AI tokens and cost recorded for every AI call during extraction
 * (backend: apps.extraction.models.AIUsage), per college x sprint x month --
 * the numbers to bill universities from. Same figures as
 * `manage.py ai_usage_report` on the server.
 */

type Period = 'this_month' | 'last_month' | 'all' | 'custom';

const iso = (d: Date) => d.toISOString().slice(0, 10);

function periodRange(period: Period, custom: { since: string; until: string }) {
  const now = new Date();
  if (period === 'this_month') {
    return { since: iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1))), until: undefined };
  }
  if (period === 'last_month') {
    return {
      since: iso(new Date(Date.UTC(now.getFullYear(), now.getMonth() - 1, 1))),
      until: iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 0))),
    };
  }
  if (period === 'custom') return { since: custom.since || undefined, until: custom.until || undefined };
  return { since: undefined, until: undefined };
}

const formatTokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : String(n);
const formatUsd = (value: string) => {
  const n = Number(value);
  return `$${n >= 1 ? n.toFixed(2) : n.toFixed(3)}`;
};

const STAGE_LABELS: Record<string, string> = {
  classification: 'Classification',
  // One request that classified the document and extracted its first chunk's facts; tokens are not split.
  document_analysis: 'Document analysis (classification + facts)',
  fact_extraction: 'Fact extraction',
  conflict_check: 'Conflict check',
  other: 'Other',
};

export const AIUsageTab: React.FC = () => {
  const [period, setPeriod] = useState<Period>('this_month');
  const [custom, setCustom] = useState({ since: '', until: '' });
  const [college, setCollege] = useState('');
  const range = periodRange(period, custom);

  const { data, loading, error, refetch } = useApiResource<PlatformAIUsage>(
    () => getPlatformAIUsage(range),
    [range.since, range.until],
  );

  const colleges = useMemo(
    () => [...new Set((data?.rows || []).map((r) => r.institution))].sort(),
    [data],
  );
  const rows = (data?.rows || []).filter((r) => !college || r.institution === college);
  const shown = rows.reduce(
    (acc, r) => ({
      calls: acc.calls + r.calls,
      input: acc.input + r.input_tokens,
      output: acc.output + r.output_tokens,
      cost: acc.cost + Number(r.cost_usd),
      unpriced: acc.unpriced + r.unpriced_calls,
      imported: acc.imported + r.imported_calls + r.estimated_calls,
    }),
    { calls: 0, input: 0, output: 0, cost: 0, unpriced: 0, imported: 0 },
  );

  const downloadCsv = () => {
    const header = ['College', 'Sprint', 'Month', 'Documents', 'AI calls', 'Input tokens', 'Output tokens', 'Cost (USD)', 'Unpriced calls', 'Imported calls', 'Estimated calls'];
    const lines = rows.map((r) => [r.institution, r.sprint, r.month, r.documents, r.calls, r.input_tokens, r.output_tokens, r.cost_usd, r.unpriced_calls, r.imported_calls, r.estimated_calls]);
    const csv = [header, ...lines]
      .map((cells) => cells.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `ai-usage_${range.since || 'all'}_${range.until || 'now'}${college ? `_${college}` : ''}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="glass-card p-5 flex flex-wrap items-end gap-3">
        <label className="text-xs text-ink-500 flex flex-col gap-1">
          Period
          <select value={period} onChange={(e) => setPeriod(e.target.value as Period)} className="input py-2 text-sm w-auto">
            <option value="this_month">This month</option>
            <option value="last_month">Last month</option>
            <option value="all">All time</option>
            <option value="custom">Custom dates</option>
          </select>
        </label>
        {period === 'custom' && (
          <>
            <label className="text-xs text-ink-500 flex flex-col gap-1">
              From
              <input type="date" value={custom.since} onChange={(e) => setCustom({ ...custom, since: e.target.value })} className="input py-2 text-sm" />
            </label>
            <label className="text-xs text-ink-500 flex flex-col gap-1">
              To
              <input type="date" value={custom.until} onChange={(e) => setCustom({ ...custom, until: e.target.value })} className="input py-2 text-sm" />
            </label>
          </>
        )}
        <label className="text-xs text-ink-500 flex flex-col gap-1">
          College
          <select value={college} onChange={(e) => setCollege(e.target.value)} className="input py-2 text-sm w-auto max-w-[260px]">
            <option value="">All colleges</option>
            {colleges.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <button onClick={downloadCsv} disabled={rows.length === 0} className="btn-secondary btn-sm ml-auto">
          <Download className="w-4 h-4" />
          <span>Download CSV</span>
        </button>
      </div>

      {loading && <LoadingState message="Loading AI usage…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              ['AI cost', `$${shown.cost.toFixed(2)}`],
              ['Input tokens', formatTokens(shown.input)],
              ['Output tokens', formatTokens(shown.output)],
              ['AI calls', shown.calls.toLocaleString()],
            ].map(([label, value]) => (
              <div key={label} className="glass-card p-5">
                <p className="text-xs text-ink-500">{label}</p>
                <p className="text-2xl font-bold text-ink-900 mt-1 tabular-nums">{value}</p>
              </div>
            ))}
          </div>

          {!college && data.by_stage.length > 0 && (
            <p className="text-xs text-ink-500 flex flex-wrap gap-x-4 gap-y-1">
              {data.by_stage.map((s) => (
                <span key={s.stage}>{STAGE_LABELS[s.stage] || s.stage}: {formatUsd(s.cost_usd)}</span>
              ))}
              <span>Models: {data.by_model.map((m) => m.model).join(', ')}</span>
            </p>
          )}

          {shown.imported > 0 && (
            <p className="text-xs text-info">
              Rows marked <span className="badge-neutral">imported</span> are totals copied from a provider
              dashboard (or estimated) for usage before automatic recording started: exact for the period, but not
              split per document.
              {data.notes.length > 0 && ` Source: ${data.notes.join(' | ')}`}
            </p>
          )}

          {shown.unpriced > 0 && (
            <p className="text-xs text-warning">
              {shown.unpriced} AI call{shown.unpriced === 1 ? '' : 's'} used a model with no configured price
              {data.unpriced_models.length > 0 && ` (${data.unpriced_models.join(', ')})`}, so the cost shown is
              incomplete. Set its price with AI_PRICING_JSON in the server's .env.
            </p>
          )}

          {rows.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No AI usage recorded for this period.</p>
            </div>
          ) : (
            <div className="table-shell table-scroll">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>College</th>
                    <th>Sprint</th>
                    <th>Month</th>
                    <th className="text-right">Documents</th>
                    <th className="text-right">AI calls</th>
                    <th className="text-right">Input tokens</th>
                    <th className="text-right">Output tokens</th>
                    <th className="text-right">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.institution_id}-${r.sprint_id}-${r.month}`}>
                      <td className="font-semibold text-ink-900">{r.institution}</td>
                      <td className="text-ink-600">
                        {r.sprint}
                        {r.imported_calls + r.estimated_calls > 0 && (
                          <span className="badge-neutral ml-2">{r.estimated_calls > 0 && !r.imported_calls ? 'estimated' : 'imported'}</span>
                        )}
                      </td>
                      <td className="text-ink-600 tabular-nums">{r.month}</td>
                      <td className="text-right tabular-nums">{r.documents || '—'}</td>
                      <td className="text-right tabular-nums">{r.calls.toLocaleString()}</td>
                      <td className="text-right tabular-nums">{r.input_tokens.toLocaleString()}</td>
                      <td className="text-right tabular-nums">{r.output_tokens.toLocaleString()}</td>
                      <td className="text-right font-semibold text-ink-900 tabular-nums" title={`$${r.cost_usd}`}>
                        {formatUsd(r.cost_usd)}
                        {r.unpriced_calls > 0 && <span className="text-warning"> *</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-ink-500">
            Costs are what the AI provider charges at list price (USD), recorded at the time of each call. Server,
            storage and search costs are not included.
          </p>
        </>
      )}
    </div>
  );
};
