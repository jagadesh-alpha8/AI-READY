import { useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import type { Resource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { getRecommendation, updateRecommendation } from '../services/recommendations';
import type { Recommendation } from '../types/api';
import { humanize, num } from '../utils/format';
import { ActionDialog, Empty, ErrorState, Loading, Notice, Pill, Table } from './ui';

/**
 * The sprint's audit recommendations with InGage staff's edit and status controls (PATCH /recommendations/{id}).
 * Hidden ones are listed only on request.
 */
export function AuditRecommendationTable({ recs }: { recs: Resource<Recommendation[]> }) {
  const { staff } = useAccess();
  const [editing, setEditing] = useState<Recommendation | null>(null);
  const [showHidden, setShowHidden] = useState(false);
  const { busy, msg, setMsg, run } = useRunner();
  const list = (recs.data || []).filter((r) => showHidden || r.status !== 'hidden');
  const hidden = (recs.data || []).length - (recs.data || []).filter((r) => r.status !== 'hidden').length;

  const open = (r: Recommendation) => run(`get:${r.id}`, async () => setEditing((await getRecommendation(r.id)).data));
  const setStatus = (r: Recommendation, status: Recommendation['status']) =>
    run(`st:${r.id}`, async () => { await updateRecommendation(r.id, { status }); await recs.refetch(); }, `${r.title}: ${humanize(status)}.`);

  if (recs.loading && !recs.data) return <Loading />;
  if (recs.error) return <ErrorState error={recs.error} onRetry={() => void recs.refetch()} />;
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {!list.length ? <Empty title="No recommendations yet" /> : (
        <Table columns={['Recommendation', 'Pillar', 'Priority', 'Timeline', 'Expected lift', 'Status', ...(staff ? [''] : [])]}>
          {list.map((r) => (
            <tr key={r.id}>
              <td><strong>{r.title}</strong><small className="cell-sub clamp-2">{r.description || r.trigger_gap}</small></td>
              <td>{r.pillar_label}</td>
              <td><Pill status={r.priority} /></td>
              <td>{r.timeline || '—'}</td>
              <td>+{num(r.expected_cri_lift, 1)}</td>
              <td><Pill status={r.status} /></td>
              {staff && (
                <td>
                  <div className="row-actions">
                    <button className="secondary-button" disabled={!!busy} onClick={() => void open(r)}>Edit</button>
                    {r.status !== 'accepted' && r.status !== 'completed' && <button className="secondary-button" disabled={!!busy} onClick={() => void setStatus(r, 'accepted')}>Accept</button>}
                    {r.status === 'accepted' && <button className="secondary-button" disabled={!!busy} onClick={() => void setStatus(r, 'completed')}>Complete</button>}
                    {r.status !== 'hidden'
                      ? <button className="secondary-button" disabled={!!busy} onClick={() => void setStatus(r, 'hidden')}>Hide</button>
                      : <button className="secondary-button" disabled={!!busy} onClick={() => void setStatus(r, 'draft')}>Unhide</button>}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </Table>
      )}
      {staff && hidden > 0 && (
        <button className="link-button" onClick={() => setShowHidden(!showHidden)}>{showHidden ? 'Hide hidden recommendations' : `Show ${hidden} hidden`}</button>
      )}
      {editing && (
        <ActionDialog title="Edit recommendation" confirmLabel="Save"
          fields={[
            { name: 'title', label: 'Title', required: true, initial: editing.title },
            { name: 'description', label: 'Description', type: 'textarea', initial: editing.description },
            { name: 'priority', label: 'Priority', type: 'select', required: true, initial: editing.priority, options: ['blocking', 'high', 'medium', 'optional'].map((v) => ({ value: v, label: humanize(v) })) },
            { name: 'timeline', label: 'Timeline', initial: editing.timeline },
            { name: 'expected_cri_lift', label: 'Expected CRI lift', type: 'number', initial: String(editing.expected_cri_lift) },
            { name: 'consultant_notes', label: 'Consultant notes', type: 'textarea' },
          ]}
          onSubmit={async (v) => {
            await updateRecommendation(editing.id, {
              title: v.title, description: v.description, priority: v.priority as Recommendation['priority'], timeline: v.timeline,
              expected_cri_lift: Number(v.expected_cri_lift), consultant_notes: v.consultant_notes || undefined,
            });
            await recs.refetch();
            setMsg({ tone: 'success', text: 'Recommendation saved.' });
          }}
          onClose={() => setEditing(null)} />
      )}
    </>
  );
}
