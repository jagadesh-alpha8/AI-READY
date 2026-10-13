import React, { useState } from 'react';
import { CheckCircle2, Lock, Plus, Send, Trash2, Undo2 } from 'lucide-react';

import {
  addReleaseItem, createRelease, getRelease, getReleaseDiff, listCatalogue, listReleases, releaseAction,
  removeReleaseItem,
} from '../../api/benchmarks';
import type { BenchmarkReleaseInfo, CatalogueBenchmark, ReleaseDetail, ReleaseDiffRow, ReleaseStatus } from '../../api/benchmarks';
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
  const [err, setErr] = useState('');
  const inProgress = (list.data || []).find((r) => !['published', 'retired'].includes(r.status));

  const create = async () => {
    setErr('');
    try {
      const r = await createRelease({ release_label: label, release_notes: notes });
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
          <p className="text-ink-500">A new release starts with every benchmark of the current release, marked unchanged.</p>
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
        <div className="rounded-lg border border-warning-line bg-warning-bg p-2 space-y-0.5">
          <p className="font-bold text-ink-900">Not ready yet</p>
          {r.problems.map((p) => <p key={p} className="text-ink-700">• {p}</p>)}
        </div>
      )}
      {r.warnings.map((w) => <p key={w} className="text-warning">{w}</p>)}

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
