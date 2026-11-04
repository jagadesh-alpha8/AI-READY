import { useState, type FormEvent } from 'react';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { createInstitution, listInstitutions, resendCoordinatorInvitation } from '../services/institutions';
import { createSprint, updateSprint } from '../services/sprints';
import { Empty, ErrorState, Loading, Notice, PageHeading, PageLink, Panel, Pill, Table } from '../components/ui';
import type { Institution } from '../types/api';
import { errorMessage } from '../utils/errors';
import { date } from '../utils/format';

type Msg = { tone: 'success' | 'error'; text: string } | null;

/** Four steps: create the workspace, confirm scope (the sprint), invite the core team, schedule the kickoff. */
export function Onboarding() {
  const { can } = useAccess();
  const { sprint, reload, select } = useSprint();
  const institutions = useResource<Institution[]>(listInstitutions, 'institutions');
  const [institutionId, setInstitutionId] = useState('');
  const [msg, setMsg] = useState<Msg>(null);
  const chosen = institutionId || sprint?.institution_id || institutions.data?.[0]?.id || '';
  const institution = institutions.data?.find((i) => i.id === chosen);

  return (
    <>
      <PageHeading page="onboarding" />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="step-grid">
        <Panel title="1 · Create institution workspace" sub="Customer identity, institution type and IQAC Coordinator">
          {can('institution.create') ? (
            <CreateInstitutionForm onDone={(i, sent) => {
              setMsg({ tone: 'success', text: `${i.name} was created. ${sent ? 'The coordinator invitation was emailed.' : 'The invitation email could not be sent; resend it in step 3.'}` });
              setInstitutionId(i.id);
              void institutions.refetch();
            }} onError={(text) => setMsg({ tone: 'error', text })} />
          ) : (
            <p className="muted">InGage staff create the institution workspace and invite its IQAC Coordinator. Your institution is listed below.</p>
          )}
        </Panel>

        <Panel title="2 · Confirm assessment scope" sub="An audit sprint scopes the period and evidence collection">
          {!institution ? <p className="muted">Create or choose an institution first.</p> : can('sprint.manage') ? (
            <CreateSprintForm institution={institution} onDone={async (id) => {
              await reload();
              select(id);
              setMsg({ tone: 'success', text: 'The audit sprint was created in Draft. Upload evidence to start collecting.' });
            }} onError={(text) => setMsg({ tone: 'error', text })} />
          ) : <p className="muted">Your role cannot create sprints.</p>}
        </Panel>

        <Panel title="3 · Invite the core team" sub="The IQAC Coordinator activates the college's access">
          {!institution ? <p className="muted">Choose an institution first.</p> : (
            <>
              <dl className="kv">
                <dt>Coordinator</dt><dd>{institution.coordinator?.name || '—'} {institution.coordinator?.email && `(${institution.coordinator.email})`}</dd>
                <dt>Invitation</dt><dd>{institution.coordinator ? <Pill status={institution.coordinator.state} label={institution.coordinator.state_label} /> : '—'}</dd>
              </dl>
              <div className="button-row">
                {can('institution.create') && institution.coordinator?.can_resend && (
                  <button className="secondary-button" onClick={async () => {
                    try {
                      await resendCoordinatorInvitation(institution.id);
                      setMsg({ tone: 'success', text: 'Invitation sent again.' });
                      void institutions.refetch();
                    } catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
                  }}>Resend invitation</button>
                )}
                <PageLink to="team">People & roles</PageLink>
              </div>
            </>
          )}
        </Panel>

        <Panel title="4 · Schedule kickoff" sub="Agree sprint dates and responsibilities">
          {!sprint ? <p className="muted">Create a sprint first.</p> : can('sprint.manage') ? (
            <ScheduleForm key={sprint.id} sprintId={sprint.id} start={sprint.start_date} end={sprint.target_completion_date}
              onDone={async () => { await reload(); setMsg({ tone: 'success', text: 'Sprint dates saved.' }); }}
              onError={(text) => setMsg({ tone: 'error', text })} />
          ) : <p className="muted">Sprint dates: {date(sprint.start_date)} to {date(sprint.target_completion_date)}</p>}
        </Panel>
      </div>

      <h2 className="section-title">Institutions</h2>
      {institutions.loading ? <Loading /> : institutions.error ? <ErrorState error={institutions.error} onRetry={() => void institutions.refetch()} /> :
        !institutions.data?.length ? <Empty title="No institutions yet">Create the first institution workspace above.</Empty> : (
          <Table columns={['Institution', 'Type', 'Location', 'Sprints', 'Coordinator', '']}>
            {institutions.data.map((i) => (
              <tr key={i.id} className={i.id === chosen ? 'selected' : ''}>
                <td><strong>{i.name}</strong></td>
                <td>{i.institution_type || '—'}</td>
                <td>{[i.city, i.state].filter(Boolean).join(', ') || '—'}</td>
                <td>{i.sprint_count}</td>
                <td>{i.coordinator ? <Pill status={i.coordinator.state} label={i.coordinator.state_label} /> : '—'}</td>
                <td><button className="secondary-button" onClick={() => setInstitutionId(i.id)} disabled={i.id === chosen}>{i.id === chosen ? 'Selected' : 'Choose'}</button></td>
              </tr>
            ))}
          </Table>
        )}
    </>
  );
}

function CreateInstitutionForm({ onDone, onError }: { onDone: (i: Institution, sent: boolean) => void; onError: (t: string) => void }) {
  const [form, setForm] = useState({ name: '', institution_type: '', city: '', state: '', affiliation: '', coordinator_name: '', coordinator_email: '' });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await createInstitution(form);
      onDone(res.data, res.data.invitation_email_sent);
      setForm({ name: '', institution_type: '', city: '', state: '', affiliation: '', coordinator_name: '', coordinator_email: '' });
    } catch (err) { onError(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="field span-2"><span>Legal name *</span><input required value={form.name} onChange={set('name')} /></label>
      <label className="field"><span>Institution type</span><input value={form.institution_type} onChange={set('institution_type')} placeholder="e.g. Engineering college" /></label>
      <label className="field"><span>Affiliation</span><input value={form.affiliation} onChange={set('affiliation')} placeholder="University / autonomous" /></label>
      <label className="field"><span>City</span><input value={form.city} onChange={set('city')} /></label>
      <label className="field"><span>State</span><input value={form.state} onChange={set('state')} /></label>
      <label className="field"><span>IQAC Coordinator name *</span><input required value={form.coordinator_name} onChange={set('coordinator_name')} /></label>
      <label className="field"><span>Coordinator email *</span><input required type="email" value={form.coordinator_email} onChange={set('coordinator_email')} /></label>
      <button className="primary-action span-2" disabled={busy}>{busy ? 'Creating…' : 'Create workspace and invite'}</button>
    </form>
  );
}

function CreateSprintForm({ institution, onDone, onError }: { institution: Institution; onDone: (id: string) => Promise<void>; onError: (t: string) => void }) {
  const [form, setForm] = useState({ name: '', academic_year: '', description: '' });
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await createSprint({ institution_id: institution.id, ...form });
      await onDone(res.data.id);
      setForm({ name: '', academic_year: '', description: '' });
    } catch (err) { onError(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <form className="form-grid" onSubmit={submit}>
      <p className="muted span-2">For <b>{institution.name}</b></p>
      <label className="field"><span>Sprint name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="AI readiness audit" /></label>
      <label className="field"><span>Academic year</span><input value={form.academic_year} onChange={(e) => setForm({ ...form, academic_year: e.target.value })} placeholder="2026-27" /></label>
      <label className="field span-2"><span>Scope and purpose</span><textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Campuses, programmes, period, exclusions" /></label>
      <button className="primary-action span-2" disabled={busy}>{busy ? 'Creating…' : 'Create audit sprint'}</button>
    </form>
  );
}

function ScheduleForm({ sprintId, start, end, onDone, onError }: {
  sprintId: string; start: string | null; end: string | null; onDone: () => Promise<void>; onError: (t: string) => void;
}) {
  const [s, setS] = useState(start || '');
  const [t, setT] = useState(end || '');
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await updateSprint(sprintId, { start_date: s || null, target_completion_date: t || null });
      await onDone();
    } catch (err) { onError(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="field"><span>Kickoff / start</span><input type="date" value={s} onChange={(e) => setS(e.target.value)} /></label>
      <label className="field"><span>Target completion</span><input type="date" value={t} onChange={(e) => setT(e.target.value)} /></label>
      <button className="primary-action span-2" disabled={busy}>{busy ? 'Saving…' : 'Save schedule'}</button>
    </form>
  );
}
