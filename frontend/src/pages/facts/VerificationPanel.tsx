import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';

import { getVerificationSummary, reverifySprint } from '../../api/facts';
import type { VerificationSummary } from '../../api/facts';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';

/**
 * Exception review: how much the verification rules take off reviewers' hands, and why the rest need a person
 * (grouped, highest risk and CRI weight first). In shadow mode the rules only record what they would do.
 */
export const VerificationPanel: React.FC<{ sprintId: string; canReview: boolean; onChanged: () => void }> = ({
  sprintId, canReview, onChanged,
}) => {
  const { data, refetch } = useApiResource<VerificationSummary>(() => getVerificationSummary(sprintId), [sprintId]);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  if (!data) return null;
  const w = data.workload;
  const shadow = data.mode === 'shadow';
  const tiles: [string, number, string][] = [
    ['Verified', w.outcomes.verified || 0, 'text-success'],
    ['Needs review', w.outcomes.needs_review || 0, 'text-warning'],
    ['Invalid', w.outcomes.invalid || 0, 'text-danger'],
    ['Conflicting', w.outcomes.conflicting || 0, 'text-danger'],
    [shadow ? 'Would auto-confirm' : 'Auto-confirmed', shadow ? w.would_auto_verify : w.auto_verified + w.auto_by_precedent,
      'text-ink-900'],
    ['Reviewer overrides', w.reviewer_overrides, w.reviewer_overrides ? 'text-danger' : 'text-ink-900'],
  ];
  const rerun = async () => {
    setBusy(true);
    setMessage('');
    try {
      const res = await reverifySprint(sprintId);
      setMessage(`Checked ${res.data.checked} unreviewed fact(s).`);
      refetch();
      onChanged();
    } catch (err) {
      setMessage(getErrorMessage(err, 'Verification could not be re-run.'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="glass-card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <ShieldCheck className="w-5 h-5 text-brand-700 mt-0.5" />
          <div>
            <h2 className="text-sm font-bold text-ink-900">Fact verification</h2>
            <p className="text-xs text-ink-500">
              {shadow
                ? 'Shadow mode: every fact is checked against its source and the rules record what they would do. Nothing is confirmed automatically yet.'
                : 'Rules active: facts that pass every check (and whose risk level allows it) are confirmed automatically; the rest are listed below.'}
            </p>
          </div>
        </div>
        {canReview && (
          <button className="btn-secondary btn-sm" onClick={rerun} disabled={busy}>
            {busy ? 'Checking…' : 'Re-check unreviewed facts'}
          </button>
        )}
      </div>
      {message && <p className="text-xs text-ink-600">{message}</p>}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {tiles.map(([label, value, cls]) => (
          <div key={label} className="panel-muted">
            <div className="text-[11px] uppercase tracking-wide text-ink-500">{label}</div>
            <div className={`text-lg font-bold tabular-nums ${cls}`}>{value}</div>
          </div>
        ))}
      </div>
      {data.groups.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-xs font-bold text-ink-700">Why facts need a person</h3>
          {data.groups.map((g) => (
            <div key={g.code} className="border border-line-200 rounded-md">
              <button type="button" className="w-full flex items-center justify-between px-3 py-1.5 text-left"
                onClick={() => setOpen(open === g.code ? null : g.code)}>
                <span className="text-xs font-semibold text-ink-800 flex items-center gap-1">
                  {open === g.code ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  {g.label}
                </span>
                <span className="text-xs text-ink-500 tabular-nums">
                  {g.count}{g.high_risk ? ` · ${g.high_risk} high risk` : ''}
                </span>
              </button>
              {open === g.code && (
                <ul className="px-3 pb-2 space-y-1">
                  {g.items.map((i) => (
                    <li key={i.fact_id} className="text-xs text-ink-600">
                      <span className="font-mono font-semibold text-brand-800">{i.field_key}</span>{' '}
                      <span className="font-mono">{JSON.stringify(i.value)}</span>
                      {i.risk_level ? <span className="text-ink-400"> · {i.risk_level} risk</span> : null}
                      <span className="block text-ink-500">{i.reason || 'Not verified yet.'}</span>
                    </li>
                  ))}
                  {g.count > g.items.length && <li className="text-xs text-ink-400">…and {g.count - g.items.length} more</li>}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
