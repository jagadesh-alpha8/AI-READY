import React from 'react';

import type { PillarScore } from '../../types';
import { factorNote, weightLabel, weightedTotal } from './scoreExplain.ts';

const STATUS_LABEL: Record<string, string> = {
  strong: 'Strong', developing: 'Developing', at_risk: 'At risk', not_started: 'Not started',
};
const STATUS_BADGE: Record<string, string> = {
  strong: 'badge-success', developing: 'badge-brand', at_risk: 'badge-warning', not_started: 'badge-neutral',
};

/**
 * The 9 AI-QIF factors behind the Raw CRI, as the score API returns them: each factor's score (0-100), its
 * weight, and its contribution (score x weight). The contributions add up to the Raw CRI.
 */
export const FactorBreakdown: React.FC<{ pillars: PillarScore[]; rawCri: number }> = ({ pillars, rawCri }) => {
  if (pillars.length === 0) {
    return <p className="text-xs text-ink-500">No factor scores yet. Recalculate the CRI once facts are reviewed.</p>;
  }
  const total = weightedTotal(pillars);
  return (
    <div className="space-y-2">
      {/* Wide screens: one table. */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink-500">
              <th className="py-1.5 pr-2 font-semibold">AI-QIF factor</th>
              <th className="py-1.5 px-2 font-semibold text-right">Score</th>
              <th className="py-1.5 px-2 font-semibold text-right">Weight</th>
              <th className="py-1.5 px-2 font-semibold text-right">Contribution</th>
              <th className="py-1.5 px-2 font-semibold text-right">Confidence</th>
              <th className="py-1.5 pl-2 font-semibold">Status · evidence</th>
            </tr>
          </thead>
          <tbody>
            {pillars.map((p) => (
              <tr key={p.pillar} className="border-t border-line-200 align-top">
                <td className="py-1.5 pr-2 font-semibold text-ink-900">{p.label || p.pillar}</td>
                <td className="py-1.5 px-2 text-right tabular-nums font-mono">{p.raw_score} / 100</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{weightLabel(p.weight)}</td>
                <td className="py-1.5 px-2 text-right tabular-nums font-semibold">{p.weighted_score}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{Math.round(p.confidence_score * 100)}%</td>
                <td className="py-1.5 pl-2">
                  <span className={STATUS_BADGE[p.status] || 'badge-neutral'}>{STATUS_LABEL[p.status] || p.status}</span>
                  <span className="block text-ink-500 mt-0.5">{factorNote(p)}</span>
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-line-300 font-bold">
              <td className="py-1.5 pr-2">Raw CRI (sum of contributions)</td>
              <td colSpan={2} />
              <td className="py-1.5 px-2 text-right tabular-nums">{total}</td>
              <td colSpan={2} className="py-1.5 pl-2 text-ink-500 font-normal">Reported Raw CRI: {rawCri}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Narrow screens: one card per factor. */}
      <div className="md:hidden space-y-2">
        {pillars.map((p) => (
          <div key={p.pillar} className="p-3 bg-surface rounded-xl border border-line-200 text-xs space-y-1">
            <div className="flex items-start justify-between gap-2">
              <span className="font-bold text-ink-900">{p.label || p.pillar}</span>
              <span className={STATUS_BADGE[p.status] || 'badge-neutral'}>{STATUS_LABEL[p.status] || p.status}</span>
            </div>
            <div className="w-full bg-line-200 h-1.5 rounded-full overflow-hidden">
              <div className="bg-brand-500 h-full rounded-full" style={{ width: `${Math.min(100, p.raw_score)}%` }} />
            </div>
            <p className="text-ink-700">
              Score <strong className="font-mono">{p.raw_score} / 100</strong> · weight {weightLabel(p.weight)} ·
              contribution <strong>{p.weighted_score}</strong> · confidence {Math.round(p.confidence_score * 100)}%
            </p>
            <p className="text-ink-500">{factorNote(p)}</p>
          </div>
        ))}
        <p className="text-xs font-bold text-ink-800">Raw CRI = sum of contributions = {total} (reported {rawCri})</p>
      </div>
    </div>
  );
};
