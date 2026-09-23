import React, { useMemo, useState } from 'react';
import {
  BookOpen, Clock, Edit3, Layers, Lock, Search, Shield, ShieldCheck, Sparkles,
} from 'lucide-react';

import { DemoDataNotice } from '../../components/DemoDataNotice';
import { PageHeader, TabStrip } from '../../components/PageHeader';
import {
  seedApprovalRequests, seedBenchmarkVersions, seedBenchmarks, seedCandidates,
  benchmarkSources, sourceClaims,
} from '../../data/benchmark/seed';
import {
  MATURITY_LABELS, MATURITY_ORDER, canEditBenchmark, runAdversarialCritic,
  simulateImpact, validateBenchmark,
} from '../../data/benchmark/scoring';
import type { Benchmark, BenchmarkLifecycleState } from '../../data/benchmark/types';

/**
 * Ported from the InGage prototype's Benchmark Studio (7 tabs).
 *
 * The internal governance tool: author a benchmark, define its three maturity
 * levels, cite the authority behind it, move it through review, and publish it
 * — after which it is frozen. Nothing here writes to a server.
 */

type Tab = 'explorer' | 'editor' | 'levels' | 'sources' | 'approvals' | 'versions' | 'candidates';

const LIFECYCLE_BADGE: Partial<Record<BenchmarkLifecycleState, string>> = {
  PUBLISHED: 'badge-success',
  DRAFT: 'badge-neutral',
  INTERNAL_REVIEW: 'badge-warning',
  INGAGE_APPROVAL: 'badge-warning',
  REVISED: 'badge-info',
  REJECTED: 'badge-danger',
  RETIRED: 'badge-neutral',
  SUPERSEDED: 'badge-neutral',
};

const CRITICALITY_BADGE = {
  CRITICAL: 'badge-danger',
  HIGH: 'badge-warning',
  MEDIUM: 'badge-info',
  LOW: 'badge-neutral',
} as const;

export const BenchmarkStudio: React.FC = () => {
  const [tab, setTab] = useState<Tab>('explorer');
  const [selectedId, setSelectedId] = useState(seedBenchmarks[0].id);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<BenchmarkLifecycleState | 'ALL'>('ALL');

  const selected = seedBenchmarks.find((b) => b.id === selectedId) ?? seedBenchmarks[0];
  const selectedVersion =
    seedBenchmarkVersions.find((v) => v.id === selected.currentVersionId) ?? seedBenchmarkVersions[0];

  const pendingApprovals = seedApprovalRequests.filter((r) => r.status === 'PENDING').length;

  return (
    <div className="space-y-6">
      <DemoDataNotice detail="The library below is the prototype's twelve seed benchmarks; editing and publishing do not persist." />

      <PageHeader
        icon={BookOpen}
        title="Benchmark Studio"
        description="Author, source, version, approve and publish the benchmark library every client institution is scored against."
        badge={<span className="badge badge-neutral">InGage internal</span>}
      />

      <div className="glass-card p-4 flex items-start gap-3 border-brand-500/30">
        <Shield className="w-4 h-4 text-brand-800 shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600">
          <strong className="text-ink-900">Not a client-facing screen. </strong>
          This is the company's benchmark IP and its governance trail. In the prototype it sits behind
          nine dedicated roles — editor, source reviewer, methodology reviewer, approver, publisher,
          auditor — none of which exist in this platform's role model yet.
        </p>
      </div>

      <TabStrip
        tabs={[
          { id: 'explorer', label: 'Explorer', icon: Search, count: seedBenchmarks.length },
          { id: 'editor', label: 'Editor', icon: Edit3 },
          { id: 'levels', label: 'Levels', icon: Layers },
          { id: 'sources', label: 'Sources', icon: BookOpen, count: benchmarkSources.length },
          { id: 'approvals', label: 'Approvals', icon: ShieldCheck, count: pendingApprovals },
          { id: 'versions', label: 'Versions', icon: Clock },
          { id: 'candidates', label: 'AI candidates', icon: Sparkles, count: seedCandidates.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'explorer' && (
        <Explorer
          query={query}
          onQuery={setQuery}
          statusFilter={statusFilter}
          onStatusFilter={setStatusFilter}
          selectedId={selectedId}
          onSelect={(id) => { setSelectedId(id); setTab('editor'); }}
        />
      )}
      {tab === 'editor' && <Editor benchmark={selected} version={selectedVersion} />}
      {tab === 'levels' && <Levels benchmark={selected} version={selectedVersion} />}
      {tab === 'sources' && <Sources />}
      {tab === 'approvals' && <Approvals />}
      {tab === 'versions' && <Versions benchmark={selected} />}
      {tab === 'candidates' && <Candidates />}
    </div>
  );
};

// ===== EXPLORER =====
const Explorer: React.FC<{
  query: string;
  onQuery: (v: string) => void;
  statusFilter: BenchmarkLifecycleState | 'ALL';
  onStatusFilter: (v: BenchmarkLifecycleState | 'ALL') => void;
  selectedId: string;
  onSelect: (id: string) => void;
}> = ({ query, onQuery, statusFilter, onStatusFilter, selectedId, onSelect }) => {
  const statuses = useMemo(
    () => Array.from(new Set(seedBenchmarks.map((b) => b.status))).sort(),
    [],
  );

  const visible = seedBenchmarks.filter((b) => {
    const matchesStatus = statusFilter === 'ALL' || b.status === statusFilter;
    const q = query.trim().toLowerCase();
    const matchesQuery = !q || b.title.toLowerCase().includes(q) || b.code.toLowerCase().includes(q);
    return matchesStatus && matchesQuery;
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="benchmark-search">Search</label>
          <input
            id="benchmark-search"
            type="text"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            className="input"
            placeholder="Title or code, e.g. GOV.STR"
          />
        </div>
        <div>
          <label className="label" htmlFor="benchmark-status">Lifecycle state</label>
          <select
            id="benchmark-status"
            value={statusFilter}
            onChange={(e) => onStatusFilter(e.target.value as BenchmarkLifecycleState | 'ALL')}
            className="input"
          >
            <option value="ALL">All states</option>
            {statuses.map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="table-shell">
        <table className="table-base">
          <thead>
            <tr>
              <th>Code</th>
              <th>Benchmark</th>
              <th>Criticality</th>
              <th>Authority</th>
              <th>State</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((b) => (
              <tr key={b.id} className={b.id === selectedId ? 'bg-brand-50/40' : undefined}>
                <td className="font-mono text-xs font-bold text-brand-800 whitespace-nowrap">{b.code}</td>
                <td>
                  <p className="font-semibold text-ink-900">{b.title}</p>
                  <p className="text-xs text-ink-500">{b.ontologyPath}</p>
                </td>
                <td><span className={`badge ${CRITICALITY_BADGE[b.criticality]}`}>{b.criticality}</span></td>
                <td className="text-ink-600 text-xs">{b.authorityCategory.replace(/_/g, ' ')}</td>
                <td>
                  <span className={`badge ${LIFECYCLE_BADGE[b.status] ?? 'badge-neutral'}`}>
                    {b.status.replace(/_/g, ' ')}
                  </span>
                </td>
                <td className="text-right">
                  <button type="button" onClick={() => onSelect(b.id)} className="btn-secondary btn-sm">
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {visible.length === 0 && (
        <div className="panel-muted">
          <p className="text-sm text-ink-500">No benchmark matches that search.</p>
        </div>
      )}
    </div>
  );
};

// ===== EDITOR =====
const Editor: React.FC<{ benchmark: Benchmark; version: typeof seedBenchmarkVersions[number] }> = ({
  benchmark, version,
}) => {
  const editable = canEditBenchmark(benchmark);
  const validation = validateBenchmark(benchmark, version);

  return (
    <div className="space-y-4">
      {!editable.canEdit && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-4 flex items-start gap-3">
          <Lock className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <p className="text-sm text-ink-600">
            <strong className="text-warning">Locked. </strong>{editable.reason}
          </p>
        </div>
      )}

      <div className="glass-card p-5 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs font-bold text-brand-800 bg-brand-500/10 px-2 py-1 rounded">
            {benchmark.code}
          </span>
          <span className={`badge ${LIFECYCLE_BADGE[benchmark.status] ?? 'badge-neutral'}`}>
            {benchmark.status.replace(/_/g, ' ')}
          </span>
          <span className={`badge ${CRITICALITY_BADGE[benchmark.criticality]}`}>{benchmark.criticality}</span>
        </div>

        <div>
          <h2 className="text-lg font-bold text-ink-900">{benchmark.title}</h2>
          <p className="text-xs text-ink-500">{benchmark.ontologyPath}</p>
        </div>

        <Field label="Definition" value={benchmark.definition} />
        <Field label="Rationale" value={benchmark.rationale} />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Field label="Authority" value={benchmark.authorityCategory.replace(/_/g, ' ')} />
          <Field label="Confidence" value={benchmark.benchmarkConfidence.replace(/_/g, ' ')} />
          <Field label="Scoring config" value={benchmark.scoringConfigStatus.replace(/_/g, ' ')} />
        </div>
      </div>

      <div className="glass-card p-5 space-y-3">
        <h3 className="eyebrow">Completeness check</h3>
        {validation.isValid && validation.warnings.length === 0 ? (
          <p className="text-sm text-success">This benchmark is complete enough to publish.</p>
        ) : (
          <>
            {validation.errors.map((error) => (
              <p key={error} className="text-sm text-danger flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-danger-solid shrink-0 mt-1.5" />
                {error}
              </p>
            ))}
            {validation.warnings.map((warning) => (
              <p key={warning} className="text-sm text-warning flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-warning shrink-0 mt-1.5" />
                {warning}
              </p>
            ))}
          </>
        )}
      </div>
    </div>
  );
};

const Field: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="min-w-0">
    <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">{label}</p>
    <p className="text-sm text-ink-700 mt-0.5">{value}</p>
  </div>
);

// ===== LEVELS =====
const Levels: React.FC<{ benchmark: Benchmark; version: typeof seedBenchmarkVersions[number] }> = ({
  benchmark, version,
}) => (
  <div className="space-y-4">
    <div className="glass-card p-4">
      <p className="text-sm text-ink-600">
        <strong className="text-ink-900">Note the numbering. </strong>
        L3 is the lowest level and L1 the highest — the reverse of what most readers expect. This is
        the prototype's convention, preserved rather than silently corrected.
      </p>
    </div>

    <p className="text-sm text-ink-500">
      Maturity levels for <strong className="text-ink-900">{benchmark.code}</strong> — {benchmark.title}
    </p>

    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {MATURITY_ORDER.map((level) => {
        const detail = version.levels.find((l) => l.level === level);
        if (!detail) return null;
        return (
          <div key={level} className="glass-card p-5 space-y-3">
            <div>
              <span className="badge badge-brand">{MATURITY_LABELS[level]}</span>
              <h3 className="text-sm font-bold text-ink-900 mt-2">{detail.levelTitle}</h3>
              <p className="text-sm text-ink-600 mt-1">{detail.definition}</p>
            </div>

            <LevelList title="Observable requirements" items={detail.observableRequirements} />
            <LevelList title="Minimum evidence" items={detail.minimumEvidenceRequirements} />
            <LevelList title="Expected outcomes" items={detail.outcomeExpectations} />
            {detail.nonExamples.length > 0 && (
              <LevelList title="Does NOT count" items={detail.nonExamples} />
            )}
          </div>
        );
      })}
    </div>

    <div className="glass-card p-5 space-y-3">
      <h3 className="eyebrow">Evidence requirements</h3>
      <div className="table-shell">
        <table className="table-base">
          <thead>
            <tr>
              <th>Level</th>
              <th>Evidence</th>
              <th>Type</th>
              <th>Freshness</th>
              <th>Validation</th>
            </tr>
          </thead>
          <tbody>
            {version.evidenceRequirements.map((req) => (
              <tr key={req.id}>
                <td className="whitespace-nowrap text-ink-600">{MATURITY_LABELS[req.level]}</td>
                <td className="font-medium text-ink-900">{req.title}</td>
                <td className="text-ink-600 text-xs">{req.evidenceType.replace(/_/g, ' ')}</td>
                <td className="text-ink-600 whitespace-nowrap">{req.freshnessDays} days</td>
                <td className="text-ink-600 text-xs">{req.validationMethod.replace(/_/g, ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  </div>
);

const LevelList: React.FC<{ title: string; items: string[] }> = ({ title, items }) => (
  <div>
    <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500 mb-1">{title}</p>
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item} className="text-xs text-ink-600 flex items-start gap-1.5">
          <span className="w-1 h-1 rounded-full bg-ink-500/50 shrink-0 mt-1.5" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  </div>
);

// ===== SOURCES =====
const Sources: React.FC = () => (
  <div className="space-y-4">
    <p className="text-sm text-ink-500">
      The authorities benchmarks cite. A source can support or contradict a benchmark, and goes stale
      unless re-reviewed.
    </p>

    <div className="space-y-3">
      {benchmarkSources.map((source) => {
        const claims = sourceClaims.filter((c) => c.sourceId === source.id);
        return (
          <div key={source.id} className="glass-card p-5 space-y-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-ink-900">{source.title}</h3>
                <p className="text-xs text-ink-500 mt-0.5">
                  {source.sourceType.replace(/_/g, ' ')} · {source.authorityLevel.replace(/_/g, ' ')}
                  {source.publishedDate ? ` · published ${source.publishedDate}` : ''}
                </p>
              </div>
              <span className={`badge ${source.status === 'ACTIVE' ? 'badge-success' : 'badge-warning'}`}>
                {source.status}
              </span>
            </div>

            {claims.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500">
                  Extracted claims
                </p>
                {claims.map((claim) => (
                  <div key={claim.id} className="rounded-lg bg-surface border border-line-200 p-3">
                    <p className="text-sm text-ink-700">{claim.claimText}</p>
                    <p className="text-xs text-ink-500 mt-1.5">
                      {claim.pageReference ?? 'No page reference'} · confidence{' '}
                      {(claim.confidence * 100).toFixed(0)}% ·{' '}
                      <span className={claim.status === 'HUMAN_VALIDATED' ? 'text-success' : 'text-warning'}>
                        {claim.status.replace(/_/g, ' ').toLowerCase()}
                      </span>
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  </div>
);

// ===== APPROVALS =====
const Approvals: React.FC = () => (
  <div className="space-y-3">
    <p className="text-sm text-ink-500">
      Nothing reaches a client's score without passing through here. Approval is recorded, not
      assumed.
    </p>

    {seedApprovalRequests.map((request) => {
      const target = seedBenchmarks.find(
        (b) => b.id === request.objectId || b.currentVersionId === request.objectId,
      );
      return (
        <div key={request.id} className="glass-card p-5 space-y-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <p className="text-sm font-bold text-ink-900">
                {target ? `${target.code} — ${target.title}` : request.objectId}
              </p>
              <p className="text-xs text-ink-500 mt-0.5">
                {request.objectType.replace(/_/g, ' ').toLowerCase()} · requested by{' '}
                {request.requestedBy.replace(/_/g, ' ').toLowerCase()}
              </p>
            </div>
            <span
              className={`badge ${
                request.status === 'APPROVED' ? 'badge-success'
                  : request.status === 'PENDING' ? 'badge-warning' : 'badge-danger'
              }`}
            >
              {request.status.replace(/_/g, ' ')}
            </span>
          </div>

          <p className="text-sm text-ink-600 rounded-lg bg-surface border border-line-200 p-3">
            {request.reviewerComments}
          </p>

          {request.status === 'PENDING' ? (
            <div className="flex gap-2">
              <button type="button" className="btn-primary btn-sm" disabled title="Not wired up in this demo">
                Approve
              </button>
              <button type="button" className="btn-secondary btn-sm" disabled title="Not wired up in this demo">
                Request changes
              </button>
            </div>
          ) : (
            <p className="text-xs text-ink-500">
              {request.action} by {request.reviewedBy} on {request.reviewedAt?.slice(0, 10)}
            </p>
          )}
        </div>
      );
    })}
  </div>
);

// ===== VERSIONS =====
const Versions: React.FC<{ benchmark: Benchmark }> = ({ benchmark }) => {
  const versions = seedBenchmarkVersions.filter((v) => v.benchmarkId === benchmark.id);

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        Version history for <strong className="text-ink-900">{benchmark.code}</strong>. A published
        version is immutable — revising it creates a new one, so a score calculated last month still
        points at exactly what it was measured against.
      </p>

      <div className="space-y-2">
        {versions.map((version) => (
          <div key={version.id} className="glass-card p-4 flex items-center gap-4">
            <span className="font-mono text-xs font-bold bg-line-100 text-ink-700 px-2 py-1 rounded shrink-0">
              v{version.versionNumber}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-ink-900">{version.changeNote}</p>
              <p className="text-xs text-ink-500">
                {version.publishedAt ? `Published ${version.publishedAt}` : 'Not published'}
              </p>
            </div>
            {version.isImmutable && (
              <span className="badge badge-neutral shrink-0">
                <Lock className="w-3 h-3" /> Immutable
              </span>
            )}
            <span className={`badge ${LIFECYCLE_BADGE[version.status] ?? 'badge-neutral'} shrink-0`}>
              {version.status.replace(/_/g, ' ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ===== AI CANDIDATES =====
const Candidates: React.FC = () => (
  <div className="space-y-4">
    <div className="glass-card p-5 border-accent-line">
      <h2 className="text-sm font-bold text-ink-900 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-accent" />
        AI benchmark factory — advisory only
      </h2>
      <p className="text-sm text-ink-600 mt-1.5">
        An agent proposes candidates from the source registry. A candidate cannot affect any score
        until a human converts it to a draft and it survives the full approval path.
      </p>
    </div>

    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {seedCandidates.map((candidate) => {
        const findings = runAdversarialCritic(candidate);
        const simulation = simulateImpact(candidate);

        return (
          <div key={candidate.id} className="glass-card p-5 space-y-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="font-mono text-xs font-bold text-accent bg-accent-bg px-2 py-1 rounded">
                {candidate.suggestedCode}
              </span>
              <span className="badge badge-info">{candidate.status.replace(/_/g, ' ')}</span>
            </div>

            <div>
              <h3 className="text-sm font-bold text-ink-900">{candidate.suggestedTitle}</h3>
              <p className="text-xs text-ink-500 mt-0.5">{candidate.suggestedOntologyPath}</p>
            </div>

            <p className="text-sm text-ink-600 rounded-lg bg-surface border border-line-200 p-3">
              {candidate.suggestedDefinition}
            </p>

            <div className="space-y-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500">
                Proposed levels
              </p>
              {(['L3', 'L2', 'L1'] as const).map((key) => (
                <p key={key} className="text-xs text-ink-600">
                  <strong className="text-ink-900">{key}:</strong> {candidate.suggestedLevels[key]}
                </p>
              ))}
            </div>

            <div className="space-y-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500">
                Adversarial critic — {findings.length} finding{findings.length === 1 ? '' : 's'}
              </p>
              {findings.map((finding) => (
                <div
                  key={finding.id}
                  className={`text-xs rounded-lg p-2.5 border ${
                    finding.severity === 'ERROR'
                      ? 'bg-danger-bg border-danger-line text-danger'
                      : finding.severity === 'WARNING'
                        ? 'bg-warning-bg border-warning-line text-warning'
                        : 'bg-info-bg border-info-line text-info'
                  }`}
                >
                  <strong>{finding.checkType.replace(/_/g, ' ')}:</strong> {finding.finding}
                </div>
              ))}
            </div>

            <div className="rounded-lg bg-surface border border-line-200 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wide text-ink-500 mb-1">
                Impact simulation · risk {simulation.riskLevel.toLowerCase()}
              </p>
              <p className="text-xs text-ink-600">{simulation.summary}</p>
            </div>

            <button type="button" className="btn-primary btn-sm" disabled title="Not wired up in this demo">
              Convert to human draft
            </button>
          </div>
        );
      })}
    </div>
  </div>
);
