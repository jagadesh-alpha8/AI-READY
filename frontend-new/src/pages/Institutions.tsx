import { useState } from 'react';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Stat, Table, type DialogField } from '../components/ui';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import {
  archiveInstitution, createDepartment, createLeader, createSystem, deleteDepartment, deleteInstitution, deleteLeader, deleteSystem,
  getCoordinator, getDeletionPreview, getInstitution, listDepartments, listInstitutions, listLeaders, listSystems, resendCoordinatorInvitation,
  setCoordinator, unarchiveInstitution, updateDepartment, updateLeader, updateSystem,
} from '../services/institutions';
import { getDashboard } from '../services/sprints';
import type {
  CoordinatorStatus, DashboardData, Department, Institution, InstitutionDetail, InstitutionLeader, InstitutionSystem,
} from '../types/api';
import type { InstitutionDeletionPreview } from '../types/workflow';
import { humanize, num, rows } from '../utils/format';

export function Institutions() {
  const dash = useResource<DashboardData>(getDashboard, 'dashboard');
  const list = useResource<Institution[]>(listInstitutions, 'institutions');
  const [chosen, setChosen] = useState('');
  const d = dash.data;
  return (
    <>
      <PageHeading page="institutions" actions={<PageLink to="onboarding" className="primary-action">Onboard an institution</PageLink>} />
      {d && (
        <div className="stat-grid">
          <Stat label="Institutions" value={d.institution_count} note={`${d.sprint_count} sprints`} />
          <Stat label="Active sprints" value={d.active_sprints} note={`${d.completion_percentage}% average completion`} />
          <Stat label="Pending confirmations" value={num(d.pending_confirmations)} note={`${d.high_priority_gaps} high-priority gaps`} />
          <Stat label="Reports ready" value={d.reports_ready} />
        </div>
      )}
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> :
        !list.data?.length ? <Empty title="No institutions yet" /> : (
          <Table columns={['Institution', 'Location', 'Sprints', 'Coordinator', 'Status', '']}>
            {list.data.map((i) => (
              <tr key={i.id} aria-selected={i.id === chosen}>
                <td><strong>{i.name}</strong><small className="cell-sub">{humanize(i.institution_type)}</small></td>
                <td>{[i.city, i.state].filter(Boolean).join(', ') || '—'}</td>
                <td>{i.sprint_count}</td>
                <td>{i.coordinator ? `${i.coordinator.name || i.coordinator.email} · ${i.coordinator.state_label}` : '—'}</td>
                <td><Pill status={i.is_active ? 'active' : 'neutral'} label={i.is_active ? 'Active' : 'Archived'} /></td>
                <td><button className="secondary-button" onClick={() => setChosen(i.id === chosen ? '' : i.id)}>{i.id === chosen ? 'Close' : 'Manage'}</button></td>
              </tr>
            ))}
          </Table>
        )}
      {d && rows(d.sprints).length > 0 && (
        <Panel title="Sprints across institutions">
          <Table columns={['Institution', 'Sprint', 'Status', 'Completion', 'CRI', 'Open gaps']}>
            {rows(d.sprints).map((s) => (
              <tr key={s.id}><td>{s.institution}</td><td>{s.name}</td><td><Pill status={s.status} /></td><td>{s.completion}%</td><td>{s.cri ?? '—'}</td><td>{s.pending_gaps}</td></tr>
            ))}
          </Table>
        </Panel>
      )}
      {chosen && <Manage id={chosen} onChanged={() => void list.refetch()} onGone={() => { setChosen(''); void list.refetch(); }} />}
    </>
  );
}

type Edit =
  | { kind: 'coordinator' } | { kind: 'delete'; preview: InstitutionDeletionPreview }
  | { kind: 'dept'; item?: Department } | { kind: 'system'; item?: InstitutionSystem } | { kind: 'leader'; item?: InstitutionLeader };

function Manage({ id, onChanged, onGone }: { id: string; onChanged: () => void; onGone: () => void }) {
  const { role } = useAccess();
  const { reload } = useSprint();
  const inst = useResource<InstitutionDetail>(() => getInstitution(id), `inst:${id}`);
  const coord = useResource<CoordinatorStatus>(() => getCoordinator(id), `coord:${id}`);
  const depts = useResource<Department[]>(() => listDepartments(id), `depts:${id}`);
  const systems = useResource<InstitutionSystem[]>(() => listSystems(id), `sys:${id}`);
  const leaders = useResource<InstitutionLeader[]>(() => listLeaders(id), `leaders:${id}`);
  const [edit, setEdit] = useState<Edit | null>(null);
  const { busy, msg, setMsg, run } = useRunner();
  const i = inst.data;

  const fields = (e: Edit): DialogField[] => {
    if (e.kind === 'coordinator') return [
      { name: 'name', label: 'Coordinator name', required: true, initial: coord.data?.name || '' },
      { name: 'email', label: 'Email (a new email sends a new invitation)', type: 'email', required: true, initial: coord.data?.email || '' },
    ];
    if (e.kind === 'dept') return [
      { name: 'name', label: 'Department', required: true, initial: e.item?.name || '' },
      { name: 'head_name', label: 'Head', initial: e.item?.head_name || '' },
      { name: 'faculty_count', label: 'Faculty', type: 'number', initial: String(e.item?.faculty_count ?? '') },
      { name: 'student_count', label: 'Students', type: 'number', initial: String(e.item?.student_count ?? '') },
      { name: 'program_count', label: 'Programmes', type: 'number', initial: String(e.item?.program_count ?? '') },
    ];
    if (e.kind === 'system') return [
      { name: 'name', label: 'System', required: true, initial: e.item?.name || '' },
      { name: 'tag', label: 'Tag', type: 'select', initial: e.item?.tag || '', options: [{ value: 'legacy', label: 'Legacy' }, { value: 'manual', label: 'Manual' }] },
      { name: 'notes', label: 'Notes', type: 'textarea', initial: e.item?.notes || '' },
    ];
    if (e.kind === 'leader') return [
      { name: 'name', label: 'Name', required: true, initial: e.item?.name || '' },
      { name: 'role', label: 'Role', required: true, initial: e.item?.role || '' },
      { name: 'email', label: 'Email', type: 'email', initial: e.item?.email || '' },
    ];
    return e.preview.can_delete ? [{ name: 'confirm', label: `Type the name to confirm: ${e.preview.institution_name}`, required: true }] : [];
  };

  const n = (v: string) => (v === '' ? undefined : Number(v));
  const submit = async (e: Edit, v: Record<string, string>) => {
    if (e.kind === 'coordinator') { await setCoordinator(id, v.name, v.email); await coord.refetch(); onChanged(); return setMsg({ tone: 'success', text: 'Coordinator saved.' }); }
    if (e.kind === 'dept') {
      const body = { name: v.name, head_name: v.head_name, faculty_count: n(v.faculty_count), student_count: n(v.student_count), program_count: n(v.program_count) };
      if (e.item) await updateDepartment(id, e.item.id, body); else await createDepartment(id, body);
      await depts.refetch(); return setMsg({ tone: 'success', text: 'Department saved.' });
    }
    if (e.kind === 'system') {
      const body = { name: v.name, tag: v.tag as '' | 'legacy' | 'manual', notes: v.notes };
      if (e.item) await updateSystem(id, e.item.id, body); else await createSystem(id, body);
      await systems.refetch(); return setMsg({ tone: 'success', text: 'System saved.' });
    }
    if (e.kind === 'leader') {
      const body = { name: v.name, role: v.role, email: v.email };
      if (e.item) await updateLeader(id, e.item.id, body); else await createLeader(id, body);
      await leaders.refetch(); return setMsg({ tone: 'success', text: 'Leader saved.' });
    }
    if (!e.preview.can_delete) throw new Error(e.preview.block_reason || 'Protected records exist: archive the institution instead.');
    if (v.confirm.trim() !== e.preview.institution_name) throw new Error('The name does not match.');
    await deleteInstitution(id);
    await reload();
    onGone();
  };

  const remove = (label: string, fn: () => Promise<unknown>, refetch: () => Promise<void>) =>
    run(`del:${label}`, async () => { await fn(); await refetch(); }, `${label} removed.`);

  return (
    <Panel title={i ? `Manage ${i.name}` : 'Loading…'} sub={i ? `${i.department_count} departments · ${i.program_count} programmes · ${i.digital_maturity_label || 'maturity not set'}` : undefined}
      actions={i && (
        <div className="row-actions">
          <PageLink to="profile">Edit profile</PageLink>
          {i.is_active
            ? <button className="secondary-button" disabled={!!busy} onClick={() => void run('arch', async () => { await archiveInstitution(id); await inst.refetch(); onChanged(); await reload(); }, 'Institution archived.')}>Archive</button>
            : <button className="secondary-button" disabled={!!busy} onClick={() => void run('unarch', async () => { await unarchiveInstitution(id); await inst.refetch(); onChanged(); await reload(); }, 'Institution restored.')}>Unarchive</button>}
          {role === 'super_admin' && <button className="secondary-button" disabled={!!busy} onClick={() => void run('prev', async () => setEdit({ kind: 'delete', preview: (await getDeletionPreview(id)).data }))}>Delete…</button>}
        </div>
      )}>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {inst.error != null && <ErrorState error={inst.error} />}
      <h3>IQAC Coordinator</h3>
      {coord.loading ? <Loading /> : coord.error ? <ErrorState error={coord.error} /> : (
        <div className="row-actions">
          <span>{coord.data?.configured ? `${coord.data.name} · ${coord.data.email}` : 'Not named yet'}</span>
          {coord.data?.configured && <Pill status={coord.data.state} label={coord.data.state_label} />}
          <button className="secondary-button" onClick={() => setEdit({ kind: 'coordinator' })}>{coord.data?.configured ? 'Change' : 'Name coordinator'}</button>
          {coord.data?.can_resend && <button className="secondary-button" disabled={!!busy} onClick={() => void run('resend', async () => { await resendCoordinatorInvitation(id); await coord.refetch(); }, 'Invitation sent again.')}>Resend invitation</button>}
        </div>
      )}
      <h3>Departments <button className="link-button" onClick={() => setEdit({ kind: 'dept' })}>+ Add</button></h3>
      {depts.loading ? <Loading /> : !depts.data?.length ? <p className="muted">None recorded.</p> : (
        <Table columns={['Department', 'Head', 'Faculty', 'Students', 'Programmes', '']}>
          {depts.data.map((x) => (
            <tr key={x.id}><td>{x.name}</td><td>{x.head_name || '—'}</td><td>{x.faculty_count}</td><td>{x.student_count}</td><td>{x.program_count}</td>
              <td><div className="row-actions nowrap"><button className="secondary-button" onClick={() => setEdit({ kind: 'dept', item: x })}>Edit</button>
                <button className="secondary-button" disabled={!!busy} onClick={() => void remove(x.name, () => deleteDepartment(id, x.id), depts.refetch)}>Remove</button></div></td></tr>
          ))}
        </Table>
      )}
      <h3>Systems <button className="link-button" onClick={() => setEdit({ kind: 'system' })}>+ Add</button></h3>
      {systems.loading ? <Loading /> : !systems.data?.length ? <p className="muted">None recorded.</p> : (
        <Table columns={['System', 'Tag', 'Notes', '']}>
          {systems.data.map((x) => (
            <tr key={x.id}><td>{x.name}</td><td>{x.tag_label || '—'}</td><td>{x.notes || '—'}</td>
              <td><div className="row-actions nowrap"><button className="secondary-button" onClick={() => setEdit({ kind: 'system', item: x })}>Edit</button>
                <button className="secondary-button" disabled={!!busy} onClick={() => void remove(x.name, () => deleteSystem(id, x.id), systems.refetch)}>Remove</button></div></td></tr>
          ))}
        </Table>
      )}
      <h3>Leaders <button className="link-button" onClick={() => setEdit({ kind: 'leader' })}>+ Add</button></h3>
      {leaders.loading ? <Loading /> : !leaders.data?.length ? <p className="muted">None recorded.</p> : (
        <Table columns={['Name', 'Role', 'Email', '']}>
          {leaders.data.map((x) => (
            <tr key={x.id}><td>{x.name}</td><td>{x.role}</td><td>{x.email || '—'}</td>
              <td><div className="row-actions nowrap"><button className="secondary-button" onClick={() => setEdit({ kind: 'leader', item: x })}>Edit</button>
                <button className="secondary-button" disabled={!!busy} onClick={() => void remove(x.name, () => deleteLeader(id, x.id), leaders.refetch)}>Remove</button></div></td></tr>
          ))}
        </Table>
      )}
      {edit && (
        <ActionDialog
          title={edit.kind === 'delete' ? `Delete ${edit.preview.institution_name}?` : edit.kind === 'coordinator' ? 'IQAC Coordinator' : `${'item' in edit && edit.item ? 'Edit' : 'Add'} ${edit.kind === 'dept' ? 'department' : edit.kind}`}
          danger={edit.kind === 'delete'}
          confirmLabel={edit.kind === 'delete' ? 'Delete permanently' : 'Save'}
          description={edit.kind === 'delete' && (
            <>
              {edit.preview.is_blocked || !edit.preview.can_delete
                ? <Notice tone="warn">{edit.preview.block_reason || 'Protected records exist. Archive the institution instead.'}</Notice>
                : <p>This permanently removes the institution and everything below. It cannot be undone.</p>}
              <ul className="plain-list">{Object.entries({ ...edit.preview.dependencies, ...edit.preview.protected_counts }).filter(([, c]) => c > 0).map(([k, c]) => <li key={k}>{humanize(k)}: {c}</li>)}</ul>
            </>
          )}
          fields={fields(edit)}
          onSubmit={(v) => submit(edit, v)}
          onClose={() => setEdit(null)} />
      )}
    </Panel>
  );
}
