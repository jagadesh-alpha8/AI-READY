import React, { useState } from 'react';
import { CheckCircle2, GitBranch, Plus, Send } from 'lucide-react';

import {
  benchmarkCandidateAction as candidateAction, createBenchmarkCandidate as createCandidate,
  listBenchmarkCandidates as listCandidates, reviewBenchmarkCandidate as reviewCandidate,
} from '../../api/benchmarks';
import type { BenchmarkCandidateInfo, CandidateRole, CandidateStatus } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';

/**
 * Stage 4b: benchmark candidates. Proposed changes to the library, kept apart
 * from approved data until each required expert role approves (a different
 * person per role). Most come from the daily watcher; staff can add their own.
 * Approving never edits a benchmark -- it lets staff open a new draft version,
 * which then goes through readiness and a release like any other change.
 */

const STATUS_BADGE: Record<CandidateStatus, string> = {
  research: 'badge-neutral', review: 'badge-warning', approved: 'badge-success', rejected: 'badge-neutral',
  published: 'badge-brand',
};
const ROLE_LABEL: Record<CandidateRole, string> = {
  accreditation: 'Accreditation', academic: 'Academic', legal: 'Legal', ai_governance: 'AI governance',
  cybersecurity: 'Cybersecurity', product: 'Product',
};
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—');

export const CandidatesTab: React.FC = () => {
  const [filter, setFilter] = useState<'open' | 'all'>('open');
  const list = useApiResource<BenchmarkCandidateInfo[]>(() => listCandidates(filter), [filter]);
  const [adding, setAdding] = useState(false);

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Proposed changes to the benchmark library. The daily watcher creates one when an official source changes;
        you can also propose a new benchmark. Each needs approval from the listed expert roles — a different person
        for each — before a benchmark can be revised, and nothing reaches colleges until a release is published.
      </p>
      <div className="flex flex-wrap gap-2 items-center">
        <select className="input text-xs w-auto" value={filter} onChange={(e) => setFilter(e.target.value as 'open' | 'all')}>
          <option value="open">Open (research, review, approved)</option>
          <option value="all">All candidates</option>
        </select>
        <span className="flex-1" />
        {!adding && <button className="btn-secondary btn-sm" onClick={() => setAdding(true)}><Plus className="w-3.5 h-3.5" /> Propose a benchmark</button>}
      </div>
      {adding && <NewCandidate onDone={() => { setAdding(false); list.refetch(); }} onCancel={() => setAdding(false)} />}
      {list.loading && <LoadingState message="Loading candidates…" />}
      {list.error && <ErrorState message={list.error} onRetry={list.refetch} />}
      {(list.data || []).map((c) => <CandidateCard key={c.id} c={c} onChanged={list.refetch} />)}
      {list.data && list.data.length === 0 && (
        <p className="text-sm text-ink-500">{filter === 'open' ? 'No open candidates.' : 'No candidates yet.'}</p>
      )}
    </div>
  );
};

const NewCandidate: React.FC<{ onDone: () => void; onCancel: () => void }> = ({ onDone, onCancel }) => {
  const [type, setType] = useState('new_benchmark');
  const [title, setTitle] = useState('');
  const [code, setCode] = useState('');
  const [source, setSource] = useState('');
  const [rationale, setRationale] = useState('');
  const [err, setErr] = useState('');
  const save = async () => {
    setErr('');
    try {
      await createCandidate({ candidate_type: type, title, source_rationale: rationale,
        benchmark_code: code || undefined, source_code: source || undefined });
      onDone();
    } catch (e) { setErr(getErrorMessage(e)); }
  };
  return (
    <div className="glass-card p-4 space-y-2 text-xs">
      <div className="grid md:grid-cols-[1fr_2fr] gap-2">
        <select className="input text-xs" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="new_benchmark">New benchmark</option>
          <option value="update_benchmark">Update a benchmark</option>
          <option value="retire_benchmark">Retire a benchmark</option>
          <option value="source_update">Review a source change</option>
        </select>
        <input className="input text-xs" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className="input text-xs" placeholder="Benchmark code (to update / retire), e.g. ACA-05" value={code} onChange={(e) => setCode(e.target.value)} />
        <input className="input text-xs" placeholder="Source code (optional), e.g. UGC-005" value={source} onChange={(e) => setSource(e.target.value)} />
      </div>
      <textarea className="input text-xs" rows={3} placeholder="Why — which source says so, and what changes for colleges"
        value={rationale} onChange={(e) => setRationale(e.target.value)} />
      <div className="flex gap-2">
        <button className="btn-primary btn-sm" disabled={!title.trim() || !rationale.trim()} onClick={save}>Save as research</button>
        <button className="btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
    </div>
  );
};

const CandidateCard: React.FC<{ c: BenchmarkCandidateInfo; onChanged: () => void }> = ({ c, onChanged }) => {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState<CandidateRole>(c.required_roles[0]);
  const [notes, setNotes] = useState('');
  const [err, setErr] = useState('');
  const run = async (fn: () => Promise<unknown>) => {
    setErr('');
    try { await fn(); setNotes(''); onChanged(); } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="glass-card p-3 text-xs space-y-2">
      <button className="w-full text-left flex items-center gap-2 flex-wrap" onClick={() => setOpen(!open)}>
        <span className={`badge ${STATUS_BADGE[c.status]}`}>{c.status_label}</span>
        <span className="badge badge-neutral">{c.type_label}</span>
        <span className="text-ink-900 font-bold flex-1 min-w-0">{c.title}</span>
        <span className="text-ink-500">
          {c.required_roles.map((r) => {
            const s = c.role_status[r];
            const mark = !s ? '○' : s.decision === 'approve' ? '✓' : s.decision === 'reject' ? '✗' : '?';
            return `${mark} ${ROLE_LABEL[r]}`;
          }).join('  ·  ')}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-line-200 pt-2">
          <p className="text-ink-500">
            {c.benchmark_code ? `Benchmark ${c.benchmark_code} (${c.benchmark_status}) · ` : ''}
            {c.source_code ? `Source ${c.source_code} · ` : ''}
            importance {Math.round(Number(c.emergence_score))} · by {c.created_by} on {when(c.created_at)}
          </p>
          <pre className="whitespace-pre-wrap font-sans text-ink-700 bg-surface rounded-lg border border-line-200 p-2">{c.source_rationale}</pre>
          {c.reviews.length > 0 && (
            <div className="space-y-0.5">
              {c.reviews.map((r) => (
                <p key={r.id} className="text-ink-600">
                  {r.reviewer_role_label}: <strong>{r.decision_label}</strong> by {r.reviewer} on {when(r.reviewed_at)}
                  {r.notes ? ` — “${r.notes}”` : ''}
                </p>
              ))}
            </div>
          )}
          {c.status === 'research' && (
            <button className="btn-primary btn-sm" onClick={() => run(() => candidateAction(c.id, 'submit'))}>
              <Send className="w-3.5 h-3.5" /> Send to expert review
            </button>
          )}
          {c.status === 'review' && (
            <div className="space-y-2">
              <div className="grid md:grid-cols-[12rem_1fr] gap-2">
                <select className="input text-xs" value={role} onChange={(e) => setRole(e.target.value as CandidateRole)}>
                  {c.required_roles.map((r) => <option key={r} value={r}>Review as {ROLE_LABEL[r]}</option>)}
                </select>
                <input className="input text-xs" placeholder="Notes (needed to reject or ask for research)" value={notes} onChange={(e) => setNotes(e.target.value)} />
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-primary btn-sm" onClick={() => run(() => reviewCandidate(c.id, { reviewer_role: role, decision: 'approve', notes }))}>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Approve
                </button>
                <button className="btn-secondary btn-sm" onClick={() => run(() => reviewCandidate(c.id, { reviewer_role: role, decision: 'needs_research', notes }))}>Needs research</button>
                <button className="btn-secondary btn-sm" onClick={() => run(() => reviewCandidate(c.id, { reviewer_role: role, decision: 'reject', notes }))}>Reject</button>
              </div>
            </div>
          )}
          {c.status === 'approved' && c.benchmark_code && c.benchmark_status === 'active' && (
            <button className="btn-primary btn-sm" onClick={() => run(() => candidateAction(c.id, 'open-revision'))}>
              <GitBranch className="w-3.5 h-3.5" /> Open a new draft of {c.benchmark_code}
            </button>
          )}
          {c.status === 'approved' && c.benchmark_status === 'draft' && (
            <p className="text-ink-500">{c.benchmark_code} is a draft — edit it in Levels, then add it to the next release.</p>
          )}
          {err && <InlineError message={err} onDismiss={() => setErr('')} />}
        </div>
      )}
    </div>
  );
};
