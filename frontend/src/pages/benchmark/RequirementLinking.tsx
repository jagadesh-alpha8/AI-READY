import React, { useState } from 'react';
import { Link2, Unlink } from 'lucide-react';

import {
  linkRequirement, listApprovedRequirements, listBenchmarkLinks, suggestBenchmarks, unlinkRequirement,
} from '../../api/benchmarks';
import type {
  ApprovedRequirement, BenchmarkLink, BenchmarkSuggestion, LinkRelationship,
} from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';

/**
 * Stage 3.2: which approved requirements each benchmark interprets.
 * - BenchmarkLinks: inside a catalogue benchmark -- its linked requirements, add / remove.
 * - RequirementsTab: every approved requirement, with explainable benchmark suggestions.
 * Links can only change while the benchmark is a draft; the server enforces it.
 */

const REL_BADGE: Record<LinkRelationship, string> = {
  primary: 'badge-brand',
  supporting: 'badge-neutral',
  crosswalk: 'badge-neutral',
};

const RelationshipSelect: React.FC<{ value: LinkRelationship; onChange: (v: LinkRelationship) => void }> = ({
  value, onChange,
}) => (
  <select className="input text-xs" value={value} onChange={(e) => onChange(e.target.value as LinkRelationship)}>
    <option value="primary">Primary</option>
    <option value="supporting">Supporting</option>
    <option value="crosswalk">Crosswalk</option>
  </select>
);

export const BenchmarkLinks: React.FC<{ benchmarkCode: string; editable: boolean; onChanged?: () => void }> = ({
  benchmarkCode, editable, onChanged,
}) => {
  const { data, loading, error, refetch } = useApiResource<BenchmarkLink[]>(
    () => listBenchmarkLinks(benchmarkCode), [benchmarkCode],
  );
  const [code, setCode] = useState('');
  const [relationship, setRelationship] = useState<LinkRelationship>('primary');
  const [actionError, setActionError] = useState('');

  const act = async (fn: () => Promise<unknown>) => {
    setActionError('');
    try {
      await fn();
      refetch();
      onChanged?.();
    } catch (err) {
      setActionError(getErrorMessage(err));
    }
  };

  return (
    <div className="space-y-2">
      <p className="font-bold text-ink-900">Linked requirements</p>
      {loading && <LoadingState message="Loading links…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && (
        <p className="text-ink-500">None yet. Approved requirements are linked here (Requirements tab has suggestions).</p>
      )}
      {(data || []).map((l) => (
        <div key={l.requirement_code} className="rounded-lg border border-line-200 bg-surface p-2 flex items-start gap-2">
          <span className={`badge ${REL_BADGE[l.relationship]}`}>{l.relationship}</span>
          <div className="min-w-0 flex-1">
            <p className="text-ink-900"><span className="font-mono text-ink-500 mr-1">{l.requirement_code}</span>{l.statement}</p>
            <p className="text-ink-500 italic">“{l.source_quote}” — {l.source_code} p.{l.page ?? '?'}</p>
          </div>
          {editable && (
            <button className="btn-secondary btn-sm" title="Unlink"
              onClick={() => act(() => unlinkRequirement(benchmarkCode, l.requirement_code))}>
              <Unlink className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ))}
      {editable && (
        <div className="flex flex-wrap items-center gap-2">
          <input className="input text-xs flex-1 min-w-[180px]" placeholder="Requirement code, e.g. UGC-005-R001"
            value={code} onChange={(e) => setCode(e.target.value.trim())} />
          <RelationshipSelect value={relationship} onChange={setRelationship} />
          <button className="btn-primary btn-sm" disabled={!code}
            onClick={() => act(async () => { await linkRequirement(benchmarkCode, { requirement_code: code, relationship }); setCode(''); })}>
            <Link2 className="w-3.5 h-3.5" /> Link
          </button>
        </div>
      )}
      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
    </div>
  );
};

export const RequirementsTab: React.FC = () => {
  const [unlinkedOnly, setUnlinkedOnly] = useState(true);
  const { data, loading, error, refetch } = useApiResource<ApprovedRequirement[]>(
    () => listApprovedRequirements({ unlinked: unlinkedOnly }), [unlinkedOnly],
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Approved requirements (accepted from AI drafts in Sources). Link each one to the benchmark(s) it
        belongs to. Suggestions are ranked by source and wording overlap and say why; you decide.
      </p>
      <label className="flex items-center gap-2 text-sm text-ink-700">
        <input type="checkbox" checked={unlinkedOnly} onChange={(e) => setUnlinkedOnly(e.target.checked)} />
        Only requirements not linked to any benchmark yet
      </label>
      {loading && <LoadingState message="Loading requirements…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && (
        <EmptyState message={unlinkedOnly
          ? 'No unlinked requirements. Requirements appear here after an expert accepts AI drafts in Sources.'
          : 'No approved requirements yet. Draft them with AI in Sources, then accept the good ones.'} />
      )}
      <div className="space-y-3">
        {(data || []).map((r) => <RequirementCard key={r.id} requirement={r} onChanged={refetch} />)}
      </div>
    </div>
  );
};

const RequirementCard: React.FC<{ requirement: ApprovedRequirement; onChanged: () => void }> = ({
  requirement: r, onChanged,
}) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="glass-card p-4 space-y-2 text-xs">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <p className="text-sm text-ink-900"><span className="font-mono text-ink-500 mr-2">{r.code}</span>{r.statement}</p>
          <p className="text-ink-500 italic mt-0.5">“{r.source_quote}” — {r.source_code} {r.version_label} p.{r.page ?? '?'}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge badge-neutral">{r.kind}</span>
          {r.benchmarks.map((b) => (
            <span key={b.benchmark_code} className={`badge ${REL_BADGE[b.relationship]}`}>{b.benchmark_code}</span>
          ))}
          <button className="btn-secondary btn-sm" onClick={() => setOpen(!open)}>
            {open ? 'Hide suggestions' : 'Suggest benchmarks'}
          </button>
        </div>
      </div>
      {open && <Suggestions requirementCode={r.code} onLinked={onChanged} />}
    </div>
  );
};

const Suggestions: React.FC<{ requirementCode: string; onLinked: () => void }> = ({ requirementCode, onLinked }) => {
  const { data, loading, error, refetch } = useApiResource<BenchmarkSuggestion[]>(
    () => suggestBenchmarks(requirementCode), [requirementCode],
  );
  const [relationship, setRelationship] = useState<LinkRelationship>('primary');
  const [actionError, setActionError] = useState('');

  const link = async (benchmarkCode: string) => {
    setActionError('');
    try {
      await linkRequirement(benchmarkCode, { requirement_code: requirementCode, relationship });
      refetch();
      onLinked();
    } catch (err) {
      setActionError(getErrorMessage(err));
    }
  };

  if (loading) return <LoadingState message="Finding matching benchmarks…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-ink-500">Link as</span>
        <RelationshipSelect value={relationship} onChange={setRelationship} />
      </div>
      {(data || []).length === 0 && <p className="text-ink-500">No matching benchmark found; link one by code from the Catalogue tab.</p>}
      {(data || []).map((s) => (
        <div key={s.benchmark_code} className="rounded-lg border border-line-200 bg-surface p-2 flex items-start gap-2">
          <span className="badge badge-neutral" title="match score">{s.score}</span>
          <div className="min-w-0 flex-1">
            <p className="text-ink-900"><span className="font-mono text-ink-500 mr-1">{s.benchmark_code}</span>{s.title}</p>
            <p className="text-ink-500">{s.reasons.join(' · ')}</p>
          </div>
          <button className="btn-primary btn-sm" onClick={() => link(s.benchmark_code)}>
            <Link2 className="w-3.5 h-3.5" /> Link
          </button>
        </div>
      ))}
      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
    </div>
  );
};
