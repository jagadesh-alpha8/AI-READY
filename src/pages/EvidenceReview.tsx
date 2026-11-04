import { useState } from 'react';
import { FactDetailDialog } from '../components/FactDetail';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Pager, Pill, Stat, Table, type DialogField } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { confirmFact, correctFact, getSprintFactFacets, listSprintFactsPage, rejectFact, requestFactEvidence } from '../services/facts';
import type { Fact, FactFacets, Page, Sprint } from '../types/api';
import { pct, valueText } from '../utils/format';

const PAGE_SIZE = 20;

type Decision = 'approve' | 'reject' | 'edit' | 'insufficient';

const DIALOGS: Record<Decision, { title: string; confirm: string; danger?: boolean; fields: (f: Fact) => DialogField[] }> = {
  approve: { title: 'Approve evidence', confirm: 'Approve', fields: () => [{ name: 'reason', label: 'Decision reason', type: 'textarea', required: true, initial: 'Matches the source document.' }] },
  reject: { title: 'Reject evidence', confirm: 'Reject', danger: true, fields: () => [{ name: 'reason', label: 'Why is it rejected?', type: 'textarea', required: true }] },
  edit: { title: 'Correct the value', confirm: 'Save correction', fields: (f) => [
    { name: 'value', label: 'Correct value', required: true, initial: valueText(f.value) },
    { name: 'reason', label: 'Reason (the previous value is kept in history)', type: 'textarea', required: true },
  ] },
  insufficient: { title: 'Mark evidence insufficient', confirm: 'Request evidence', fields: () => [
    { name: 'evidence_needed', label: 'What evidence is needed?', type: 'textarea', required: true },
    { name: 'reason', label: 'Why is the current evidence insufficient?', type: 'textarea', required: true },
  ] },
};

/** Reviewers approve, reject, edit or mark evidence insufficient; each decision is kept with reviewer, time and reason. */
export function EvidenceReview() {
  return <RequireSprint>{(sprint) => <ReviewBody sprint={sprint} />}</RequireSprint>;
}

function ReviewBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const [page, setPage] = useState(1);
  const facets = useResource<FactFacets>(() => getSprintFactFacets(sprint.id), sprint.id);
  const queue = useResource<Page<Fact>>(() => listSprintFactsPage(sprint.id, { status: 'extracted', page, page_size: PAGE_SIZE, ordering: 'confidence_score' }), `${sprint.id}:${page}`);
  const [action, setAction] = useState<{ fact: Fact; decision: Decision } | null>(null);
  const [viewing, setViewing] = useState<Fact | null>(null);
  const [done, setDone] = useState('');

  const decide = async (fact: Fact, decision: Decision, v: Record<string, string>) => {
    if (decision === 'approve') await confirmFact(fact.id, v.reason);
    else if (decision === 'reject') await rejectFact(fact.id, v.reason);
    else if (decision === 'edit') await correctFact(fact.id, v.value, v.reason);
    else await requestFactEvidence(fact.id, v.evidence_needed, v.reason);
    setDone(`${fact.field_name}: decision recorded.`);
    void queue.refetch();
    void facets.refetch();
  };

  /** Approve / Edit / Insufficient / Reject on one row; the same buttons appear in the full-fact view. */
  const decisionButtons = (f: Fact, before?: () => void) => {
    if (!can('facts.review')) return <span className="muted">View only</span>;
    if (f.can_act === false) return <span className="muted" title={f.act_blocked_reason}>{f.act_blocked_reason || 'Another role decides this'}</span>;
    const open = (decision: Decision) => { before?.(); setAction({ fact: f, decision }); };
    return (
      <div className="row-actions nowrap">
        <button className="primary-action small" onClick={() => open('approve')}>Approve</button>
        <button className="secondary-button" onClick={() => open('edit')}>Edit</button>
        <button className="secondary-button" onClick={() => open('insufficient')}>Insufficient</button>
        <button className="secondary-button danger-text" onClick={() => open('reject')}>Reject</button>
      </div>
    );
  };

  const s = facets.data?.status || {};
  return (
    <>
      <PageHeading page="review" actions={<PageLink to="gaps">Open contradictions</PageLink>} />
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      <div className="stat-grid">
        <Stat label="Review queue" value={facets.data ? s.extracted || 0 : '—'} note="Extracted, undecided" />
        <Stat label="Approved" value={facets.data ? s.confirmed || 0 : '—'} note="Confirmed" />
        <Stat label="Edited" value={facets.data ? s.corrected || 0 : '—'} note="Corrected, history kept" />
        <Stat label="Rejected / insufficient" value={facets.data ? (s.rejected || 0) + (s.evidence_requested || 0) : '—'} note="Not used in scoring" />
      </div>
      {queue.loading && !queue.data ? <Loading /> : queue.error ? <ErrorState error={queue.error} onRetry={() => void queue.refetch()} /> :
        !queue.data?.results.length ? <Empty title="The review queue is empty">Every extracted fact has a decision. Run the assessment next.</Empty> : (
          <>
            <Table columns={['Review queue', 'Suggested fact', 'Issue', 'Confidence', 'Decision']}>
              {queue.data.results.map((f) => (
                <tr key={f.id}>
                  <td className="source-cell">{f.source_document_filename || 'No source'}{f.source_page && `, page ${f.source_page}`}</td>
                  <td>
                    <strong>{f.field_name}</strong>
                    <small className="cell-sub clamp-2" title={valueText(f.value)}>{valueText(f.value)}</small>
                    <button className="link-button" onClick={() => setViewing(f)}>View full fact</button>
                  </td>
                  <td>{f.verification ? <Pill status={f.verification.status} label={f.verification.status_label} /> : 'Not verified yet'}</td>
                  <td>{pct(f.confidence_score)}</td>
                  <td className="decision-cell">{decisionButtons(f)}</td>
                </tr>
              ))}
            </Table>
            <Pager page={page} count={queue.data.count} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}
      {viewing && (
        <FactDetailDialog fact={viewing} onClose={() => setViewing(null)} actions={(f) => decisionButtons(f, () => setViewing(null))} />
      )}
      {action && (
        <ActionDialog
          title={DIALOGS[action.decision].title}
          description={<><b>{action.fact.field_name}</b>: {valueText(action.fact.value)}{action.fact.source_snippet && <blockquote>{action.fact.source_snippet}</blockquote>}</>}
          fields={DIALOGS[action.decision].fields(action.fact)}
          confirmLabel={DIALOGS[action.decision].confirm}
          danger={DIALOGS[action.decision].danger}
          onSubmit={(v) => decide(action.fact, action.decision, v)}
          onClose={() => setAction(null)}
        />
      )}
    </>
  );
}
