import React, { useState } from 'react';
import { BookOpen, Clock, Eye, Layers, Search, Shield, ShieldCheck, Sparkles } from 'lucide-react';

import { PageHeader, TabStrip } from '../../components/PageHeader';
import { getSourceSummary, listSources } from '../../api/benchmarks';
import type { SourceDocument, SourceLibrarySummary } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/access';
import { SourceVersionPanel } from './SourceVersionPanel';
import { AddSourceButton } from './AddSourceForm';
import { CatalogueTab } from './CatalogueTab';
import { RequirementsTab } from './RequirementLinking';
import { LevelsEditorTab } from './LevelsEditorTab';
import { ApplicabilityPreviewTab } from './Applicability';
import { ReleasesTab } from './ReleasesTab';
import { WatcherTab } from './WatcherTab';
import { CandidatesTab } from './CandidatesTab';

/**
 * Benchmark Studio -- InGage's internal benchmark library (apps/benchmarks).
 * Every tab is backed by the API: sources, requirements, the catalogue and its
 * levels / evidence / applicability rules, releases, the daily watcher, and
 * the benchmark candidates that watcher changes turn into. (The prototype's
 * seed-data Editor / Approvals / AI-candidates tabs were removed: their real
 * equivalents are Levels, Releases and Candidates.)
 */

type Tab = 'explorer' | 'requirements' | 'applicability' | 'levels' | 'sources' | 'versions' | 'watcher' | 'candidates';

const BenchmarkStudioPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('explorer');
  const [levelsCode, setLevelsCode] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BookOpen}
        title="Benchmark Studio"
        description="Author, source, version, approve and publish the benchmark library every client institution is scored against."
        badge={<span className="badge badge-danger">Admin</span>}
      />

      <div className="rounded-lg border-2 border-danger-line bg-danger-bg p-4 flex items-start gap-3">
        <Shield className="w-5 h-5 text-danger shrink-0 mt-0.5" />
        <div className="text-sm text-ink-600 min-w-0 space-y-1.5">
          <p>
            <strong className="text-danger">InGage internal only — not for client eyes. </strong>
            This screen holds the company's benchmark IP and its governance trail.
          </p>
          <p>
            Only InGage staff (super admins and consultants) can open this page, and every
            benchmark API enforces the same rule on the server.
          </p>
        </div>
      </div>

      {/* Tabs in the order the work is done; keeping source documents current is its own section. */}
      <div className="flex flex-col lg:flex-row lg:items-end gap-3 lg:gap-6">
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500 mb-1.5">Benchmark library</p>
          <TabStrip
            tabs={[
              { id: 'sources', label: 'Sources', icon: BookOpen },
              { id: 'requirements', label: 'Requirements', icon: Layers },
              { id: 'explorer', label: 'Catalogue', icon: Search },
              { id: 'levels', label: 'Levels', icon: Layers },
              { id: 'applicability', label: 'Applicability', icon: ShieldCheck },
              { id: 'versions', label: 'Releases', icon: Clock },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>
        <div className="min-w-0 lg:pl-6 lg:border-l lg:border-line-200">
          <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500 mb-1.5">Source Updates</p>
          <TabStrip
            tabs={[
              { id: 'watcher', label: 'Watcher', icon: Eye },
              { id: 'candidates', label: 'Candidates', icon: Sparkles },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>
      </div>

      {tab === 'explorer' && <CatalogueTab onEditLevels={(c) => { setLevelsCode(c); setTab('levels'); }} />}
      {tab === 'requirements' && <RequirementsTab />}
      {tab === 'applicability' && <ApplicabilityPreviewTab />}
      {tab === 'levels' && <LevelsEditorTab code={levelsCode} onCode={setLevelsCode} />}
      {tab === 'sources' && <Sources />}
      {tab === 'versions' && <ReleasesTab />}
      {tab === 'watcher' && <WatcherTab />}
      {tab === 'candidates' && <CandidatesTab />}
    </div>
  );
};

/** Benchmark Studio is InGage's internal tool (benchmark IP): super admins and
 * consultants only. The Sources API enforces the same rule server-side. */
export const BenchmarkStudio: React.FC = () => {
  const { user } = useAuth();
  if (!canDo(user?.role, 'benchmarks.studio')) {
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
        The official documents benchmarks are built from, imported from the Source Register or added
        here. Every version is a draft until a reviewer approves it; approved versions can never be changed.
      </p>

      <AddSourceButton onAdded={refreshAll} />

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
        <EmptyState message="No sources yet. Use Add source above, or import the Source Register (python manage.py import_source_register <file.xlsx> --commit)." />
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
