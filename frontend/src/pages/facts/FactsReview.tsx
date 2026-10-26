import React, { useState } from 'react';
import { ProcessingStatusBanner } from '../../components/ProcessingStatusBanner';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  listSprintFacts, listSprintFactsPage, getSprintFactFacets, confirmFact, bulkConfirmSprintFacts,
  correctFact, rejectFact, type FactFacets,
} from '../../api/facts';
import { DEFAULT_PAGE_SIZE, type Page } from '../../api/pagination';
import { Pagination, optionsFromCounts, useDebounced } from '../../components/Pagination';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Fact } from '../../types';
import { FileSearch, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';
import { CriConfidenceTile } from '../scoring/CriConfidenceTile';
import { RequestEvidenceModal } from './RequestEvidenceModal';
import { FactKindBadge } from './AIQIFSummaryBar';
import { ProfileConfirmPanel } from './ProfileConfirmPanel';
import { AIQIFTagRow, FactReviewState } from './AIQIFTagRow';

const KIND_LABELS: Record<string, string> = {
  ai_evidence: 'AI evidence', context: 'Context', profile: 'Institution profile', '': 'Not classified yet',
};

export const FactsReview: React.FC = () => {
  const { step, can } = useAccess();
  const canReview = can('facts.review');
  // Indicator tags are the AI-QIF expert's (Super Admin); everyone else -- the sales flow -- sees only what
  // each fact is for (AI evidence / context / profile), assigned automatically.
  const isExpert = can('aiqif.expert');
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  // Filters (server-side, apps/facts/filters.py): only the current page of facts is loaded; filter options and
  // totals come from aggregate counts over the whole sprint (facets).
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [kindFilter, setKindFilter] = useState('');
  const q = useDebounced(search.trim());
  const query = {
    q, status: statusFilter, owner_role: ownerFilter, source_document: sourceFilter, fact_kind: kindFilter,
  };
  const queryKey = JSON.stringify(query);
  // The page belongs to its filters: a new filter starts at page 1 in the same render (never a request for
  // page 2 of a filter that may have only one page).
  const [pageState, setPageState] = useState({ key: queryKey, page: 1 });
  const page = pageState.key === queryKey ? pageState.page : 1;
  const setPage = (next: number) => setPageState({ key: queryKey, page: next });
  const {
    data: pageData,
    loading,
    error,
    refetch: refetchPage,
  } = useApiResource<Page<Fact>>(() => listSprintFactsPage(sprintId!, { ...query, page, page_size: DEFAULT_PAGE_SIZE }),
    [sprintId, queryKey, page], isRealSprint);
  const { data: facets, refetch: refetchFacets } = useApiResource<FactFacets>(
    () => getSprintFactFacets(sprintId!), [sprintId], isRealSprint);
  const refetch = () => { refetchPage(); refetchFacets(); };
  const facts = pageData?.results || [];
  const totalFacts = facets?.total ?? 0;
  const filtersActive = Object.values(query).some(Boolean);

  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [correctionValue, setCorrectionValue] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [actingOnId, setActingOnId] = useState<string | null>(null);
  const [bulkConfirming, setBulkConfirming] = useState(false);
  const [bulkProgress, setBulkProgress] = useState('');

  const filteredFacts = facts;  // the current page, already filtered by the server
  // The CRI pillars are the 9 AI-QIF criteria (live scoring config, in framework order). All 9 are offered,
  // with their fact counts -- a criterion no fact is tagged to yet still shows, as (0).

  const handleConfirm = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await confirmFact(factId);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to confirm fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleBulkConfirm = async () => {
    if (!sprintId) return;
    setBulkConfirming(true);
    setBulkProgress('Finding eligible facts…');
    let factIds: string[] = [];
    try {
      // Every page matching the current filters, still unreviewed; the server decides who may act on each.
      const { data } = await listSprintFacts(sprintId, { ...query, status: 'extracted' });
      factIds = data.filter((fact) => fact.can_act === true && !fact.open_evidence_request).map((fact) => fact.id);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Could not list the eligible facts.'));
      setBulkConfirming(false); setBulkProgress('');
      return;
    }
    setBulkConfirming(false); setBulkProgress('');
    if (factIds.length === 0) {
      setActionMessage('Nothing to confirm in bulk: every fact in this list is already reviewed, or needs a one-by-one review.');
      return;
    }
    const accepted = window.confirm(
      `Confirm ${factIds.length} fact(s) from this list? The others need a one-by-one review. `
      + 'Each confirmation is recorded in the audit history.',
    );
    if (!accepted) return;

    setBulkConfirming(true);
    setActionError('');
    setActionMessage('');
    let confirmedCount = 0;
    let skippedCount = 0;
    const skippedReasons = new Map<string, number>();
    try {
      // The API accepts bounded batches; chunking lets a large sprint finish without an oversized request.
      const batchSize = 100;
      for (let offset = 0; offset < factIds.length; offset += batchSize) {
        const batch = factIds.slice(offset, offset + batchSize);
        setBulkProgress(`Confirming ${Math.min(offset + batch.length, factIds.length)} of ${factIds.length}…`);
        const { data } = await bulkConfirmSprintFacts(sprintId, batch, 'Confirmed by reviewer using Confirm all.');
        confirmedCount += data.confirmed_count;
        skippedCount += data.skipped_count;
        data.skipped.forEach(({ reason }) => skippedReasons.set(reason, (skippedReasons.get(reason) || 0) + 1));
      }
      const reasonSummary = [...skippedReasons.entries()].map(([reason, count]) => `${count} ${reason}`).join('; ');
      setActionMessage(
        `Bulk confirmation finished: ${confirmedCount} confirmed, ${skippedCount} skipped. `
        + (reasonSummary ? `Skipped: ${reasonSummary}` : 'All selected facts were confirmed.'),
      );
    } catch (err) {
      const partial = confirmedCount ? ` ${confirmedCount} fact(s) were confirmed before the request failed.` : '';
      setActionError(`${getErrorMessage(err, 'Bulk confirmation failed.')}${partial}`);
    } finally {
      setBulkConfirming(false);
      setBulkProgress('');
      refetch();
    }
  };


  const handleCorrectSubmit = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await correctFact(factId, correctionValue);
      setEditingFactId(null);
      setCorrectionValue('');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to correct fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleReject = async (factId: string) => {
    // The reason is required: it stays with the fact's gap, which moves to "needs replacement".
    const reason = window.prompt('Why is this value wrong? (kept with the fact and its gap)', '');
    if (!reason || !reason.trim()) return;
    setActingOnId(factId);
    setActionError('');
    try {
      await rejectFact(factId, reason.trim());
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to reject fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  // "Request Evidence" opens a form (what, why, who, by when); see RequestEvidenceModal.
  const [requestingFor, setRequestingFor] = useState<Fact | null>(null);

  const statusBadgeClass = (status: Fact['status']) => {
    switch (status) {
      case 'confirmed': return 'badge-success';
      case 'corrected': return 'badge-brand';
      case 'rejected': return 'badge-danger';
      case 'evidence_requested': return 'badge-accent';
      default: return 'badge-warning';
    }
  };

  return (
    <div className="space-y-6">
      {requestingFor && (
        <RequestEvidenceModal
          fact={requestingFor}
          onClose={() => setRequestingFor(null)}
          onCreated={() => { setRequestingFor(null); refetch(); }}
        />
      )}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <FileSearch className="w-5 h-5 text-brand-800" /> Step {step('sprint-facts')}: Extracted Facts Review
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Review candidate facts extracted by AIOS. Confirm, correct, or reject values with complete source snippet lineage.
            </p>
            {isRealSprint && <CriConfidenceTile sprintId={sprintId!} />}
          </div>
          <button onClick={() => navigate(`/sprint/${sprintId}/gaps`)} className="btn-primary shrink-0">
            <span>Proceed to Gap Dashboard</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}
      {actionMessage && (
        <div role="status" className="rounded-xl border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          {actionMessage}
        </div>
      )}

      {/* Facts Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Candidate & Extracted Fact Records</h2>
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <span className="text-xs text-ink-500">{totalFacts} facts registered</span>
            {isExpert && (
              <Link to={`/sprint/${sprintId}/aiqif-review`} className="btn-secondary btn-sm">AI-QIF expert queue</Link>
            )}
          </div>
        </div>

        {loading && !pageData ? (
          <LoadingState message="Loading extracted facts..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : totalFacts === 0 && facts.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No facts extracted yet. Seed facts or run extraction.</p>
            <button
              onClick={() => setActionError(
                'Demo fact seeding is disabled: facts are only ever created by the extraction pipeline, never fabricated.',
              )}
              className="btn-primary btn-sm mt-3"
            >
              Seed Sample Facts
            </button>
          </div>
        ) : (
          <>
          {isRealSprint && <ProfileConfirmPanel sprintId={sprintId!} canConfirm={can('profile.confirm')} />}
          {isRealSprint && (
            <div className="mb-4">
              <ProcessingStatusBanner sprintId={sprintId!} consequence="Facts from those documents may be missing below." />
            </div>
          )}
          <TableFilters
            search={search}
            onSearch={setSearch}
            placeholder="Search field ID, value, snippet or document…"
            shown={pageData?.count ?? 0}
            total={totalFacts}
            selects={[
              { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                options: optionsFromCounts(facets?.status, (v: string) => v.replace(/_/g, ' ')) },
              { key: 'kind', label: 'Fact kind', value: kindFilter, onChange: setKindFilter,
                options: optionsFromCounts(facets?.fact_kind, (v: string) => KIND_LABELS[v === 'none' ? '' : v] || v) },
              { key: 'owner', label: 'Owner', value: ownerFilter, onChange: setOwnerFilter,
                options: optionsFromCounts(facets?.owner_role) },
              { key: 'source', label: 'Source document', value: sourceFilter, onChange: setSourceFilter,
                options: optionsFromCounts(facets?.source_document) },
            ]}
          />
          {canReview && filteredFacts.length > 0 && (
            // Acts on the list below -- every page of it, with the filters above.
            <div className="flex justify-end mb-2">
              <button
                type="button"
                onClick={handleBulkConfirm}
                disabled={bulkConfirming}
                className="btn-primary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
                title={'Confirms every not-yet-reviewed fact in this list (all pages) that you may confirm. Facts that '
                  + 'need a closer look -- low confidence, in a conflict, missing details, owned by another role, or '
                  + 'with an open evidence request -- are left for you to review one by one.'}
              >
                {bulkConfirming ? bulkProgress : `Confirm all listed facts (${pageData?.count ?? 0})`}
              </button>
            </div>
          )}
          {filteredFacts.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No facts match these filters.</p>
            </div>
          ) : (
          <ScrollableTable>
            <table className="table-base min-w-[1640px]">
              <thead>
                <tr>
                  <th>S.No</th>
                  <th>Audit Field ID</th>
                  <th>Extracted Value</th>
                  <th title="The AI-QIF criteria and key indicators this fact is evidence for. A category only: it does not change any score.">
                    AI-QIF Category
                  </th>
                  <th title="The pillar the CRI scores this fact under once it is confirmed.">CRI Pillar</th>
                  <th>Source Document</th>
                  <th>Source Snippet</th>
                  <th>Confidence</th>
                  <th>Owner</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFacts.map((fact, index) => (
                  <tr key={fact.id}>
                    <td className="text-ink-500 tabular-nums">{(page - 1) * DEFAULT_PAGE_SIZE + index + 1}</td>
                    <td className="font-mono text-xs font-bold text-brand-800">
                      {fact.audit_field_id}
                    </td>
                    <td className="font-semibold text-ink-900">
                      {editingFactId === fact.id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={correctionValue}
                            onChange={(e) => setCorrectionValue(e.target.value)}
                            className="input py-1.5 px-2 text-xs"
                          />
                          <button
                            onClick={() => handleCorrectSubmit(fact.id)}
                            disabled={actingOnId === fact.id}
                            className="btn-primary btn-sm"
                          >
                            {actingOnId === fact.id ? 'Saving...' : 'Save'}
                          </button>
                        </div>
                      ) : (
                        <span>{typeof fact.value_json === 'object' ? JSON.stringify(fact.value_json) : String(fact.value_json)}</span>
                      )}
                    </td>
                    <td>
                      {isExpert ? (
                        <div className="space-y-1">
                          <FactKindBadge fact={fact} />
                          <AIQIFCategoryCell fact={fact} sprintId={sprintId!} />
                        </div>
                      ) : <FactKindBadge fact={fact} />}
                    </td>
                    <td>
                      <span className="badge-neutral">
                        {fact.pillar_label || fact.pillar || '—'}
                      </span>
                    </td>
                    <td className="text-ink-600 max-w-[10rem] truncate" title={fact.source_document_filename}>
                      {fact.source_document_filename || '—'}
                    </td>
                    <td className="text-ink-500 max-w-xs italic" title={fact.confidence_reason}>
                      <div className="truncate">&ldquo;{fact.source_snippet}&rdquo; ({fact.source_page || 'n/a'})</div>
                      {fact.confidence_reason && (
                        <div className="not-italic text-xs text-ink-400 truncate mt-0.5">
                          {fact.confidence_reason}
                        </div>
                      )}
                    </td>
                    <td className="font-mono font-semibold text-success tabular-nums">
                      {(fact.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="text-ink-700 font-medium">{fact.owner_role || 'IQAC'}</td>
                    <td>
                      <span className={statusBadgeClass(fact.status)}>{fact.status}</span>
                      {fact.auto_confirmed && (
                        <span className="block text-[11px] text-ink-500 mt-0.5"
                          title="Confirmed by the system because the AI confidence was above 80%. Correct or reject it if it is wrong.">
                          auto ({Math.round(fact.confidence * 100)}%)
                        </span>
                      )}
                      {fact.evidence_for_gaps?.map((g) => (
                        <span key={g.id} className="block text-[11px] text-ink-500 mt-0.5 max-w-[14rem] whitespace-normal"
                          title="This fact comes from a document uploaded as evidence for this gap. Confirming or correcting it (with its citation) settles a Low Confidence gap; it is not confirmed automatically.">
                          Evidence for gap: {g.title} ({g.status.replace(/_/g, ' ')})
                        </span>
                      ))}
                    </td>
                    <td className="text-right space-x-1 whitespace-nowrap">
                      {fact.can_act === false ? (
                        // The server's ownership rule (apps/facts/ownership.py): say who may act instead.
                        <span className="inline-block max-w-[16rem] whitespace-normal text-left text-xs text-ink-500" title={fact.act_blocked_reason}>
                          {fact.act_blocked_reason}
                        </span>
                      ) : fact.open_evidence_request ? (
                        // Decided on the request (accept / correct / reject evidence / withdraw), not here.
                        <Link
                          to={`/evidence-requests?view=all&id=${fact.open_evidence_request.id}`}
                          className="inline-block text-left text-xs font-semibold text-accent hover:underline"
                        >
                          Evidence request: {fact.open_evidence_request.overdue ? 'overdue' : fact.open_evidence_request.status_label.toLowerCase()}
                          <span className="block font-normal text-ink-500">
                            {fact.open_evidence_request.assigned_to_name || 'not assigned yet'}
                            {fact.open_evidence_request.due_date ? ` · due ${fact.open_evidence_request.due_date}` : ''}
                          </span>
                        </Link>
                      ) : (
                      <>
                      {fact.status !== 'confirmed' && (
                        <button
                          onClick={() => handleConfirm(fact.id)}
                          disabled={actingOnId === fact.id}
                          className="px-2.5 py-1 bg-success-solid text-white text-xs font-semibold rounded transition-colors disabled:opacity-60 hover:brightness-95"
                        >
                          {actingOnId === fact.id ? 'Working...' : 'Confirm'}
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setEditingFactId(fact.id);
                          setCorrectionValue(String(fact.value_json));
                        }}
                        className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-ink-700 text-xs font-semibold rounded transition-colors"
                      >
                        Correct
                      </button>
                      <button
                        onClick={() => setRequestingFor(fact)}
                        disabled={actingOnId === fact.id}
                        className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-accent text-xs font-semibold rounded transition-colors disabled:opacity-60"
                      >
                        Request Evidence
                      </button>
                      {fact.status !== 'rejected' && (
                        <button
                          onClick={() => handleReject(fact.id)}
                          disabled={actingOnId === fact.id}
                          className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-danger text-xs font-semibold rounded transition-colors disabled:opacity-60"
                        >
                          Reject
                        </button>
                      )}
                      </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollableTable>
          )}
          {pageData && (
            <Pagination page={page} pageSize={DEFAULT_PAGE_SIZE} count={pageData.count} onPage={setPage} />
          )}
          </>
        )}
      </div>
    </div>
  );
};


/** The fact's AI-QIF criterion and indicator(s), each with its confidence;
 * the AI's reason on hover. Unclear tags say so instead of guessing. */
/** The fact's AI-QIF tags, read-only: decision, reviewer, relationship, whether each counts. Confirm / reject /
 * edit / reopen happen in the AI-QIF expert queue (the link). */
const AIQIFCategoryCell: React.FC<{ fact: Fact; sprintId: string }> = ({ fact, sprintId }) => {
  if (fact.aiqif_mapping_status === 'pending' && fact.aiqif_mappings.length === 0) {
    return <span className="text-xs text-ink-400" title="Not classified yet: run retag_aiqif_facts, or re-run extraction.">Not classified yet</span>;
  }
  if (fact.aiqif_mappings.length === 0 && (fact.fact_kind === 'context' || fact.fact_kind === 'profile')) {
    return <span className="text-xs text-ink-500">No indicator (not AI evidence)</span>;
  }
  if (fact.aiqif_mappings.length === 0) {
    return (
      <span className="badge-neutral" title="The AI found no AI-QIF indicator this fact clearly supports.">
        Unmapped
      </span>
    );
  }
  return (
    <div className="min-w-[250px] max-w-[320px] space-y-2">
      <FactReviewState fact={fact} />
      {fact.aiqif_mappings.map((m) => (
        <AIQIFTagRow key={m.indicator_code} fact={fact} mapping={m} indicators={[]} readOnly />
      ))}
      <Link to={`/sprint/${sprintId}/aiqif-review?${fact.aiqif_mappings.some((m) => m.pending) ? '' : 'tab=reviewed&'}q=${encodeURIComponent(fact.field_key)}`}
        className="text-[11px] font-semibold text-brand-800 hover:underline">
        Manage in AI-QIF expert queue
      </Link>
    </div>
  );
};
