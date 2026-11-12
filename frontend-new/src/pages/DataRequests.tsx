import { useState } from 'react';
import { EvidenceRequestDialog } from '../components/EvidenceRequestDetail';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { listEvidenceRequests, submitEvidence } from '../services/evidenceRequests';
import type { EvidenceRequest, Sprint } from '../types/api';
import { date } from '../utils/format';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'unresolved', label: 'Unresolved' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'me', label: 'Assigned to me' },
] as const;

const RESPONDABLE = new Set(['open', 'returned']);

export function DataRequests() {
  return <RequireSprint>{(sprint) => <RequestsBody sprint={sprint} />}</RequireSprint>;
}

function RequestsBody({ sprint }: { sprint: Sprint }) {
  const { user } = useAccess();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('unresolved');
  const all = useResource<EvidenceRequest[]>(() => listEvidenceRequests({ sprint: sprint.id }), sprint.id);
  const [responding, setResponding] = useState<EvidenceRequest | null>(null);
  const [done, setDone] = useState('');
  const [viewing, setViewing] = useState<string | null>(null);

  const list = (all.data || []).filter((r) =>
    filter === 'all' ? true
      : filter === 'unresolved' ? !['accepted', 'accepted_corrected', 'withdrawn'].includes(r.status)
        : filter === 'overdue' ? r.overdue
          : r.assigned_to === user?.id);
  const count = (pred: (r: EvidenceRequest) => boolean) => (all.data || []).filter(pred).length;

  return (
    <>
      <PageHeading page="requests" />
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      <div className="stat-grid">
        <Stat label="Requests" value={all.data ? all.data.length : '—'} note="Raised behind extracted facts" />
        <Stat label="Awaiting response" value={all.data ? count((r) => RESPONDABLE.has(r.status)) : '—'} note="Open or returned" />
        <Stat label="Ready for review" value={all.data ? count((r) => r.status === 'ready_for_review' || r.status === 'submitted') : '—'} note="Evidence submitted" />
        <Stat label="Overdue" value={all.data ? count((r) => r.overdue) : '—'} note="Past the due date" />
      </div>
      <div className="filter-pills" role="tablist" aria-label="Filter requests">
        {FILTERS.map((f) => (
          <button key={f.key} role="tab" aria-selected={filter === f.key} className={filter === f.key ? 'active' : ''} onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
      </div>
      {all.loading ? <Loading /> : all.error ? <ErrorState error={all.error} onRetry={() => void all.refetch()} /> :
        list.length === 0 ? <Empty title="No requests here">Requests are raised from Evidence review when a fact needs more proof.</Empty> : (
          <Table columns={['Request', 'Owner', 'Due', 'Responses', 'Status', '']}>
            {list.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.fact_field_name}</strong><small className="cell-sub">{r.evidence_needed || r.reason}</small></td>
                <td>{r.assigned_to_name || r.responsible_role || 'Unassigned'}</td>
                <td>{date(r.due_date)} {r.overdue && <Pill status="overdue" label="Overdue" />}</td>
                <td>{r.evidence_count} item{r.evidence_count === 1 ? '' : 's'}</td>
                <td><Pill status={r.status} label={r.status_label} /></td>
                <td><div className="row-actions nowrap">
                  <button className="secondary-button" onClick={() => setViewing(r.id)}>Open</button>
                  {RESPONDABLE.has(r.status) && r.assigned_to === user?.id && (
                    <button className="secondary-button" onClick={() => setResponding(r)}>Respond</button>
                  )}
                </div></td>
              </tr>
            ))}
          </Table>
        )}
      {viewing && <EvidenceRequestDialog id={viewing} sprintId={sprint.id} onClose={() => setViewing(null)} onChanged={() => void all.refetch()} />}
      {responding && (
        <ActionDialog
          title={`Respond: ${responding.fact_field_name}`}
          description={responding.evidence_needed}
          confirmLabel="Submit evidence"
          fields={[
            { name: 'file', label: 'Evidence file', type: 'file' },
            { name: 'submitted_text', label: 'Or describe / paste the evidence', type: 'textarea' },
            { name: 'note', label: 'Note to the reviewer', type: 'text' },
          ]}
          onSubmit={async (v, files) => {
            if (!files.file && !v.submitted_text.trim()) throw new Error('Attach a file or enter the evidence text.');
            await submitEvidence(responding.id, { file: files.file, submitted_text: v.submitted_text, note: v.note });
            setDone('Evidence submitted for review.');
            void all.refetch();
          }}
          onClose={() => setResponding(null)}
        />
      )}
    </>
  );
}
