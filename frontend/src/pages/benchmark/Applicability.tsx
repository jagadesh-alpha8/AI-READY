import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import {
  createApplicabilityRule, deleteApplicabilityRule, getApplicabilityReference, listApplicabilityRules,
  previewApplicability,
} from '../../api/benchmarks';
import type {
  ApplicabilityPreview, ApplicabilityReference, ApplicabilityResult, ApplicabilityRule, ApplicabilityRuleInput,
  InstitutionProfile,
} from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';
import { AiBadge } from './AiBadge';
import { getApplicabilityValidation } from '../../api/benchmarks';
import type { ApplicabilityValidation } from '../../api/benchmarks';

/**
 * Stage 3.5: which institutions a benchmark applies to.
 * - ApplicabilityRulesPanel: a benchmark's rules (Levels tab). Rules run in
 *   priority order; the first that matches decides; empty conditions match all.
 * - ApplicabilityPreviewTab: describe a college, see every benchmark's result + reason.
 * A benchmark with no rules shows "requires review", never "applies".
 */

export const RESULT_BADGE: Record<ApplicabilityResult, string> = {
  applies: 'badge-success',
  does_not_apply: 'badge-neutral',
  optional: 'badge-brand',
  requires_review: 'badge-warning',
};
const RESULT_LABEL: Record<ApplicabilityResult, string> = {
  applies: 'Applies', does_not_apply: 'Does not apply', optional: 'Optional', requires_review: 'Requires review',
};

const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

const ChipPicker: React.FC<{ label: string; options: { code: string; name: string }[]; value: string[]; onChange: (v: string[]) => void; hint?: string }> = ({
  label, options, value, onChange, hint,
}) => (
  <div className="space-y-1">
    <p className="text-ink-500">{label}{hint && <span className="text-ink-400"> — {hint}</span>}</p>
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={o.code} type="button" onClick={() => onChange(toggle(value, o.code))}
          className={`badge cursor-pointer ${value.includes(o.code) ? 'badge-brand' : 'badge-neutral'}`}>
          {o.name}
        </button>
      ))}
    </div>
  </div>
);

const EMPTY_RULE: ApplicabilityRuleInput = {
  result: 'applies', priority: 100, institution_types: [], autonomous_statuses: [], programme_types: [],
  approval_bodies: [], jurisdiction: 'India', reason: '',
};

export const ApplicabilityRulesPanel: React.FC<{ code: string; sourcePackText: string; editable: boolean; onChanged: () => void }> = ({
  code, sourcePackText, editable, onChanged,
}) => {
  const ref = useApiResource<ApplicabilityReference>(() => getApplicabilityReference(), []);
  const rules = useApiResource<ApplicabilityRule[]>(() => listApplicabilityRules(code), [code]);
  const [form, setForm] = useState<ApplicabilityRuleInput | null>(null);
  const [err, setErr] = useState('');
  const set = <K extends keyof ApplicabilityRuleInput>(k: K, v: ApplicabilityRuleInput[K]) => setForm((f) => ({ ...(f || EMPTY_RULE), [k]: v }));
  const name = (list: { code: string; name: string }[] | undefined, c: string) => list?.find((x) => x.code === c)?.name || c;

  const save = async () => {
    if (!form) return;
    setErr('');
    try { await createApplicabilityRule(code, form); setForm(null); rules.refetch(); onChanged(); }
    catch (e) { setErr(getErrorMessage(e)); }
  };
  const remove = async (r: ApplicabilityRule) => {
    if (!window.confirm('Delete this applicability rule?')) return;
    try { await deleteApplicabilityRule(r.id); rules.refetch(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };

  const describe = (r: ApplicabilityRule) => {
    const parts = [
      r.institution_types.length ? `type: ${r.institution_types.map((c) => name(ref.data?.institution_types, c)).join(' / ')}` : '',
      r.autonomous_statuses.length ? `status: ${r.autonomous_statuses.map((c) => name(ref.data?.autonomous_statuses, c)).join(' / ')}` : '',
      r.programme_types.length ? `offers: ${r.programme_types.map((c) => name(ref.data?.programme_types, c)).join(' / ')}` : '',
      r.approval_bodies.length ? `approval: ${r.approval_bodies.join(' / ')}` : '',
    ].filter(Boolean);
    return parts.length ? parts.join(' · ') : 'all institutions';
  };

  return (
    <div className="glass-card p-4 space-y-3 text-xs">
      <p className="text-sm font-bold text-ink-900">Applicability rules</p>
      <p className="text-ink-500">
        Which institutions this benchmark applies to. Rules run lowest priority number first; the first one that
        matches decides. Source Pack text (same for every benchmark, so not used): <em>{sourcePackText || '—'}</em>
      </p>
      <p className="text-ink-500">To test the saved rules against a college profile, use the <strong>Applicability Preview</strong> tab.</p>
      <ValidationSummary code={code} version={(rules.data || []).map((r) => `${r.id}:${r.priority}:${r.result}`).join('|')} />
      {rules.loading && <LoadingState message="Loading rules…" />}
      {rules.error && <ErrorState message={rules.error} onRetry={rules.refetch} />}
      {rules.data && rules.data.length === 0 && (
        <p className="text-warning">No rules yet — every college will see this benchmark as "requires review".</p>
      )}
      {(rules.data || []).map((r) => (
        <div key={r.id} className="rounded-lg border border-line-200 bg-surface p-2 flex items-start gap-2">
          <span className="badge badge-neutral" title="priority">#{r.priority}</span>
          <span className={`badge ${RESULT_BADGE[r.result]}`}>{RESULT_LABEL[r.result]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-ink-900">when {describe(r)} <AiBadge model={r.ai_model} /></p>
            {r.reason && <p className="text-ink-500">Reason: {r.reason}</p>}
          </div>
          {editable && <button className="btn-secondary btn-sm" title="Delete" onClick={() => remove(r)}><Trash2 className="w-3.5 h-3.5" /></button>}
        </div>
      ))}

      {editable && !form && (
        <button className="btn-secondary btn-sm" onClick={() => setForm({ ...EMPTY_RULE })}><Plus className="w-3.5 h-3.5" /> Add rule</button>
      )}
      {editable && form && ref.data && (
        <div className="rounded-lg border border-brand-300 p-3 space-y-3">
          <div className="grid md:grid-cols-[1fr_auto] gap-2 items-end">
            <label className="space-y-1"><span className="text-ink-500">Result</span>
              <select className="input w-full text-xs" value={form.result} onChange={(e) => set('result', e.target.value as ApplicabilityResult)}>
                {ref.data.results.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
              </select></label>
            <label className="space-y-1"><span className="text-ink-500">Priority</span>
              <input className="input w-24 text-xs" type="number" min={0} max={1000} value={form.priority}
                onChange={(e) => set('priority', Number(e.target.value))} /></label>
          </div>
          <ChipPicker label="Institution types" hint="none selected = any" options={ref.data.institution_types}
            value={form.institution_types} onChange={(v) => set('institution_types', v)} />
          <ChipPicker label="Status" hint="none = any" options={ref.data.autonomous_statuses}
            value={form.autonomous_statuses} onChange={(v) => set('autonomous_statuses', v)} />
          <ChipPicker label="Offers any of these programmes" hint="none = any" options={ref.data.programme_types}
            value={form.programme_types} onChange={(v) => set('programme_types', v)} />
          <ChipPicker label="Holds any of these approvals" hint="none = any"
            options={ref.data.approval_bodies.map((b) => ({ code: b, name: b }))}
            value={form.approval_bodies} onChange={(v) => set('approval_bodies', v)} />
          <label className="block space-y-1"><span className="text-ink-500">Reason shown to reviewers and colleges</span>
            <input className="input w-full text-xs" value={form.reason} placeholder="e.g. ITIs follow DGT assessment norms instead"
              onChange={(e) => set('reason', e.target.value)} /></label>
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

export const ApplicabilityPreviewTab: React.FC = () => {
  const ref = useApiResource<ApplicabilityReference>(() => getApplicabilityReference(), []);
  const [profile, setProfile] = useState<InstitutionProfile>({
    institution_type: 'engineering', autonomous_status: 'autonomous', programme_types: ['ug_engineering'],
    approval_bodies: ['AICTE', 'NAAC'], jurisdiction: 'India',
  });
  const [result, setResult] = useState<ApplicabilityPreview | null>(null);
  const [filter, setFilter] = useState<ApplicabilityResult | ''>('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const set = <K extends keyof InstitutionProfile>(k: K, v: InstitutionProfile[K]) => setProfile((p) => ({ ...p, [k]: v }));

  const run = async () => {
    setBusy(true); setErr('');
    try { setResult((await previewApplicability(profile)).data); } catch (e) { setErr(getErrorMessage(e)); } finally { setBusy(false); }
  };

  if (ref.loading) return <LoadingState message="Loading…" />;
  if (ref.error || !ref.data) return <ErrorState message={ref.error || 'Failed'} onRetry={ref.refetch} />;
  const rows = (result?.benchmarks || []).filter((b) => !filter || b.result === filter);

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h3 className="text-sm font-bold text-ink-900">Applicability Preview</h3>
        <p className="text-sm text-ink-500">
          Tests the saved applicability rules against an institution profile: describe a college and see which
          benchmarks apply to it, which need review and which don't, and why. Nothing is saved here. Benchmarks
          without rules show "requires review".
        </p>
        <p className="text-xs text-ink-500">
          To create or edit the rules, open <strong>Levels</strong>, choose a benchmark, and use its{' '}
          <strong>Applicability rules</strong> section.
        </p>
      </div>
      <div className="glass-card p-4 space-y-3 text-xs">
        <div className="grid md:grid-cols-2 gap-2">
          <label className="space-y-1"><span className="text-ink-500">Institution type</span>
            <select className="input w-full text-xs" value={profile.institution_type} onChange={(e) => set('institution_type', e.target.value)}>
              {ref.data.institution_types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            </select></label>
          <label className="space-y-1"><span className="text-ink-500">Status</span>
            <select className="input w-full text-xs" value={profile.autonomous_status} onChange={(e) => set('autonomous_status', e.target.value)}>
              <option value="">—</option>
              {ref.data.autonomous_statuses.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select></label>
        </div>
        <ChipPicker label="Programmes offered" options={ref.data.programme_types}
          value={profile.programme_types || []} onChange={(v) => set('programme_types', v)} />
        <ChipPicker label="Approvals held" options={ref.data.approval_bodies.map((b) => ({ code: b, name: b }))}
          value={profile.approval_bodies || []} onChange={(v) => set('approval_bodies', v)} />
        <button className="btn-primary btn-sm" disabled={busy} onClick={run}>{busy ? 'Checking…' : 'Show applicable benchmarks'}</button>
        {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      </div>

      {result && (
        <>
          <div className="flex flex-wrap gap-2 text-xs">
            <button className={`badge ${filter === '' ? 'badge-brand' : 'badge-neutral'}`} onClick={() => setFilter('')}>
              All {result.benchmarks.length}
            </button>
            {(Object.keys(RESULT_LABEL) as ApplicabilityResult[]).map((r) => (
              <button key={r} className={`badge ${filter === r ? 'badge-brand' : RESULT_BADGE[r]}`} onClick={() => setFilter(r)}>
                {RESULT_LABEL[r]}: {result.counts[r] || 0}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            {rows.map((b) => (
              <div key={b.benchmark_code} className="glass-card p-3 flex items-start gap-2 text-xs">
                <span className={`badge ${RESULT_BADGE[b.result]}`}>{RESULT_LABEL[b.result]}</span>
                <div className="min-w-0">
                  <p className="text-ink-900"><span className="font-mono text-ink-500 mr-1">{b.benchmark_code}</span>{b.title}</p>
                  <p className="text-ink-500">{b.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

/** The saved rules run against every supported institution profile (read-only). */
const ValidationSummary: React.FC<{ code: string; version: string }> = ({ code, version }) => {
  const v = useApiResource<ApplicabilityValidation>(() => getApplicabilityValidation(code), [code, version]);
  if (v.loading || !v.data) return null;
  const d = v.data;
  const byType = (x: Record<string, number>) => Object.entries(x).map(([t, n]) => `${t.replace(/_/g, ' ')} (${n})`).join(', ');
  return (
    <div className={`rounded-lg border p-2 space-y-1 ${!d.has_rules || d.issues.length ? 'border-warning-line bg-warning-bg' : 'border-line-200 bg-surface'}`}>
      <p className="font-bold text-ink-900">
        Validation summary{d.has_rules ? ` - ${d.profiles_checked} institution profiles checked (type x status x programme x approval body)` : ''}
      </p>
      {!d.has_rules && <p className="text-danger">No rules yet: every college sees this benchmark as "requires review". Required before release.</p>}
      {d.has_rules && (
        <>
          <p className="text-ink-700">
            Results: {Object.entries(d.by_result).map(([k, n]) => `${k.replace(/_/g, ' ')} ${n}`).join(' · ')}
          </p>
          {d.requires_review && (
            <p className="text-ink-700">
              <strong>{d.requires_review.count}</strong> profile(s) end as "requires review": {byType(d.requires_review.by_institution_type)}.
            </p>
          )}
          {d.unmatched && (
            <p className="text-ink-700">
              <strong>{d.unmatched.count}</strong> profile(s) match no rule, so the benchmark does not apply to them:{' '}
              {byType(d.unmatched.by_institution_type)}. Add a rule if any of them should be assessed.
            </p>
          )}
          {d.rules.filter((r) => r.note).map((r) => (
            <p key={r.id} className={r.decides === 0 ? 'text-danger' : 'text-ink-700'}>Rule #{r.priority} ({r.result.replace(/_/g, ' ')}): {r.note}.</p>
          ))}
          {d.issues.length === 0 && !d.requires_review && !d.unmatched && <p className="text-success">Every rule decides at least one profile and every profile is decided.</p>}
        </>
      )}
    </div>
  );
};

