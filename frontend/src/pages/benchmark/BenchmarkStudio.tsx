import React, { useMemo, useState } from 'react';
import {
  BookOpen, Clock, Edit3, Eye, Layers, Lock, Search, Shield, ShieldCheck, Sparkles,
} from 'lucide-react';

import { PageHeader, TabStrip } from '../../components/PageHeader';
import {
  seedApprovalRequests, seedBenchmarkVersions, seedBenchmarks, seedCandidates,
} from '../../data/benchmark/seed';
import { getSourceSummary, listSources } from '../../api/benchmarks';
import type { SourceDocument, SourceLibrarySummary } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { useAuth } from '../../context/AuthContext';
import { SourceVersionPanel } from './SourceVersionPanel';
import { CatalogueTab } from './CatalogueTab';
import { RequirementsTab } from './RequirementLinking';
import { LevelsEditorTab } from './LevelsEditorTab';
import { ApplicabilityPreviewTab } from './Applicability';
import { ReleasesTab } from './ReleasesTab';
import { WatcherTab } from './WatcherTab';
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

type Tab = 'explorer' | 'requirements' | 'applicability' | 'editor' | 'levels' | 'sources' | 'approvals' | 'versions' | 'watcher' | 'candidates';

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

const BenchmarkStudioPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('explorer');
  const [selectedId, setSelectedId] = useState(seedBenchmarks[0].id);
  const [levelsCode, setLevelsCode] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<BenchmarkLifecycleState | 'ALL'>('ALL');

  const selected = seedBenchmarks.find((b) => b.id === selectedId) ?? seedBenchmarks[0];
  const selectedVersion =
    seedBenchmarkVersions.find((v) => v.id === selected.currentVersionId) ?? seedBenchmarkVersions[0];

  const pendingApprovals = seedApprovalRequests.filter((r) => r.status === 'PENDING').length;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BookOpen}
        title="Benchmark Studio"
        description="Author, source, version, approve and publish the benchmark library every client institution is scored against."
        badge={<span className="badge badge-danger">Admin</span>}
      />

      {/* Spec §3 and §25.1 put this screen in a separate INTERNAL navigation
          that client users cannot reach at all. It is temporarily left in the
          client menu so the work can be reviewed; moving it out is a tracked
          correction, not an open question. Until then this banner is the only
          thing standing between a client and the company's benchmark IP, so
          it is deliberately the loudest on the page. */}
      <div className="rounded-lg border-2 border-danger-line bg-danger-bg p-4 flex items-start gap-3">
        <Shield className="w-5 h-5 text-danger shrink-0 mt-0.5" />
        <div className="text-sm text-ink-600 min-w-0 space-y-1.5">
          <p>
            <strong className="text-danger">InGage internal only — not for client eyes. </strong>
            This screen holds the company's benchmark IP and its governance trail.
          </p>
          <p>
            Only InGage staff (super admins and consultants) can open this page, and the Sources
            API enforces the same rule on the server. Specification §3 and §25.1 still call for a
            separate internal navigation; the menu entry is visible to clients for now.
          </p>
          <p className="text-ink-500">
            §20.1 defines nine governance roles for this workspace — editor, source reviewer,
            methodology reviewer, approver, publisher, auditor and more. None exist in this
            platform's role model yet.
          </p>
          <p className="text-ink-500">
            <strong>Catalogue</strong>, <strong>Requirements</strong>, <strong>Applicability</strong>, <strong>Levels</strong>,
            <strong> Sources</strong>, <strong>Releases</strong> and <strong>Watcher</strong> are real. Editor, Approvals and AI candidates still show the
            prototype's twelve seed benchmarks — editing, approving and
            publishing there change nothing and a reload resets everything.
          </p>
        </div>
      </div>

      <TabStrip
        tabs={[
          { id: 'explorer', label: 'Catalogue', icon: Search },
          { id: 'requirements', label: 'Requirements', icon: Layers },
          { id: 'applicability', label: 'Applicability', icon: ShieldCheck },
          { id: 'editor', label: 'Editor', icon: Edit3 },
          { id: 'levels', label: 'Levels', icon: Layers },
          { id: 'sources', label: 'Sources', icon: BookOpen },
          { id: 'approvals', label: 'Approvals', icon: ShieldCheck, count: pendingApprovals },
          { id: 'versions', label: 'Releases', icon: Clock },
          { id: 'watcher', label: 'Watcher', icon: Eye },
          { id: 'candidates', label: 'AI candidates', icon: Sparkles, count: seedCandidates.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === 'explorer' && <CatalogueTab onEditLevels={(c) => { setLevelsCode(c); setTab('levels'); }} />}
      {tab === 'requirements' && <RequirementsTab />}
      {tab === 'applicability' && <ApplicabilityPreviewTab />}
      {tab === 'editor' && <Editor benchmark={selected} version={selectedVersion} />}
      {tab === 'levels' && <LevelsEditorTab code={levelsCode} onCode={setLevelsCode} />}
      {tab === 'sources' && <Sources />}
      {tab === 'approvals' && <Approvals />}
      {tab === 'versions' && <ReleasesTab />}
      {tab === 'watcher' && <WatcherTab />}
      {tab === 'candidates' && <Candidates />}
    </div>
  );
};

/** Benchmark Studio is InGage's internal tool (benchmark IP): super admins and
 * consultants only. The Sources API enforces the same rule server-side. */
export const BenchmarkStudio: React.FC = () => {
  const { user } = useAuth();
  if (user?.role !== 'super_admin' && user?.role !== 'consultant') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={BookOpen}
          title="Benchmark Studio"
          description="InGage's internal benchmark library."
        />
        <div className="panel-muted">
          <p className="text-sm text-ink-500">Benchmark Studio is available to InGage staff only.</p>
        </div>
      </div>
    );
  }
  return <BenchmarkStudioPage />;
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
// Real data: the Source Library backend (apps/benchmarks), filled by the
// interns' Source Register import. Read-only here -- changes go through the
// audited importer and, later, the approval workflow.
const COLLECTION_BADGE: Record<string, string> = {
  downloaded: 'badge-success',
  link_only: 'badge-brand',
  licensed_link_only: 'badge-brand',
  to_find: 'badge-neutral',
  blocked: 'badge-warning',
  not_available: 'badge-danger',
};

const Sources: React.FC = () => {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [openCode, setOpenCode] = useState<string | null>(null);
  const summary = useApiResource<SourceLibrarySummary>(() => getSourceSummary(), []);
  const { data, loading, error, refetch } = useApiResource<SourceDocument[]>(
    () => listSources({ q: query || undefined, category: category || undefined }),
    [query, category],
  );
  const categories = Object.keys(summary.data?.by_category || {}).sort();
  const refreshAll = () => { refetch(); summary.refetch(); };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        The official documents benchmarks are built from, imported from the Source Register. Every
        version is a draft until a reviewer approves it; approved versions can never be changed.
      </p>

      {summary.data && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="badge badge-neutral">{summary.data.documents} documents</span>
          <span className="badge badge-neutral">{summary.data.versions} versions</span>
          {Object.entries(summary.data.by_collection_status).map(([k, n]) => (
            <span key={k} className={`badge ${COLLECTION_BADGE[k] || 'badge-neutral'}`}>
              {k.replace(/_/g, ' ')}: {n}
            </span>
          ))}
          {summary.data.flagged_versions > 0 && (
            <span className="badge badge-warning">{summary.data.flagged_versions} need review</span>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          className="input flex-1 min-w-[200px]"
          placeholder="Search title or source code"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c || '(none)'}</option>)}
        </select>
      </div>

      {loading && <LoadingState message="Loading source library…" />}
      {error && <ErrorState message={error} onRetry={refetch} />}
      {data && data.length === 0 && (
        <EmptyState message="No sources yet. Import the Source Register: python manage.py import_source_register <file.xlsx> --commit" />
      )}

      <div className="space-y-3">
        {(data || []).map((doc) => {
          const v = doc.latest_version;
          const open = openCode === doc.source_code;
          return (
            <div key={doc.id} className="glass-card p-5 space-y-3">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-ink-900">
                    <span className="font-mono text-ink-500 mr-2">{doc.source_code}</span>
                    {doc.title}
                  </h3>
                  <p className="text-xs text-ink-500 mt-0.5">
                    {doc.authority_name} · {doc.source_role_label || 'role not set'} · {doc.document_type || 'type not set'}
                    {v && v.version_label !== 'unversioned' ? ` · ${v.version_label}` : ''}
                    {v?.issued_on ? ` · issued ${v.issued_on}` : ''}
                    {doc.licensed_content ? ' · licensed (link only)' : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {v && (
                    <span className={`badge ${COLLECTION_BADGE[v.collection_status] || 'badge-neutral'}`}>
                      {v.collection_status_label}
                    </span>
                  )}
                  {v && <span className="badge badge-neutral">{v.status}</span>}
                  {doc.review_flag_count > 0 && (
                    <button
                      className="badge badge-warning"
                      onClick={() => setOpenCode(open ? null : doc.source_code)}
                    >
                      {doc.review_flag_count} to review
                    </button>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                {doc.official_url && <a className="text-brand-700 hover:underline" href={doc.official_url} target="_blank" rel="noreferrer">Official page</a>}
                {v?.direct_url && <a className="text-brand-700 hover:underline" href={v.direct_url} target="_blank" rel="noreferrer">Document</a>}
                {v?.drive_url && <a className="text-brand-700 hover:underline" href={v.drive_url} target="_blank" rel="noreferrer">Drive copy</a>}
                {v?.checksum_sha256 && (
                  <span className="font-mono text-ink-500" title={v.checksum_sha256}>
                    SHA-256 {v.checksum_sha256.slice(0, 12)}…
                  </span>
                )}
                {doc.applies_to && <span className="text-ink-500">Applies to: {doc.applies_to}</span>}
              </div>

              {v && <SourceVersionPanel version={v} onChanged={refreshAll} />}

              {open && v && (
                <ul className="rounded-lg bg-surface border border-line-200 p-3 space-y-1 text-xs text-ink-700 list-disc pl-6">
                  {v.review_flags.map((f) => <li key={f}>{f}</li>)}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

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
