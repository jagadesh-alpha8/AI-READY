import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowRight, FileText, Network } from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { listSprintDocuments } from '../../api/documents';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { PageHeader } from '../../components/PageHeader';
import type { Gap, Sprint, SprintDocument } from '../../types';

/**
 * Compliance Mapping — which accreditation evidence this institution holds.
 *
 * ⚠ This is deliberately NARROWER than its name suggests, and the page says
 * so. Real criterion-level mapping ("Criterion 6.5 is 55% covered") needs the
 * official NAAC / NBA / NIRF / NEP criteria lists, and none is loaded: there
 * is no criteria model, no source for them, and inventing criteria with
 * plausible coverage percentages would be exactly the fabricated comfort the
 * rest of this platform refuses to give.
 *
 * What IS knowable today: which accreditation-relevant documents the sprint
 * holds and which are missing. Only document types whose own name identifies
 * a framework are claimed — `naac_ssr` is NAAC evidence by definition. The
 * rest are listed as general evidence rather than assigned a framework on
 * this team's guess.
 */

/** Frameworks a document type names explicitly. Nothing inferred. */
const FRAMEWORK_BY_TYPE: Record<string, string> = {
  naac_ssr: 'NAAC',
  aqar: 'NAAC',
  aqar_report: 'NAAC',
  aicte_approval: 'AICTE',
  nirf_submission: 'NIRF',
};

const FRAMEWORKS = ['NAAC', 'AICTE', 'NIRF'] as const;

export const ComplianceMapping: React.FC = () => {
  const navigate = useNavigate();
  const [sprintId, setSprintId] = useState('');

  const { data: sprints, loading, error, refetch } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = sprintId || sprints?.[0]?.id || '';
  const enabled = !!activeSprintId;

  const { data: documents } = useApiResource<SprintDocument[]>(
    () => listSprintDocuments(activeSprintId), [activeSprintId], enabled);
  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId), [activeSprintId], enabled);

  const missingDocs = useMemo(
    () => (gaps ?? []).filter((g) => g.gap_type === 'missing_document' && g.status === 'open'),
    [gaps],
  );

  const byFramework = useMemo(() => {
    const docs = documents ?? [];
    return FRAMEWORKS.map((framework) => {
      const held = docs.filter((d) => FRAMEWORK_BY_TYPE[d.document_type] === framework);
      const missing = missingDocs.filter((g) => {
        const name = g.title.toLowerCase();
        return Object.entries(FRAMEWORK_BY_TYPE)
          .filter(([, f]) => f === framework)
          .some(([type]) => name.includes(type.split('_')[0]));
      });
      return { framework, held, missing };
    }).filter((row) => row.held.length > 0 || row.missing.length > 0);
  }, [documents, missingDocs]);

  const otherEvidence = useMemo(
    () => (documents ?? []).filter((d) => !FRAMEWORK_BY_TYPE[d.document_type]),
    [documents],
  );

  if (loading) return <LoadingState message="Loading sprints…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Network}
          title="Compliance Mapping"
          description="Which accreditation evidence this institution holds, and what is missing."
        />
        <EmptyState message="No sprints yet. Evidence is gathered during a discovery sprint." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Network}
        title="Compliance Mapping"
        description="Which accreditation evidence this institution holds, and what is missing."
      />

      <div className="glass-card p-4">
        <label className="label" htmlFor="compliance-sprint">Sprint</label>
        <select
          id="compliance-sprint"
          value={activeSprintId}
          onChange={(e) => setSprintId(e.target.value)}
          className="input"
        >
          {sprints.map((s) => (
            <option key={s.id} value={s.id}>
              {s.institution_name || s.name || 'Institution'} · {s.sprint_code} ({s.status.replace(/_/g, ' ')})
            </option>
          ))}
        </select>
      </div>

      {/* The limitation is the most important thing on this page. */}
      <div className="rounded-lg border-2 border-warning-line bg-warning-bg p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
        <div className="text-sm text-ink-600 min-w-0 space-y-1.5">
          <p>
            <strong className="text-warning">Criterion-level mapping is not built. </strong>
            This page shows which accreditation <em>documents</em> the sprint holds. It does not
            say how far any NAAC, NBA, NIRF or NEP criterion is covered.
          </p>
          <p>
            Doing that needs the official criteria lists loaded as data, and a mapping engine to
            match evidence against them. Neither exists. Showing invented criteria with confidence
            percentages would look far more finished than it is — which is why this page shows less.
          </p>
        </div>
      </div>

      {byFramework.length === 0 && otherEvidence.length === 0 ? (
        <EmptyState
          message="No documents uploaded to this sprint yet."
          action={{
            label: 'Upload the data pack',
            onClick: () => navigate(`/sprint/${activeSprintId}/upload`),
          }}
        />
      ) : (
        <>
          {byFramework.map(({ framework, held, missing }) => (
            <div key={framework} className="glass-card p-5 space-y-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <h2 className="eyebrow">{framework}</h2>
                <div className="flex gap-2">
                  {held.length > 0 && <span className="badge badge-success">{held.length} held</span>}
                  {missing.length > 0 && <span className="badge badge-danger">{missing.length} missing</span>}
                </div>
              </div>

              {held.map((doc) => (
                <Row
                  key={doc.id}
                  title={doc.title || doc.original_filename}
                  detail={`${doc.document_type_label}${doc.page_count ? ` · ${doc.page_count} pages` : ''}`}
                  state={doc.status === 'processed' ? 'held' : 'pending'}
                />
              ))}

              {missing.map((gap) => (
                <Row key={gap.id} title={gap.title.replace(/^Missing /, '')} detail="Not uploaded" state="missing" />
              ))}
            </div>
          ))}

          {otherEvidence.length > 0 && (
            <div className="glass-card p-5 space-y-3">
              <h2 className="eyebrow">Other evidence held</h2>
              <p className="text-xs text-ink-500">
                These support accreditation generally, but their type does not name a specific
                framework — so none is claimed for them here.
              </p>
              {otherEvidence.map((doc) => (
                <Row
                  key={doc.id}
                  title={doc.title || doc.original_filename}
                  detail={doc.document_type_label}
                  state={doc.status === 'processed' ? 'held' : 'pending'}
                />
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={() => navigate('/evidence')}
            className="btn-secondary btn-sm"
          >
            <span>See the full evidence register</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </>
      )}
    </div>
  );
};

const Row: React.FC<{
  title: string;
  detail: string;
  state: 'held' | 'pending' | 'missing';
}> = ({ title, detail, state }) => (
  <div className="flex items-center gap-3 rounded-lg border border-line-200 bg-surface p-3">
    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
      state === 'held' ? 'bg-success-bg text-success'
        : state === 'missing' ? 'bg-danger-bg text-danger' : 'bg-info-bg text-info'
    }`}>
      <FileText className="w-4 h-4" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm font-medium text-ink-900 truncate">{title}</p>
      <p className="text-xs text-ink-500">{detail}</p>
    </div>
    <span className={`badge shrink-0 ${
      state === 'held' ? 'badge-success' : state === 'missing' ? 'badge-danger' : 'badge-info'
    }`}>
      {state === 'held' ? 'Held' : state === 'missing' ? 'Missing' : 'Processing'}
    </span>
  </div>
);
