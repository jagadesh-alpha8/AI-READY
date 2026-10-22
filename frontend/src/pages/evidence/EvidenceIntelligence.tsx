import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, Download, FileStack, FileText, ScanLine, Upload,
} from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { listSprintDocuments } from '../../api/documents';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import type { DocumentStatus, Fact, Gap, Sprint, SprintDocument } from '../../types';
import { useAccess } from '../../utils/access';

/**
 * Evidence Intelligence — the institution's evidence position for one sprint.
 *
 * Every figure here is REAL: documents, their processing state, the facts each
 * one produced, and the required documents still missing. Nothing is seeded.
 *
 * "Missing" is deliberately NOT computed here from a frontend copy of the
 * required-document list. The backend already raises a `missing_document` gap
 * for each required type a sprint lacks (`apps/gaps/services.py::
 * _detect_missing_documents`), so this page reads those gaps instead. One
 * source of truth — and the codebase already carries one hand-synced
 * checklist divergence, which is a defect, not a pattern to copy.
 */

type Filter = 'all' | DocumentStatus | 'needs_attention';

const STATUS_BADGE: Record<DocumentStatus, string> = {
  pending: 'badge-neutral',
  uploaded: 'badge-info',
  processing: 'badge-warning',
  processed: 'badge-success',
  failed: 'badge-danger',
  rejected: 'badge-danger',
};

const STATUS_LABEL: Record<DocumentStatus, string> = {
  pending: 'Pending',
  uploaded: 'Uploaded',
  processing: 'Processing',
  processed: 'Processed',
  failed: 'Failed',
  rejected: 'Rejected',
};

/** A document earns attention when processing failed, OCR flagged pages the
 * reader could not use, or it processed without yielding a single fact. */
function needsAttention(doc: SprintDocument, factCount: number): string | null {
  if (doc.status === 'failed' || doc.status === 'rejected') {
    return 'Processing did not complete';
  }
  if (doc.ocr_warnings.length > 0) {
    return `${doc.ocr_warnings.length} page${doc.ocr_warnings.length === 1 ? '' : 's'} could not be read`;
  }
  if (doc.status === 'processed' && factCount === 0) {
    return 'Processed but produced no facts';
  }
  return null;
}

export const EvidenceIntelligence: React.FC = () => {
  const { can } = useAccess();
  const navigate = useNavigate();
  // The selected sprint is shared by every page (context/SelectedSprintContext.tsx).
  const { sprintId: selectedSprintId } = useSelectedSprint();
  const [filter, setFilter] = useState<Filter>('all');

  const { data: sprints, loading: sprintsLoading, error: sprintsError, refetch: refetchSprints } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  // The first sprint is selected once the list arrives, rather than held in
  // state from the start: there is no valid default before it loads.
  const activeSprintId = selectedSprintId;

  const { data: documents, loading: docsLoading, error: docsError, refetch: refetchDocs } =
    useApiResource<SprintDocument[]>(
      () => listSprintDocuments(activeSprintId),
      [activeSprintId],
      !!activeSprintId,
    );

  const { data: facts } = useApiResource<Fact[]>(
    () => listSprintFacts(activeSprintId),
    [activeSprintId],
    !!activeSprintId,
  );

  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId),
    [activeSprintId],
    !!activeSprintId,
  );

  /** How many extracted facts each document produced. */
  const factsByDocument = useMemo(() => {
    const counts = new Map<string, number>();
    (facts ?? []).forEach((fact) => {
      if (!fact.document_id) return;
      counts.set(fact.document_id, (counts.get(fact.document_id) ?? 0) + 1);
    });
    return counts;
  }, [facts]);

  /** Required documents the backend says are still absent. */
  const missingDocuments = useMemo(
    () => (gaps ?? []).filter((g) => g.gap_type === 'missing_document' && g.status === 'open'),
    [gaps],
  );

  const docs = documents ?? [];
  const attentionCount = docs.filter((d) => needsAttention(d, factsByDocument.get(d.id) ?? 0)).length;

  const visible = useMemo(() => {
    if (filter === 'all') return docs;
    if (filter === 'needs_attention') {
      return docs.filter((d) => needsAttention(d, factsByDocument.get(d.id) ?? 0));
    }
    return docs.filter((d) => d.status === filter);
  }, [docs, filter, factsByDocument]);

  const filterOptions = useMemo(() => {
    const present = Array.from(new Set(docs.map((d) => d.status)));
    return [
      { id: 'all' as Filter, label: 'All', count: docs.length },
      ...present.map((s) => ({
        id: s as Filter,
        label: STATUS_LABEL[s],
        count: docs.filter((d) => d.status === s).length,
      })),
      ...(attentionCount > 0
        ? [{ id: 'needs_attention' as Filter, label: 'Needs attention', count: attentionCount }]
        : []),
    ];
  }, [docs, attentionCount]);

  if (sprintsLoading) return <LoadingState message="Loading sprints…" />;
  if (sprintsError) return <ErrorState message={sprintsError} onRetry={refetchSprints} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={FileStack}
          title="Evidence Intelligence"
          description="Every document this assessment relies on, what state it is in, and what is still missing."
        />
        <EmptyState
          message="No sprints yet. Evidence is gathered during a discovery sprint — start one to see it here."
          action={can('sprint.manage') ? { label: 'Start a sprint', onClick: () => navigate('/sprint/setup') } : undefined}
        />
      </div>
    );
  }

  if (!activeSprintId) return <SelectSprintPrompt />;

  const totalFacts = (facts ?? []).length;
  const processed = docs.filter((d) => d.status === 'processed').length;

  // Missing-document gaps are raised by the gap engine, which only runs after
  // extraction. Before that, zero gaps means "not assessed yet", NOT "nothing
  // missing" — and reporting a reassuring 0 to a client whose evidence has
  // not been looked at would be exactly the kind of fabricated comfort the
  // rest of this platform refuses to give.
  const coverageAssessed = (gaps ?? []).length > 0 || processed > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileStack}
        title="Evidence Intelligence"
        description="Every document this assessment relies on, what state it is in, and what is still missing."
        actions={
          activeSprintId && (
            <button
              type="button"
              onClick={() => navigate(`/sprint/${activeSprintId}/upload`)}
              className="btn-primary btn-sm"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload</span>
            </button>
          )
        }
      />


      {docsError && <InlineError message={docsError} onDismiss={refetchDocs} />}
      {docsLoading && <LoadingState message="Loading evidence…" />}

      {!docsLoading && !docsError && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Metric label="Documents" value={docs.length} />
            <Metric label="Processed" value={processed} tone={processed === docs.length && docs.length > 0 ? 'success' : 'default'} />
            <Metric label="Facts extracted" value={totalFacts} />
            <Metric
              label="Required, missing"
              value={coverageAssessed ? missingDocuments.length : '—'}
              tone={!coverageAssessed ? 'default' : missingDocuments.length > 0 ? 'danger' : 'success'}
              hint={coverageAssessed ? undefined : 'Not assessed until processing runs'}
            />
          </div>

          {coverageAssessed && missingDocuments.length > 0 && (
            <div className="glass-card p-5 space-y-3 border-danger-line">
              <h2 className="eyebrow flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
                Required documents not yet provided
              </h2>
              <p className="text-sm text-ink-500">
                These block a verified baseline. The list comes from the audit's own gap engine, so
                it stays correct as documents arrive.
              </p>
              <ul className="space-y-2">
                {missingDocuments.map((gap) => (
                  <li
                    key={gap.id}
                    className="flex items-start gap-2.5 rounded-lg border border-line-200 bg-surface p-3"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-danger-solid shrink-0 mt-2" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-ink-900">{gap.title}</p>
                      <p className="text-xs text-ink-500 mt-0.5">{gap.description}</p>
                    </div>
                    {gap.owner_role && (
                      <span className="badge badge-neutral shrink-0">
                        {gap.owner_role.replace(/_/g, ' ').toLowerCase()}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => navigate(`/sprint/${activeSprintId}/gaps`)}
                className="btn-secondary btn-sm"
              >
                <span>Open the gap dashboard</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {docs.length === 0 ? (
            <EmptyState
              message="No documents uploaded to this sprint yet."
              action={{
                label: 'Upload the data pack',
                onClick: () => navigate(`/sprint/${activeSprintId}/upload`),
              }}
            />
          ) : (
            <>
              <FilterPills options={filterOptions} active={filter} onChange={setFilter} />

              <div className="space-y-2">
                {visible.map((doc) => {
                  const factCount = factsByDocument.get(doc.id) ?? 0;
                  const attention = needsAttention(doc, factCount);
                  return (
                    <div key={doc.id} className="glass-card p-4 flex items-center gap-4">
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                          doc.status === 'failed' || doc.status === 'rejected'
                            ? 'bg-danger-bg text-danger'
                            : doc.status === 'processed'
                              ? 'bg-success-bg text-success'
                              : 'bg-info-bg text-info'
                        }`}
                      >
                        <FileText className="w-[18px] h-[18px]" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-ink-900 truncate">
                          {doc.title || doc.original_filename || 'Untitled document'}
                        </p>
                        <p className="text-xs text-ink-500">
                          {doc.document_type_label}
                          {doc.page_count ? ` · ${doc.page_count} pages` : ''}
                          {doc.file_size_display ? ` · ${doc.file_size_display}` : ''}
                          {doc.status === 'processed' ? ` · ${factCount} facts` : ''}
                        </p>
                        {attention && (
                          <p className="text-xs text-warning mt-0.5 flex items-center gap-1">
                            <ScanLine className="w-3 h-3 shrink-0" />
                            {attention}
                          </p>
                        )}
                      </div>

                      {doc.download_url && (
                        <a
                          href={doc.download_url}
                          className="btn-icon shrink-0"
                          title="Download"
                          aria-label={`Download ${doc.title || doc.original_filename}`}
                        >
                          <Download className="w-4 h-4" />
                        </a>
                      )}

                      <span className={`badge ${STATUS_BADGE[doc.status]} shrink-0`}>
                        {STATUS_LABEL[doc.status]}
                      </span>
                    </div>
                  );
                })}
              </div>

              {visible.length === 0 && (
                <EmptyState message="No documents match that filter." />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};

const Metric: React.FC<{
  label: string;
  value: number | string;
  tone?: 'default' | 'danger' | 'success';
  hint?: string;
}> = ({ label, value, tone = 'default', hint }) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p
      className={`text-2xl font-bold mt-1 tabular-nums ${
        tone === 'danger' ? 'text-danger' : tone === 'success' ? 'text-success' : 'text-ink-900'
      }`}
    >
      {value}
    </p>
    {hint && <p className="text-xs text-ink-500 mt-1">{hint}</p>}
  </div>
);
