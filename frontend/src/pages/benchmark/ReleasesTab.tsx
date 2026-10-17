import React, { useState } from 'react';
import { CheckCircle2, Lock, Plus, Send, Trash2, Undo2 } from 'lucide-react';

import {
  addReleaseItem, createRelease, getRelease, getReleaseDiff, listCatalogue, listReleases, releaseAction,
  removeReleaseItem, setReleaseRequiresComposite,
} from '../../api/benchmarks';
import type {
  BenchmarkReleaseInfo, CatalogueBenchmark, ReleaseDetail, ReleaseDiffRow, ReleaseEligibilityRow, ReleaseStatus,
} from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';

/**
 * Stage 3.6: Benchmark releases. draft -> review -> approved -> published (-> retired).
 * The server enforces every rule: readiness before review, approver != submitter,
 * benchmarks frozen while in review, snapshots + hashes frozen on publish, and
 * only the current published release is used for new scorecards.
 */

const STATUS_BADGE: Record<ReleaseStatus, string> = {
  draft: 'badge-neutral', review: 'badge-warning', approved: 'badge-brand', published: 'badge-success', retired: 'badge-neutral',
};
const CHANGE_BADGE: Record<string, string> = {
  added: 'badge-success', updated: 'badge-brand', retired: 'badge-danger', unchanged: 'badge-neutral',
};

export const ReleasesTab: React.FC = () => {
  const list = useApiResource<BenchmarkReleaseInfo[]>(() => listReleases(), []);
  const [open, setOpen] = useState<string | null>(null);
  const [label, setLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [prefill, setPrefill] = useState(true);
  const [needsComposite, setNeedsComposite] = useState(false);
  const [err, setErr] = useState('');
  const inProgress = (list.data || []).find((r) => !['published', 'retired'].includes(r.status));

  const create = async () => {
    setErr('');
    try {
      const r = await createRelease({ release_label: label, release_notes: notes, prefill, requires_composite: needsComposite });
      setLabel(''); setNotes(''); list.refetch(); setOpen(r.data.release_label);
    } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        A release is a complete, approved set of benchmarks. Only the current published release is used for new
        college scorecards; publishing freezes every benchmark in it, and older releases are kept unchanged.
      </p>
      {list.loading && <LoadingState message="Loading releases…" />}
      {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}

      <div className="space-y-2">
        {(list.data || []).map((r) => (
          <button key={r.id} onClick={() => setOpen(open === r.release_label ? null : r.release_label)}
            className={`glass-card w-full p-3 text-left text-xs flex items-center gap-2 flex-wrap ${open === r.release_label ? 'ring-2 ring-brand-500' : ''}`}>
            <span className="text-sm font-bold text-ink-900">{r.release_label}</span>
            <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status === 'published' ? 'published — current' : r.status}</span>
            <span className="text-ink-500">{r.item_count} benchmark(s){r.based_on ? ` · based on ${r.based_on}` : ''}</span>
            {r.content_hash && <span className="font-mono text-ink-400" title={r.content_hash}>#{r.content_hash.slice(0, 10)}</span>}
          </button>
        ))}
        {list.data && list.data.length === 0 && <p className="text-sm text-ink-500">No releases yet.</p>}
      </div>

      {!inProgress && (
        <div className="glass-card p-4 space-y-2 text-xs">
          <p className="text-sm font-bold text-ink-900">Start a new release</p>
          <div className="grid md:grid-cols-[1fr_2fr_auto] gap-2">
            <input className="input text-xs" placeholder="Release label, e.g. Release 1.0" value={label} onChange={(e) => setLabel(e.target.value)} />
            <input className="input text-xs" placeholder="Release notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
            <button className="btn-primary btn-sm" disabled={!label.trim()} onClick={create}><Plus className="w-3.5 h-3.5" /> Create</button>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            <label className="flex items-center gap-1.5 text-ink-700">
              <input type="checkbox" checked={prefill} onChange={(e) => setPrefill(e.target.checked)} />
              Include all ready draft benchmarks
            </label>
            <label className="flex items-center gap-1.5 text-ink-700">
              <input type="checkbox" checked={needsComposite} onChange={(e) => setNeedsComposite(e.target.checked)} />
              Assessments need a composite score (every benchmark must have approved scoring weights)
            </label>
          </div>
          <p className="text-ink-500">
            A later release starts with every benchmark of the current release, marked unchanged. "Include all ready"
            adds every draft benchmark whose required checks pass (including a reviewer's confirmation); the others are
            listed with what they still need.
          </p>
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      {open && <ReleasePanel key={open} label={open} onChanged={list.refetch} />}
    </div>
  );
};

const ReleasePanel: React.FC<{ label: string; onChanged: () => void }> = ({ label, onChanged }) => {
  const rel = useApiResource<ReleaseDetail>(() => getRelease(label), [label]);
  const catalogue = useApiResource<CatalogueBenchmark[]>(() => listCatalogue(), []);
  const [pick, setPick] = useState('');
  const [impact, setImpact] = useState('');
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [problems, setProblems] = useState<string[]>([]);
  const [diff, setDiff] = useState<ReleaseDiffRow[] | null>(null);

  const act = async (name: string, fn: () => Promise<unknown>) => {
    setBusy(name); setErr(''); setProblems([]);
    try { await fn(); rel.refetch(); onChanged(); }
    catch (e: any) { setErr(getErrorMessage(e)); setProblems(e?.response?.data?.problems || []); }
    finally { setBusy(''); }
  };

  if (rel.loading) return <LoadingState message="Loading release…" />;
  if (rel.error || !rel.data) return <ErrorState message={rel.error || 'Not found'} onRetry={rel.refetch} />;
  const r = rel.data;
  const inRelease = new Set(r.items.map((i) => i.benchmark_code));
  const candidates = (catalogue.data || []).filter((b) => !inRelease.has(b.benchmark_code) || b.status === 'active');

  return (
    <div className="glass-card p-4 space-y-3 text-xs">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-sm font-bold text-ink-900">{r.release_label}</p>
        <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status}</span>
        {r.release_notes && <span className="text-ink-500">{r.release_notes}</span>}
      </div>
      <p className="text-ink-500">
        Created by {r.created_by || '—'}{r.submitted_by ? ` · submitted by ${r.submitted_by}` : ''}
        {r.approved_by ? ` · approved by ${r.approved_by}` : ''}{r.published_by ? ` · published by ${r.published_by}` : ''}
      </p>

      {r.problems.length > 0 && (
        <div className="rounded-lg border border-danger-line bg-danger-bg p-2 space-y-0.5">
          <p className="font-bold text-danger">Blocks submission ({r.problems.length})</p>
          {r.problems.map((p) => <p key={p} className="text-ink-700">• {p}</p>)}
        </div>
      )}
      {r.warnings.length > 0 && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-2 space-y-0.5">
          <p className="font-bold text-ink-900">Warnings (do not block submission)</p>
          {r.warnings.map((w) => <p key={w} className="text-ink-700">• {w}</p>)}
        </div>
      )}
      {r.scoring && <ScoringPanel r={r} onChange={(v) => act('composite', () => setReleaseRequiresComposite(label, v))} busy={!!busy} />}
      {r.eligibility && (
        <EligibilityTable rows={r.eligibility} busy={!!busy} onPrefill={() => act('prefill', () => releaseAction(label, 'prefill'))} />
      )}

      <div className="space-y-1">
        {r.items.map((i) => (
          <div key={i.benchmark_code} className="rounded-lg border border-line-200 bg-surface p-2 flex items-center gap-2">
            <span className={`badge ${CHANGE_BADGE[i.change_type]}`}>{i.change_type}</span>
            <span className="font-mono text-ink-500">{i.benchmark_code}</span>
            <span className="text-ink-900 flex-1 min-w-0 truncate">{i.title}</span>
            {i.snapshot_hash && <span className="font-mono text-ink-400" title={i.snapshot_hash}><Lock className="w-3 h-3 inline" /> {i.snapshot_hash.slice(0, 8)}</span>}
            {r.status === 'draft' && i.change_type !== 'unchanged' && (
              <button className="btn-secondary btn-sm" title="Remove" onClick={() => act('rm', () => removeReleaseItem(label, i.benchmark_code))}>
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        ))}
        {r.items.length === 0 && <p className="text-ink-500">No benchmarks in this release yet.</p>}
      </div>

      {r.status === 'draft' && (
        <div className="grid md:grid-cols-[2fr_2fr_auto_auto] gap-2 items-center">
          <select className="input text-xs" value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Add a benchmark…</option>
            {candidates.map((b) => (
              <option key={b.benchmark_code} value={b.benchmark_code}>
                {b.status === 'active' ? '[retire] ' : b.levels_defined ? '✓ ' : '○ '}{b.benchmark_code} — {b.title}
              </option>
            ))}
          </select>
          <input className="input text-xs" placeholder="Impact summary (what changes for colleges)" value={impact} onChange={(e) => setImpact(e.target.value)} />
          <button className="btn-secondary btn-sm" disabled={!pick} onClick={() => act('add', async () => {
            const b = candidates.find((c) => c.benchmark_code === pick);
            await addReleaseItem(label, { benchmark_code: pick, retire: b?.status === 'active', impact_summary: impact });
            setPick(''); setImpact('');
          })}><Plus className="w-3.5 h-3.5" /> Add</button>
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => act('submit', () => releaseAction(label, 'submit'))}>
            <Send className="w-3.5 h-3.5" /> Submit for review
          </button>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {r.status === 'review' && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => act('approve', () => releaseAction(label, 'approve',
            window.prompt('Approval note:', '') || ''))}><CheckCircle2 className="w-3.5 h-3.5" /> Approve</button>
        )}
        {r.status === 'approved' && (
          <button className="btn-primary btn-sm" disabled={!!busy} onClick={() => {
            if (window.confirm(`Publish ${r.release_label}? Every benchmark in it is frozen, and it becomes the release used for new scorecards.`)) {
              act('publish', () => releaseAction(label, 'publish'));
            }
          }}><Lock className="w-3.5 h-3.5" /> Publish</button>
        )}
        {(r.status === 'review' || r.status === 'approved') && (
          <button className="btn-secondary btn-sm" disabled={!!busy} onClick={() => {
            const note = window.prompt('What needs to change?', '');
            if (note) act('back', () => releaseAction(label, 'send-back', note));
          }}><Undo2 className="w-3.5 h-3.5" /> Send back</button>
        )}
        <button className="btn-secondary btn-sm" onClick={async () => {
          try { setDiff((await getReleaseDiff(label)).data); } catch (e) { setErr(getErrorMessage(e)); }
        }}>Show changes</button>
      </div>

      {diff && (
        <div className="space-y-1">
          {diff.filter((d) => d.change_type !== 'unchanged').map((d) => (
            <p key={d.benchmark_code} className="text-ink-700">
              <span className={`badge ${CHANGE_BADGE[d.change_type]} mr-1`}>{d.change_type}</span>
              {d.benchmark_code} {d.title}{d.changed.length ? ` — changed: ${d.changed.join(', ')}` : ''}
              {d.impact_summary ? ` · ${d.impact_summary}` : ''}
            </p>
          ))}
          {diff.every((d) => d.change_type === 'unchanged') && <p className="text-ink-500">Nothing changes against the base release.</p>}
        </div>
      )}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      {problems.length > 0 && <div className="space-y-0.5">{problems.map((p) => <p key={p} className="text-danger">• {p}</p>)}</div>}
    </div>
  );
};

/** Can every included benchmark produce a composite score? Weights are approved by people (per benchmark). */
const ScoringPanel: React.FC<{ r: ReleaseDetail; onChange: (v: boolean) => void; busy: boolean }> = ({ r, onChange, busy }) => {
  const s = r.scoring!;
  return (
    <div className={`rounded-lg border p-2 space-y-1 ${s.fully_scoreable ? 'border-line-200 bg-surface' : 'border-warning-line bg-warning-bg'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-bold text-ink-900 flex-1 min-w-0">
          Scoring: {s.fully_scoreable ? 'every benchmark can produce a composite score' : `${s.missing.length} benchmark(s) cannot produce a composite score`}
          {s.scoring_model ? ` (model ${s.scoring_model})` : ' (no active scoring model)'}
        </p>
        <label className="flex items-center gap-1.5 text-ink-700">
          <input type="checkbox" checked={s.requires_composite} disabled={r.status !== 'draft' || busy}
            onChange={(e) => onChange(e.target.checked)} />
          Assessments need a composite score
        </label>
      </div>
      {s.missing.length > 0 && (
        <p className="text-ink-700">
          {s.requires_composite ? 'Blocks submission: ' : 'Shown, not blocking: '}
          {s.missing.map((m) => `${m.benchmark_code} (${m.detail})`).join('; ')}.
          {' '}Approve each benchmark's weights in Levels &rsaquo; Composite weights.
        </p>
      )}
    </div>
  );
};

/** Draft releases: which draft benchmarks are in, which are left out, and why. */
const EligibilityTable: React.FC<{ rows: ReleaseEligibilityRow[]; busy: boolean; onPrefill: () => void }> = ({ rows, busy, onPrefill }) => {
  const [showAll, setShowAll] = useState(false);
  const readyOut = rows.filter((r) => r.ready && !r.included).length;
  const included = rows.filter((r) => r.included).length;
  const shown = showAll ? rows : rows.filter((r) => !r.included);
  if (rows.length === 0) return null;
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-bold text-ink-900 flex-1">
          Draft benchmarks: {included} included · {rows.length - included} not included{readyOut ? ` (${readyOut} ready)` : ''}
        </p>
        <button className="btn-secondary btn-sm" disabled={busy || readyOut === 0} onClick={onPrefill}
          title={readyOut ? 'Add every ready draft benchmark that is not in this release yet' : 'No ready benchmark is left out'}>
          <Plus className="w-3.5 h-3.5" /> Add all ready ({readyOut})
        </button>
        <button className="btn-secondary btn-sm" onClick={() => setShowAll(!showAll)}>{showAll ? 'Only not included' : 'Show all'}</button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-line-200">
        <table className="w-full text-left">
          <thead className="bg-surface text-ink-500">
            <tr><th className="px-2 py-1">Benchmark</th><th className="px-2 py-1">In release</th><th className="px-2 py-1">Readiness</th></tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.code} className="border-t border-line-100 align-top">
                <td className="px-2 py-1"><span className="font-mono text-ink-500 mr-1">{r.code}</span>{r.title}</td>
                <td className="px-2 py-1 whitespace-nowrap">{r.included ? <span className="badge badge-success">included</span> : <span className="badge badge-neutral">not included</span>}</td>
                <td className="px-2 py-1">{r.ready ? <span className="text-success">ready</span>
                  : <span className="text-danger">needs: {r.missing.join('; ')}</span>}</td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={3} className="px-2 py-2 text-ink-500">Every draft benchmark is included.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
};

