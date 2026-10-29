import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BookOpen, Search, ShieldCheck } from 'lucide-react';

import { PageHeader, TabStrip } from '../../components/PageHeader';
import { getSourceSummary, listSources } from '../../api/benchmarks';
import type { SourceDocument, SourceLibrarySummary } from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/access';
import { SourcesTable } from './SourcesTable';
import { useStudioParam } from './studioNav';
import { CatalogueTab } from './CatalogueTab';
import { ApplicabilityPreviewTab } from './Applicability';

/**
 * Benchmark Studio -- InGage's internal, READ-ONLY view of the standard benchmark catalogue (apps/benchmarks).
 * The manager-provided workbooks are authoritative: sources, indicators, L3/L2/L1, applicability and source
 * mappings change only through the controlled workbook import, never here (the API refuses every write --
 * apps/benchmarks/permissions.py). Three sections:
 * - Source Library: the source documents, searchable, with the indicators each one is mapped to.
 * - Benchmark Library: the indicators, each with its levels, origin and source mappings.
 * - Applicability Preview: which indicators apply to a college, from its saved benchmark profile.
 * College evidence review and scoring (sprints, Benchmark Assessment) are separate and unchanged.
 */

type Tab = 'sources' | 'explorer' | 'applicability';

const TABS: Tab[] = ['sources', 'explorer', 'applicability'];

const BenchmarkStudioPage: React.FC = () => {
  // The open section lives in the URL (?tab=), so a refresh stays on it; a fresh visit opens the Source Library.
  const [params, setParams] = useSearchParams();
  const asked = params.get('tab') as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : 'sources';
  // Picking a section drops the previous one's focus (?code= / ?source=, studioNav.ts).
  const setTab = (t: Tab) => setParams(new URLSearchParams({ tab: t }), { replace: true });

  return (
    <div className="space-y-6">
      <PageHeader
        dataTour="studio-header"
        icon={BookOpen}
        title="Benchmark Studio"
        description="The standard benchmark catalogue every college is assessed against: manager-provided sources and indicators, read-only."
        badge={<span className="badge badge-danger">Admin</span>}
      />

      <div data-tour="studio-tabs">
        <TabStrip
          tabs={[
            { id: 'sources', label: 'Source Library', icon: BookOpen },
            { id: 'explorer', label: 'Benchmark Library', icon: Search },
            { id: 'applicability', label: 'Applicability Preview', icon: ShieldCheck },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      {tab === 'sources' && <Sources />}
      {tab === 'explorer' && <CatalogueTab />}
      {tab === 'applicability' && <ApplicabilityPreviewTab />}
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

// ===== SOURCE LIBRARY =====
// The manager-provided Source Register, imported by `manage.py import_source_register`; listed read-only.
const Sources: React.FC = () => {
  const [linked] = useStudioParam('source');  // from an indicator's Origin & Sources
  const [query, setQuery] = useState(linked);
  React.useEffect(() => { if (linked) setQuery(linked); }, [linked]);
  const [category, setCategory] = useState('');
  const summary = useApiResource<SourceLibrarySummary>(() => getSourceSummary(), []);
  const { data, loading, error, refetch } = useApiResource<SourceDocument[]>(
    () => listSources({ q: query || undefined, category: category || undefined }),
    [query, category],
  );
  const categories = Object.keys(summary.data?.by_category || {}).sort();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2" data-tour="studio-search">
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
      {data && data.length === 0 && <EmptyState message="No sources match." />}

      {data && data.length > 0 && (
        <div data-tour="studio-table">
          <SourcesTable docs={data} />
        </div>
      )}
    </div>
  );
};
