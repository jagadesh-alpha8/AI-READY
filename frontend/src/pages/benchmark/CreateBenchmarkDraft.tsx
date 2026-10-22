import React, { useMemo, useState } from 'react';
import { FilePlus2 } from 'lucide-react';

import { createCandidateBenchmarkDraft, getCandidateDraftOptions } from '../../api/benchmarks';
import type { BenchmarkCandidateInfo, CandidateDraftOptions } from '../../api/benchmarks';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';

/**
 * "Create benchmark draft" for an approved new-benchmark candidate (services/candidates.py
 * create_benchmark_draft). Staff choose the AI-QIF criterion and an existing capability and review the
 * title; the draft gets that criterion's next code and is otherwise empty -- levels, applicability,
 * evidence types, evidence rules and the owner are written in the usual Studio steps, never by AI.
 * Creating it twice returns the same draft.
 */
export const CreateBenchmarkDraft: React.FC<{
  candidate: BenchmarkCandidateInfo;
  onCreated: (benchmarkCode: string) => void;
  onCancel: () => void;
}> = ({ candidate, onCreated, onCancel }) => {
  const options = useApiResource<CandidateDraftOptions>(() => getCandidateDraftOptions(candidate.id), [candidate.id]);
  const [pillar, setPillar] = useState('');
  const [capability, setCapability] = useState('');
  const [title, setTitle] = useState(candidate.title);
  const [guidance, setGuidance] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const criterion = useMemo(() => options.data?.criteria.find((c) => c.code === pillar) || null, [options.data, pillar]);

  if (options.loading) return <LoadingState message="Loading the criteria…" />;
  if (options.error) return <ErrorState message={options.error} onRetry={options.refetch} />;
  const o = options.data;
  if (!o) return null;
  if (o.existing_benchmark) {
    return <p className="text-ink-600">The draft {o.existing_benchmark} was already created from this candidate.</p>;
  }
  if (!o.can_create) {
    return <p className="text-warning">Every required expert role must approve the candidate before its draft can be created.</p>;
  }
  if (o.criteria.length === 0) {
    return <p className="text-warning">No AI-QIF criteria are in the library yet; import the framework first.</p>;
  }

  const create = async () => {
    setSaving(true);
    setErr('');
    try {
      const res = await createCandidateBenchmarkDraft(candidate.id, {
        pillar_code: pillar, capability_code: capability, title, target_guidance: guidance || undefined,
      });
      if (res.data.benchmark_code) onCreated(res.data.benchmark_code);
    } catch (e) {
      setErr(getErrorMessage(e, 'The draft could not be created.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3 border border-brand-500/30 rounded-lg p-3" role="group" aria-label="Create benchmark draft">
      <p className="font-semibold text-ink-900">Create the benchmark draft</p>
      <div className="grid md:grid-cols-2 gap-2">
        <label className="space-y-1">
          <span className="font-semibold text-ink-700">AI-QIF criterion *</span>
          <select className="input text-xs w-full" value={pillar}
            onChange={(e) => { setPillar(e.target.value); setCapability(''); }}>
            <option value="">Choose a criterion…</option>
            {o.criteria.map((c) => <option key={c.code} value={c.code}>{c.code} {c.name}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="font-semibold text-ink-700">Existing capability *</span>
          <select className="input text-xs w-full" value={capability} disabled={!criterion}
            onChange={(e) => setCapability(e.target.value)}>
            <option value="">{criterion ? 'Choose a capability…' : 'Choose a criterion first'}</option>
            {(criterion?.capabilities || []).map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
          </select>
        </label>
      </div>
      {criterion && (
        <p className="text-ink-600">
          New code: <strong className="font-mono text-brand-800">{criterion.next_code}</strong>
          {' '}· kind {o.benchmark_kind_label.toLowerCase()} (as approved) · framework {o.framework} · status draft
        </p>
      )}
      {o.benchmark_kind !== 'proposed' && (
        <p className="text-warning">
          This candidate was approved as a {o.benchmark_kind_label.toLowerCase()} benchmark, so readiness will also
          require a primary link to an approved source requirement. A proposed benchmark does not need one.
        </p>
      )}
      <label className="block space-y-1">
        <span className="font-semibold text-ink-700">Title *</span>
        <input className="input text-xs w-full" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <div className="space-y-1">
        <span className="font-semibold text-ink-700">Source rationale (kept as the draft's provenance)</span>
        <pre className="whitespace-pre-wrap font-sans text-ink-700 bg-surface rounded-lg border border-line-200 p-2">
          {o.source_rationale}{o.source_code ? `\nSource: ${o.source_code}` : ''}
        </pre>
      </div>
      <label className="block space-y-1">
        <span className="font-semibold text-ink-700">Target guidance (optional)</span>
        <textarea className="input text-xs w-full" rows={2} value={guidance} onChange={(e) => setGuidance(e.target.value)} />
      </label>
      <p className="text-ink-500">
        The draft starts empty: write L3/L2/L1, applicability, evidence types, evidence rules and the expert owner in
        Levels. It then needs the readiness checks and a reviewer's confirmation before it can go into a release, and
        this candidate is marked published only when that release is published.
      </p>
      <div className="flex gap-2">
        <button className="btn-primary btn-sm" disabled={saving || !pillar || !capability || !title.trim()} onClick={create}>
          <FilePlus2 className="w-3.5 h-3.5" /> {saving ? 'Creating…' : 'Create draft'}
        </button>
        <button className="btn-secondary btn-sm" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};
