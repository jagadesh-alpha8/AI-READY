import { Dummy, Empty, ErrorState, Loading, PageHeading, PageLink, Pill, Stat, Table } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { getEvidenceRequestSummary, listEvidenceRequests } from '../services/evidenceRequests';
import type { EvidenceRequest, EvidenceRequestSummary } from '../types/api';
import { date } from '../utils/format';

const PREFERENCES = [
  ['Evidence reminders', 'Owner reminders before and after request due dates.', 'Enabled'],
  ['Review queue alerts', 'New, ageing and escalated evidence for reviewers.', 'Enabled'],
  ['Goal and task alerts', 'Milestones, overdue work and closure requests.', 'Enabled'],
  ['Executive summaries', 'Weekly progress, risks and decisions.', 'Every Monday'],
  ['Benchmark updates', 'Source or benchmark changes that affect assessments.', 'Administrators'],
  ['Security notifications', 'Access, processing and audit-log events.', 'Immediate'],
];

/** What needs the user's attention now (real data), and notification preferences (not in the backend yet). */
export function Notifications() {
  const summary = useResource<EvidenceRequestSummary>(getEvidenceRequestSummary, 'er-summary');
  const overdue = useResource<EvidenceRequest[]>(() => listEvidenceRequests({ overdue: true, unresolved: true }), 'er-overdue');

  return (
    <>
      <PageHeading page="notifications" />
      <div className="stat-grid">
        <Stat label="Assigned to me" value={summary.data?.assigned_to_me ?? '—'} note="Evidence requests" />
        <Stat label="Mine overdue" value={summary.data?.assigned_to_me_overdue ?? '—'} note="Past the due date" />
        <Stat label="Awaiting my review" value={summary.data?.awaiting_my_review ?? '—'} note="Evidence submitted" />
        <Stat label="Overdue (all)" value={overdue.data?.length ?? '—'} note="Across visible sprints" />
      </div>
      <h2 className="section-title">Overdue requests</h2>
      {overdue.loading ? <Loading /> : overdue.error ? <ErrorState error={overdue.error} onRetry={() => void overdue.refetch()} /> :
        !overdue.data?.length ? <Empty title="Nothing overdue" /> : (
          <Table columns={['Request', 'Sprint', 'Owner', 'Due', 'Status']}>
            {overdue.data.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.fact_field_name}</strong><small className="cell-sub">{r.evidence_needed}</small></td>
                <td>{r.sprint_code}</td>
                <td>{r.assigned_to_name || r.responsible_role || 'Unassigned'}</td>
                <td>{date(r.due_date)}</td>
                <td><Pill status={r.status} label={r.status_label} /></td>
              </tr>
            ))}
          </Table>
        )}
      <div className="button-row spaced"><PageLink to="requests">Open data requests</PageLink></div>
      <Dummy title="Notification preferences" note="The backend sends invitation and password emails only; it has no reminder schedule or preference API yet. These switches are not saved.">
        <div className="feature-grid">
          {PREFERENCES.map(([title, text, state], i) => (
            <article key={title} className="feature-card muted-card">
              <div className="feature-icon">{String(i + 1).padStart(2, '0')}</div>
              <h3>{title}</h3><p>{text}</p>
              <div className="feature-meta"><span>{state}</span><label className="toggle"><input type="checkbox" defaultChecked disabled /> On</label></div>
            </article>
          ))}
        </div>
      </Dummy>
    </>
  );
}
