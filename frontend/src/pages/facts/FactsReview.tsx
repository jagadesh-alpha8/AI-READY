import React, { useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import {
  listSprintFacts, listSprintFactsPage, getSprintFactFacets, confirmFact, bulkConfirmSprintFacts,
  correctFact, rejectFact, type FactFacets,
} from '../../api/facts';
import { DEFAULT_PAGE_SIZE, type Page } from '../../api/pagination';
import { Pagination, optionsFromCounts, pillarOptions, useDebounced } from '../../components/Pagination';
import { useApiResource } from '../../hooks/useApiResource';
import { useLivePolling } from '../../hooks/useLivePolling';
import { getProcessingSummary } from '../../api/extraction';
import type { ProcessingSummary } from '../../types/extraction';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Fact } from '../../types';
import { FileSearch, ArrowRight } from 'lucide-react';
import { ScrollableTable } from '../../components/ScrollableTable';
import { TableFilters } from '../../components/TableFilters';
import { useAccess } from '../../utils/access';
import { FactVerificationModal, VerificationCell } from './FactVerification';
import { VerificationPanel } from './VerificationPanel';
import { PendingCorrectionNote, ProposeCorrectionModal } from './CorrectionProposal';
import { FactKindBadge } from './AIQIFSummaryBar';
import { AIQIFTagRow, FactReviewState } from './AIQIFTagRow';
import { reviewEvidenceRequest } from '../../api/evidenceRequests';
import { confirmDialog, promptDialog } from '../../components/Dialog';
import { isRealSprintId } from '../../utils/selectedSprint';

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
  const isRealSprint = isRealSprintId(sprintId);

  // Filters (server-side, apps/facts/filters.py): only the current page of facts is loaded; filter options and
  // totals come from aggregate counts over the whole sprint (facets).
  const [search, setSearch] = useState('');
  const [reviewQueue, setReviewQueue] = useState('exceptions');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [kindFilter, setKindFilter] = useState('');
  const [pillarFilter, setPillarFilter] = useState('');
  const [verificationFilter, setVerificationFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const q = useDebounced(search.trim());
  const query = {
    q, review_queue: reviewQueue, status: statusFilter, source_document: sourceFilter, fact_kind: kindFilter,
    pillar: pillarFilter, aiqif_indicator: categoryFilter, verification_status: verificationFilter,
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
    refresh: refreshPage,
  } = useApiResource<Page<Fact>>(() => listSprintFactsPage(sprintId!, { ...query, page, page_size: DEFAULT_PAGE_SIZE }),
    [sprintId, queryKey, page], isRealSprint);
  const { data: facets, refetch: refetchFacets, refresh: refreshFacets } = useApiResource<FactFacets>(
    () => getSprintFactFacets(sprintId!), [sprintId], isRealSprint);
  // While AI extraction is still running for this sprint, new facts are swapped in place every few seconds
  // (filters, page and any open edit stay as they are); polling stops once nothing is processing.
  const { data: processing, refresh: refreshProcessing } = useApiResource<ProcessingSummary>(
    () => getProcessingSummary(sprintId!), [sprintId], isRealSprint);
  useLivePolling((processing?.counts?.active ?? 0) > 0,
    () => Promise.all([refreshPage(), refreshFacets(), refreshProcessing()]), 5000);
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

  const withdrawRequest = async (fact: Fact) => {
    if (!fact.open_evidence_request) return;
    setActingOnId(fact.id);
    setActionError('');
    try {
      await reviewEvidenceRequest(fact.open_evidence_request.id, { decision: 'withdraw', reason: 'Reviewer closed the request to continue with direct evidence upload and review.' });
      refetch();
    } catch (err) { setActionError(getErrorMessage(err, 'Could not close this evidence request.')); }
    finally { setActingOnId(null); }
  };

  const handleBulkConfirm = async () => {
    if (!sprintId) return;
    setBulkConfirming(true);
    setBulkProgress('Finding eligible facts…');
    let factIds: string[] = [];
    try {
      // Every page matching the current filters, still unreviewed; the server decides who may act on each.
      const { data } = await listSprintFacts(sprintId, { ...query, review_queue: 'verified', status: 'extracted', verification_status: 'verified' });
      factIds = data.filter((fact) => fact.can_act === true && !fact.open_evidence_request && fact.verification?.risk_level !== 'high').map((fact) => fact.id);
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
    const accepted = await confirmDialog(
      `Accept ${factIds.length} verified fact(s) matching these filters? The others need a one-by-one review. `
      + 'Each confirmation is recorded in the audit history.',
      { title: 'Bulk confirm', confirmLabel: `Confirm ${factIds.length}` },
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
        const { data } = await bulkConfirmSprintFacts(sprintId, batch, 'Verified facts accepted in a batch by the reviewer.', true);
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
    const reason = await promptDialog('Why is this value wrong? (kept with the fact and its gap)',
      { title: 'Reject fact', confirmLabel: 'Reject', danger: true, required: true });
    if (!reason) return;
    setActingOnId(factId);
    setActionError('');
    try {
      await rejectFact(factId, reason);
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to reject fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  // Why a fact was (or was not) verified, and correcting a value a person already reviewed.
  const [verifyingFact, setVerifyingFact] = useState<Fact | null>(null);
  const [proposingFor, setProposingFor] = useState<Fact | null>(null);

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
      {verifyingFact && <FactVerificationModal fact={verifyingFact} onClose={() => setVerifyingFact(null)} />}
      {proposingFor && (
        <ProposeCorrectionModal
          fact={proposingFor}
          onClose={() => setProposingFor(null)}
          onDone={() => {
            setProposingFor(null);
            setActionMessage('Correction proposed. Another reviewer must approve it before the fact changes.');
            refetch();
          }}
        />
      )}
      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold">Extracted Facts Review</h2>
          <p className="text-sm text-ink-600 mt-1">Review exceptions first. Model confidence is an estimate, not a verified probability. Fact confirmation does not gate capability assessment.</p>
        </div>
        <div className="flex items-center gap-3 shrink-0 self-end sm:self-auto">
          <button onClick={() => navigate(`/sprint/${sprintId}/score`)} className="btn-primary shrink-0">
            <span>Open assessment</span>
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

      {isRealSprint && sprintId && (
        <VerificationPanel sprintId={sprintId} canReview={canReview} onChanged={refetch} />
      )}

      {/* Facts Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Candidate & Extracted Fact Records</h2>
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <span className="text-xs text-ink-500">{totalFacts} facts registered</span>
            {isExpert && (
              <Link data-tour="facts-expert-link" to={`/sprint/${sprintId}/aiqif-review`} className="btn-secondary btn-sm">AI-QIF expert queue</Link>
            )}
          </div>
        </div>

        {loading && !pageData ? (
          <LoadingState message="Loading extracted facts..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : totalFacts === 0 && facts.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No facts extracted yet. Facts appear here once uploaded documents are processed by AI.</p>
            <div className="flex flex-wrap gap-2 mt-3">
              <Link to={`/sprint/${sprintId}/upload`} className="btn-primary btn-sm">Upload documents</Link>
              <Link to={`/sprint/${sprintId}/monitor`} className="btn-secondary btn-sm">AI processing monitor</Link>
            </div>
          </div>
        ) : (
          <>
          <div data-tour="facts-filters">
            <TableFilters
              search={search}
              onSearch={setSearch}
              placeholder="Search field ID, value, snippet or document…"
              shown={pageData?.count ?? 0}
              total={totalFacts}
              selects={[
                { key: 'queue', label: 'Review queue', value: reviewQueue, onChange: setReviewQueue,
                  options: [{ value: 'exceptions', label: 'Exceptions' }, { value: 'verified', label: 'Verified facts' }] },
                { key: 'verification', label: 'Verification', value: verificationFilter, onChange: setVerificationFilter,
                  options: optionsFromCounts(facets?.verification_status, (v: string) => ({
                    verified: 'Verified', needs_review: 'Needs review', invalid: 'Invalid', conflicting: 'Conflicting',
                    none: 'Not verified yet' } as Record<string, string>)[v] || v) },
                { key: 'status', label: 'Status', value: statusFilter, onChange: setStatusFilter,
                  options: optionsFromCounts(facets?.status, (v: string) => v.replace(/_/g, ' ')) },
                // The CRI pillars are the 9 AI-QIF criteria in framework order; one with no facts still shows, as (0).
                { key: 'pillar', label: 'Evidence pillar', value: pillarFilter, onChange: setPillarFilter,
                  options: pillarOptions(facets?.pillars) },
                // Facts tagged to one of the 36 AI-QIF key indicators (what the AI-QIF Category column shows).
                { key: 'category', label: 'AI-QIF Category', value: categoryFilter, onChange: setCategoryFilter,
                  options: pillarOptions(facets?.aiqif_indicators) },
                { key: 'kind', label: 'Fact kind', value: kindFilter, onChange: setKindFilter,
                  options: optionsFromCounts(facets?.fact_kind, (v: string) => KIND_LABELS[v === 'none' ? '' : v] || v) },
                { key: 'source', label: 'Source document', value: sourceFilter, onChange: setSourceFilter,
                  options: optionsFromCounts(facets?.source_document) },
              ]}
            />
          </div>
          {canReview && filteredFacts.length > 0 && (
            // Acts on the list below -- every page of it, with the filters above.
            <div className="flex justify-end mb-2">
              <button
                type="button"
                data-tour="facts-bulk-confirm"
                onClick={handleBulkConfirm}
                disabled={bulkConfirming}
                className="btn-primary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
                title="Accepts verified, eligible facts matching these filters across all pages. Evidence is rechecked on the server. High-risk facts require individual review."
              >
                {bulkConfirming ? bulkProgress : 'Accept verified facts'}
              </button>
            </div>
          )}
          {filteredFacts.length === 0 ? (
            <div className="panel-muted">
              <p className="text-sm text-ink-500">No facts match these filters.</p>
            </div>
          ) : (
          <div data-tour="facts-table">
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
                  <th>Evidence pillar</th>
                  <th>Source Document</th>
                  <th>Source Snippet</th>
                  <th title="The model’s own estimate, not a calibrated probability or verification result.">Model confidence</th>
                  <th title="Checked against the cited page: citation, quote, value, validation rules and other sources. Separate from the extraction confidence.">Verification</th>
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
                      {fact.catalogue && <span className="block text-[11px] font-normal text-ink-500 mt-1">{fact.catalogue.type.replace(/_/g, ' ')} · {fact.catalogue.version}</span>}
                      {fact.catalogue?.latest_extraction_presence === 'retained_from_earlier_extraction' && <span className="block text-[11px] text-warning mt-1">Current value not present in latest extraction</span>}
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
                    <td className="font-mono font-semibold text-ink-600 tabular-nums">
                      {(fact.confidence * 100).toFixed(0)}%
                    </td>
                    <td><VerificationCell fact={fact} onOpen={() => setVerifyingFact(fact)} /></td>
                    <td>
                      <span className={statusBadgeClass(fact.status)}>{fact.status}</span>
                      {fact.auto_confirmed && (
                        <span className="block text-[11px] text-ink-500 mt-0.5"
                          title="Confirmed by the system, not a person. Correct or reject it if it is wrong; that is recorded as an override.">
                          {fact.verification?.automation_decision === 'precedent' ? 'auto (earlier decision)'
                            : fact.verification?.automation_decision === 'auto_verified' ? 'auto (all checks passed)'
                              : 'auto (older rule)'}
                        </span>
                      )}
                      <PendingCorrectionNote fact={fact} onChanged={refetch} onError={setActionError} />
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
                        <div className="inline-block text-left text-xs whitespace-normal max-w-xs">
                          <p>Existing evidence request: {fact.open_evidence_request.status_label}</p>
                          <button className="btn-secondary btn-sm mt-1" disabled={actingOnId === fact.id} onClick={() => withdrawRequest(fact)}>Close request and review directly</button>
                        </div>
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
                      {(fact.status === 'confirmed' || fact.status === 'corrected') && !fact.auto_confirmed ? (
                        // A person already decided this value: a change needs another reviewer's approval.
                        !fact.pending_correction && (
                          <button
                            onClick={() => setProposingFor(fact)}
                            className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-ink-700 text-xs font-semibold rounded transition-colors"
                            title="Propose a corrected value with its source; another reviewer approves it."
                          >
                            Propose correction
                          </button>
                        )
                      ) : (
                        <button
                          onClick={() => {
                            setEditingFactId(fact.id);
                            setCorrectionValue(String(fact.value_json));
                          }}
                          className="px-2.5 py-1 bg-line-200 hover:bg-line-300 text-ink-700 text-xs font-semibold rounded transition-colors"
                        >
                          Correct
                        </button>
                      )}
                      <Link to={`/sprint/${sprintId}/upload?fact=${fact.id}`} className="px-2.5 py-1 text-accent text-xs font-semibold">Upload supporting evidence</Link>
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
          </div>
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
