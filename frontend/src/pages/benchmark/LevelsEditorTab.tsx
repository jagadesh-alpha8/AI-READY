import React, { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Clock, Save } from 'lucide-react';

import {
  getBenchmark, getHistory, getReadiness, listCatalogue, saveLevel, updateBenchmark,
} from '../../api/benchmarks';
import type { CatalogueBenchmark, EditableLevel, HistoryEntry, Readiness } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';
import { EvidenceRulesPanel } from './EvidenceRulesPanel';
import { ApplicabilityRulesPanel } from './Applicability';

/**
 * Stage 3.3: experts write each benchmark's real L3 / L2 / L1 levels.
 * The server refuses the Source Pack template text, identical levels and
 * edits to a non-draft benchmark; every save is in History.
 */

type LevelKey = 'L3' | 'L2' | 'L1';
const LEVELS: LevelKey[] = ['L3', 'L2', 'L1'];
const LISTS: { key: keyof Pick<EditableLevel, 'observable_requirements' | 'minimum_evidence' | 'outcome_expectations' | 'non_examples'>; label: string; hint: string }[] = [
  { key: 'observable_requirements', label: 'Observable requirements', hint: 'What a reviewer can see in place' },
  { key: 'minimum_evidence', label: 'Minimum evidence', hint: 'Documents / data that prove it' },
  { key: 'outcome_expectations', label: 'Outcome expectations', hint: 'The result it should produce' },
  { key: 'non_examples', label: 'Non-examples', hint: 'What does NOT count for this level' },
];

const toLines = (items: string[]) => items.join('\n');
const fromLines = (text: string) => text.split('\n').map((s) => s.trim()).filter(Boolean);

export const LevelsEditorTab: React.FC<{ code: string | null; onCode: (code: string) => void }> = ({ code, onCode }) => {
  const catalogue = useApiResource<CatalogueBenchmark[]>(() => listCatalogue(), []);
  const selected = code || catalogue.data?.[0]?.benchmark_code || null;

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Write what each maturity level means for this benchmark: L3 foundational, L2 operating, L1 advanced.
        Saved levels replace the Source Pack placeholders; the template text itself is refused.
      </p>
      {catalogue.loading && <LoadingState message="Loading catalogue…" />}
      {catalogue.error && <ErrorState message={catalogue.error} onRetry={catalogue.refetch} />}
      {catalogue.data && (
        <select className="input w-full" value={selected || ''} onChange={(e) => onCode(e.target.value)}>
          {catalogue.data.map((b) => (
            <option key={b.benchmark_code} value={b.benchmark_code}>
              {b.levels_defined ? '✓ ' : '○ '}{b.benchmark_code} — {b.title} ({b.pillar_code}, {b.kind_label})
            </option>
          ))}
        </select>
      )}
      {selected && <BenchmarkEditor key={selected} code={selected} onSaved={catalogue.refetch} />}
    </div>
  );
};

const BenchmarkEditor: React.FC<{ code: string; onSaved: () => void }> = ({ code, onSaved }) => {
  const bench = useApiResource(() => getBenchmark(code), [code]);
  const readiness = useApiResource<Readiness>(() => getReadiness(code), [code]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const refreshAll = () => { bench.refetch(); readiness.refetch(); onSaved(); };

  if (bench.loading) return <LoadingState message="Loading benchmark…" />;
  if (bench.error || !bench.data) return <ErrorState message={bench.error || 'Not found'} onRetry={bench.refetch} />;
  const b = bench.data;
  const editable = b.status === 'draft';

  return (
    <div className="space-y-4">
      <div className="glass-card p-4 space-y-2 text-xs">
        <h3 className="text-sm font-bold text-ink-900">
          <span className="font-mono text-ink-500 mr-2">{b.benchmark_code}</span>{b.title}
        </h3>
        <p className="text-ink-600">{b.capability}</p>
        <p className="text-ink-500">{b.pillar_code} {b.pillar_name} · {b.kind_label} · source basis: {b.source_basis || '—'} · applies to: {b.applicability || '—'}</p>
        {!editable && <p className="text-warning">This benchmark is {b.status}; levels can only change in a new draft.</p>}
        <OwnerFields code={code} owner={b.expert_owner} guidance={b.target_guidance} editable={editable} onSaved={refreshAll} />
      </div>

      <div className="grid lg:grid-cols-3 gap-3">
        {LEVELS.map((lv) => {
          const level = b.maturity_levels.find((m) => m.level === lv);
          return level ? (
            <LevelCard key={lv} code={code} level={level as EditableLevel} editable={editable} onSaved={refreshAll} />
          ) : null;
        })}
      </div>

      <EvidenceRulesPanel code={code} benchmarkTypes={b.evidence_types} editable={editable} onChanged={refreshAll} />

      <ApplicabilityRulesPanel code={code} sourcePackText={b.applicability} editable={editable} onChanged={refreshAll} />

      {readiness.data && <ReadinessPanel readiness={readiness.data} />}

      <button className="btn-secondary btn-sm" onClick={() => setHistoryOpen(!historyOpen)}>
        <Clock className="w-3.5 h-3.5" /> {historyOpen ? 'Hide history' : 'Show history'}
      </button>
      {historyOpen && <HistoryList code={code} />}
    </div>
  );
};

const OwnerFields: React.FC<{ code: string; owner: string; guidance: string; editable: boolean; onSaved: () => void }> = ({
  code, owner, guidance, editable, onSaved,
}) => {
  const [o, setO] = useState(owner);
  const [g, setG] = useState(guidance);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  useEffect(() => { setO(owner); setG(guidance); }, [owner, guidance]);
  const dirty = o !== owner || g !== guidance;
  const save = async () => {
    setErr(''); setMsg('');
    try {
      await updateBenchmark(code, { expert_owner: o, target_guidance: g });
      setMsg('Saved.');
      onSaved();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <div className="grid md:grid-cols-[1fr_2fr_auto] gap-2 items-end">
      <label className="space-y-1"><span className="text-ink-500">Expert owner</span>
        <input className="input w-full text-xs" value={o} disabled={!editable} placeholder="Name of the accountable expert"
          onChange={(e) => setO(e.target.value)} /></label>
      <label className="space-y-1"><span className="text-ink-500">Target guidance</span>
        <input className="input w-full text-xs" value={g} disabled={!editable} placeholder="Recommended target level and why"
          onChange={(e) => setG(e.target.value)} /></label>
      <button className="btn-secondary btn-sm" disabled={!editable || !dirty} onClick={save}><Save className="w-3.5 h-3.5" /> Save</button>
      {msg && <p className="text-success md:col-span-3">{msg}</p>}
      {err && <div className="md:col-span-3"><InlineError message={err} onDismiss={() => setErr('')} /></div>}
    </div>
  );
};

const LevelCard: React.FC<{ code: string; level: EditableLevel; editable: boolean; onSaved: () => void }> = ({
  code, level, editable, onSaved,
}) => {
  const initial = () => ({
    definition: level.is_placeholder ? '' : level.definition,
    measurement_rule: level.measurement_rule,
    requires_manual_review: level.requires_manual_review,
    ...Object.fromEntries(LISTS.map((l) => [l.key, toLines(level[l.key])])),
  }) as Record<string, any>;
  const [form, setForm] = useState<Record<string, any>>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setBusy(true); setErr(''); setMsg('');
    try {
      await saveLevel(code, level.level, {
        definition: form.definition, measurement_rule: form.measurement_rule,
        requires_manual_review: form.requires_manual_review,
        ...Object.fromEntries(LISTS.map((l) => [l.key, fromLines(form[l.key])])),
      });
      setMsg('Saved.');
      onSaved();
    } catch (e) { setErr(getErrorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <div className="glass-card p-4 space-y-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-bold text-ink-900">{level.level_label}</p>
        {level.is_placeholder
          ? <span className="badge badge-warning">placeholder</span>
          : <span className="badge badge-success">written</span>}
      </div>
      {level.is_placeholder && (
        <p className="text-ink-500 italic" title="Source Pack template text">Template: {level.definition}</p>
      )}
      <label className="block space-y-1"><span className="text-ink-500">Definition (specific to this benchmark)</span>
        <textarea className="input w-full text-xs" rows={4} disabled={!editable} value={form.definition}
          onChange={(e) => set('definition', e.target.value)} /></label>
      <label className="block space-y-1"><span className="text-ink-500">Measurement rule</span>
        <input className="input w-full text-xs" disabled={!editable} value={form.measurement_rule}
          placeholder="How a reviewer decides this level is met" onChange={(e) => set('measurement_rule', e.target.value)} /></label>
      {LISTS.map((l) => (
        <label key={l.key} className="block space-y-1"><span className="text-ink-500">{l.label} <span className="text-ink-400">— {l.hint}, one per line</span></span>
          <textarea className="input w-full text-xs" rows={2} disabled={!editable} value={form[l.key]}
            onChange={(e) => set(l.key, e.target.value)} /></label>
      ))}
      <label className="flex items-center gap-2 text-ink-700">
        <input type="checkbox" disabled={!editable} checked={!!form.requires_manual_review}
          onChange={(e) => set('requires_manual_review', e.target.checked)} /> Requires manual review
      </label>
      <div className="flex items-center gap-2">
        <button className="btn-primary btn-sm" disabled={!editable || busy} onClick={save}>
          <Save className="w-3.5 h-3.5" /> {busy ? 'Saving…' : `Save ${level.level}`}
        </button>
        {level.edited_by && <span className="text-ink-500">Last edit: {level.edited_by}</span>}
      </div>
      {msg && <p className="text-success">{msg}</p>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const ReadinessPanel: React.FC<{ readiness: Readiness }> = ({ readiness }) => (
  <div className="glass-card p-4 space-y-2 text-xs">
    <p className="text-sm font-bold text-ink-900">
      Release readiness {readiness.ready_for_review
        ? <span className="badge badge-success ml-2">required items done</span>
        : <span className="badge badge-warning ml-2">not ready</span>}
    </p>
    {readiness.checks.map((c) => (
      <div key={c.key} className="flex items-start gap-2">
        {c.ok ? <CheckCircle2 className="w-4 h-4 text-success shrink-0" /> : <Circle className="w-4 h-4 text-ink-400 shrink-0" />}
        <span className="text-ink-900">{c.label}</span>
        <span className={`badge ${c.severity === 'required' ? 'badge-brand' : 'badge-neutral'}`}>{c.severity}</span>
        <span className="text-ink-500">{c.detail}</span>
      </div>
    ))}
  </div>
);

const HistoryList: React.FC<{ code: string }> = ({ code }) => {
  const { data, loading, error, refetch } = useApiResource<HistoryEntry[]>(() => getHistory(code), [code]);
  if (loading) return <LoadingState message="Loading history…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  return (
    <div className="space-y-1 text-xs">
      {(data || []).map((h, i) => (
        <div key={i} className="rounded-lg border border-line-200 bg-surface p-2">
          <span className="text-ink-500">{new Date(h.at).toLocaleString()}</span> · <span className="text-ink-900">{h.actor}</span> ·{' '}
          <span className="font-mono">{h.action}</span>
          {h.after && typeof h.after === 'object' && 'level' in h.after && <span className="text-ink-500"> · {String(h.after.level)}</span>}
        </div>
      ))}
      {data && data.length === 0 && <p className="text-ink-500">No edits yet.</p>}
    </div>
  );
};
