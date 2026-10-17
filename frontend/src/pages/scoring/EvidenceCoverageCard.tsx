import React from 'react';
import type { EvidenceCoverage } from '../../types';

const APPLICABILITY_LABEL: Record<string, string> = {
  applies: 'Applies',
  optional: 'Optional',
  requires_review: 'Unresolved',
  does_not_apply: 'Not applicable',
};

/**
 * Raw CRI, coverage-adjusted CRI and AI-QIF evidence coverage, shown apart (formula AIQIF-COV-1,
 * backend apps/scoring/services/coverage.py). `coverage` is the frozen block of one ScoringRun;
 * an empty object means the run was made before coverage existed.
 */
export const EvidenceCoverageCard: React.FC<{
  rawCri: number;
  adjustedCri: number | null | undefined;
  coverage: EvidenceCoverage | Record<string, never> | null | undefined;
  /** Shown when the run has no coverage, e.g. "Recalculate to see it." */
  missingHint?: string;
  /** False where the page already shows the Raw CRI prominently. */
  showRaw?: boolean;
}> = ({ rawCri, adjustedCri, coverage, missingHint, showRaw = true }) => {
  if (!coverage || !('formula_version' in coverage)) {
    return (
      <div className="glass-card p-4 text-sm text-ink-600">
        AI-QIF evidence coverage was not calculated for this score. {missingHint}
      </div>
    );
  }
  const c = coverage as EvidenceCoverage;
  const labels: string[] = [];
  if (c.status !== 'complete') labels.push('Coverage incomplete');
  if (c.unresolved_applicability_count > 0) labels.push(`Applicability unresolved for ${c.unresolved_applicability_count}`);

  return (
    <div className="glass-card p-5 sm:p-6 space-y-4">
      <div className={`grid grid-cols-1 gap-4 ${showRaw ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        {showRaw && (
          <div className="p-4 bg-surface rounded-xl border border-line-200 text-center">
            <span className="text-xs font-bold text-ink-600 uppercase tracking-wide">Raw CRI</span>
            <div className="text-3xl font-bold text-ink-900 my-1 tabular-nums">{rawCri.toFixed(1)}</div>
            <span className="text-xs text-ink-500">From reviewed facts and open gaps</span>
          </div>
        )}
        <div className="p-4 bg-surface rounded-xl border border-line-200 text-center">
          <span className="text-xs font-bold text-brand-800 uppercase tracking-wide">Coverage-adjusted CRI</span>
          <div className="text-3xl font-bold text-brand-800 my-1 tabular-nums">
            {adjustedCri == null ? '—' : adjustedCri.toFixed(1)}
          </div>
          <span className="text-xs text-ink-500">Raw CRI × evidence coverage</span>
        </div>
        <div className="p-4 bg-surface rounded-xl border border-line-200 text-center">
          <span className="text-xs font-bold text-accent uppercase tracking-wide">AI-QIF evidence coverage</span>
          <div className="text-3xl font-bold text-accent my-1 tabular-nums">
            {c.ratio == null ? '—' : `${Math.round(c.ratio * 100)}%`}
          </div>
          <span className="text-xs text-ink-700 font-semibold">
            {c.covered_count} of {c.applicable_count} applicable indicators covered
          </span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {labels.map((l) => <span key={l} className="badge-warning">{l}</span>)}
        {c.status === 'complete' && <span className="badge-success">Coverage complete</span>}
        {c.excluded_count > 0 && <span className="badge-neutral">{c.excluded_count} not applicable (excluded)</span>}
        {c.mappings_awaiting_review > 0 && (
          <span className="badge-neutral" title="AI-QIF tags on confirmed facts that no reviewer has confirmed yet (Facts Review).">
            {c.mappings_awaiting_review} tag{c.mappings_awaiting_review === 1 ? '' : 's'} awaiting reviewer confirmation
          </span>
        )}
      </div>

      <div className="text-xs text-ink-500 space-y-1">
        <p>
          An indicator counts as covered only when a reviewer has confirmed its AI-QIF tag on a confirmed or corrected
          fact. Only indicators the published release rules say do not apply are excluded; unresolved ones stay in.
        </p>
        <p>Weights: {c.weights_note}</p>
        {c.applicability_note && <p>{c.applicability_note}</p>}
        <p className="font-mono">{c.formula_version}: {c.formula}{c.release_label ? ` · release ${c.release_label}` : ''}</p>
      </div>

      <details>
        <summary className="cursor-pointer text-xs font-bold text-ink-700">Indicators ({c.indicators.length})</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-ink-500">
                <th className="py-1 pr-2">Indicator</th>
                <th className="py-1 pr-2">Applicability</th>
                <th className="py-1 pr-2 text-right">Weight</th>
                <th className="py-1">Covered</th>
              </tr>
            </thead>
            <tbody>
              {c.indicators.map((r) => (
                <tr key={r.code} className="border-t border-line-200">
                  <td className="py-1 pr-2"><span className="font-mono font-bold">{r.code.replace(/^AIQIF-/, '')}</span> {r.name}</td>
                  <td className="py-1 pr-2" title={r.applicability_reason}>{APPLICABILITY_LABEL[r.applicability] || r.applicability}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">{Number(r.weight.toFixed(4))}</td>
                  <td className="py-1">
                    {!r.applicable ? '—' : r.covered
                      ? <span className="text-success font-semibold">Yes ({r.fact_ids.length} fact{r.fact_ids.length === 1 ? '' : 's'})</span>
                      : <span className="text-warning">No</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
};
