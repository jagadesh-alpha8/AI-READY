import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { createBenchmarkEvidenceRule, deleteEvidenceRule, getBenchmarkEvidenceRules, listEvidenceTypes } from '../../api/benchmarks';
import type { BenchmarkEvidenceRules, EvidenceRule, EvidenceRuleInput, EvidenceTypeInfo } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';

/**
 * Stage 3.4: what evidence proves each maturity level of a benchmark.
 * A rule with no level applies to all three. Quick-start buttons only
 * pre-fill the form from the benchmark's evidence types -- nothing is
 * created until an expert saves it. The server refuses edits to a
 * non-draft benchmark and audits every change.
 */

const EMPTY: EvidenceRuleInput = {
  level: '', evidence_type: '', title: '', description: '', mandatory: true, minimum_count: 1,
  minimum_currency_months: '', scope_rule: '', validation_method: 'manual_review', privacy_classification: 'internal',
};

export const EvidenceRulesPanel: React.FC<{ code: string; benchmarkTypes: string[]; editable: boolean; onChanged: () => void }> = ({
  code, benchmarkTypes, editable, onChanged,
}) => {
  const rules = useApiResource<BenchmarkEvidenceRules>(() => getBenchmarkEvidenceRules(code), [code]);
  const types = useApiResource<EvidenceTypeInfo[]>(() => listEvidenceTypes(), []);
  const [form, setForm] = useState<EvidenceRuleInput | null>(null);
  const [err, setErr] = useState('');
  const set = (k: keyof EvidenceRuleInput, v: unknown) => setForm((f) => ({ ...(f || EMPTY), [k]: v }));
  const typeInfo = (c: string) => types.data?.find((t) => t.code === c);

  const start = (evCode = '') => {
    const t = typeInfo(evCode);
    setForm({ ...EMPTY, evidence_type: evCode, title: t ? t.name : '', description: t ? `Minimum validation: ${t.validation_method}` : '',
      privacy_classification: evCode === 'EV-05' || evCode === 'EV-04' ? 'confidential' : 'internal' });
  };
  const save = async () => {
    if (!form) return;
    setErr('');
    try {
      await createBenchmarkEvidenceRule(code, { ...form, minimum_currency_months: form.minimum_currency_months || null });
      setForm(null);
      rules.refetch();
      onChanged();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  const remove = async (r: EvidenceRule) => {
    if (!window.confirm(`Delete rule "${r.title}"?`)) return;
    setErr('');
    try { await deleteEvidenceRule(r.id); rules.refetch(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="glass-card p-4 space-y-3 text-xs">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm font-bold text-ink-900">Evidence rules</p>
        {rules.data && (
          <div className="flex gap-1.5">
            {(['L3', 'L2', 'L1'] as const).map((lv) => (
              <span key={lv} className={`badge ${rules.data!.level_coverage[lv] ? 'badge-success' : 'badge-warning'}`}>
                {lv}: {rules.data!.level_coverage[lv]} mandatory
              </span>
            ))}
          </div>
        )}
      </div>
      <p className="text-ink-500">What an institution must submit to prove each level. A rule without a level applies to all three.</p>

      {rules.loading && <LoadingState message="Loading rules…" />}
      {rules.error && <ErrorState message={rules.error} onRetry={rules.refetch} />}
      {rules.data && rules.data.benchmark_rules.length === 0 && <p className="text-ink-500">No rules yet.</p>}
      {(rules.data?.benchmark_rules || []).map((r) => (
        <div key={r.id} className="rounded-lg border border-line-200 bg-surface p-2 flex items-start gap-2">
          <span className="badge badge-neutral">{r.level || 'all levels'}</span>
          <div className="min-w-0 flex-1">
            <p className="text-ink-900"><span className="font-mono text-ink-500 mr-1">{r.evidence_type}</span>{r.title}
              {!r.mandatory && <span className="text-ink-500"> (optional)</span>}</p>
            <p className="text-ink-500">
              at least {r.minimum_count}{r.minimum_currency_months ? ` · not older than ${r.minimum_currency_months} months` : ''}
              {' '}· {r.validation_method_label} · {r.privacy_classification}{r.scope_rule ? ` · scope: ${r.scope_rule}` : ''}
            </p>
          </div>
          {editable && <button className="btn-secondary btn-sm" title="Delete" onClick={() => remove(r)}><Trash2 className="w-3.5 h-3.5" /></button>}
        </div>
      ))}
      {(rules.data?.requirement_rules || []).length > 0 && (
        <p className="text-ink-500">+ {rules.data!.requirement_rules.length} rule(s) on linked requirements.</p>
      )}

      {editable && !form && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-ink-500">Start from:</span>
          {benchmarkTypes.map((c) => (
            <button key={c} className="btn-secondary btn-sm" onClick={() => start(c)} title={typeInfo(c)?.examples}>
              <Plus className="w-3.5 h-3.5" /> {c} {typeInfo(c)?.name}
            </button>
          ))}
          <button className="btn-secondary btn-sm" onClick={() => start()}><Plus className="w-3.5 h-3.5" /> Blank rule</button>
        </div>
      )}

      {editable && form && (
        <div className="rounded-lg border border-brand-300 p-3 space-y-2">
          <div className="grid md:grid-cols-4 gap-2">
            <label className="space-y-1"><span className="text-ink-500">Level</span>
              <select className="input w-full text-xs" value={form.level} onChange={(e) => set('level', e.target.value)}>
                <option value="">All levels</option><option value="L3">L3</option><option value="L2">L2</option><option value="L1">L1</option>
              </select></label>
            <label className="space-y-1"><span className="text-ink-500">Evidence type</span>
              <select className="input w-full text-xs" value={form.evidence_type} onChange={(e) => set('evidence_type', e.target.value)}>
                <option value="">Choose…</option>
                {(types.data || []).map((t) => <option key={t.code} value={t.code}>{t.code} {t.name}</option>)}
              </select></label>
            <label className="space-y-1"><span className="text-ink-500">Minimum count</span>
              <input className="input w-full text-xs" type="number" min={1} max={100} value={form.minimum_count}
                onChange={(e) => set('minimum_count', e.target.value)} /></label>
            <label className="space-y-1"><span className="text-ink-500">Max age (months)</span>
              <input className="input w-full text-xs" type="number" min={1} max={120} value={form.minimum_currency_months ?? ''}
                placeholder="no limit" onChange={(e) => set('minimum_currency_months', e.target.value)} /></label>
          </div>
          <label className="block space-y-1"><span className="text-ink-500">Title</span>
            <input className="input w-full text-xs" value={form.title} onChange={(e) => set('title', e.target.value)} /></label>
          <label className="block space-y-1"><span className="text-ink-500">Description</span>
            <textarea className="input w-full text-xs" rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} /></label>
          <label className="block space-y-1"><span className="text-ink-500">Scope (units / programmes / period covered)</span>
            <input className="input w-full text-xs" value={form.scope_rule} onChange={(e) => set('scope_rule', e.target.value)} /></label>
          <div className="grid md:grid-cols-3 gap-2 items-end">
            <label className="space-y-1"><span className="text-ink-500">Validation</span>
              <select className="input w-full text-xs" value={form.validation_method} onChange={(e) => set('validation_method', e.target.value)}>
                <option value="manual_review">Manual review</option><option value="ai_assisted_review">AI-assisted review</option>
                <option value="auto_extract">Automatic extraction</option><option value="system_integration">System integration</option>
              </select></label>
            <label className="space-y-1"><span className="text-ink-500">Privacy</span>
              <select className="input w-full text-xs" value={form.privacy_classification} onChange={(e) => set('privacy_classification', e.target.value)}>
                <option value="public">Public</option><option value="internal">Internal</option>
                <option value="confidential">Confidential</option><option value="restricted">Restricted</option>
              </select></label>
            <label className="flex items-center gap-2 text-ink-700">
              <input type="checkbox" checked={!!form.mandatory} onChange={(e) => set('mandatory', e.target.checked)} /> Mandatory
            </label>
          </div>
          <div className="flex gap-2">
            <button className="btn-primary btn-sm" onClick={save}>Save rule</button>
            <button className="btn-secondary btn-sm" onClick={() => { setForm(null); setErr(''); }}>Cancel</button>
          </div>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};
