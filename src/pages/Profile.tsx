import { useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Dummy, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { getCollegeProfile } from '../services/assessments';
import { previewApplicability } from '../services/benchmarks';
import { getInstitution, listDepartments, listSystems, updateInstitution } from '../services/institutions';
import type { ApplicabilityPreview, CollegeProfile, Department, InstitutionDetail, InstitutionSystem, Sprint } from '../types/api';
import { errorMessage } from '../utils/errors';
import { date, humanize } from '../utils/format';

export function Profile() {
  return <RequireSprint>{(sprint) => <ProfileBody sprint={sprint} />}</RequireSprint>;
}

function ProfileBody({ sprint }: { sprint: Sprint }) {
  const id = sprint.institution_id;
  const { can, staff } = useAccess();
  const inst = useResource<InstitutionDetail>(() => getInstitution(id), id);
  const depts = useResource<Department[]>(() => listDepartments(id), id);
  const systems = useResource<InstitutionSystem[]>(() => listSystems(id), id);
  const profile = useResource<CollegeProfile>(() => getCollegeProfile(id), id);
  const applicability = useResource<ApplicabilityPreview>(() => previewApplicability(id), id, staff);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);

  if (inst.loading) return <Loading label="Loading the institution profile…" />;
  if (inst.error) return <ErrorState error={inst.error} onRetry={() => void inst.refetch()} />;
  const i = inst.data!;
  const p = profile.data?.profile;

  return (
    <>
      <PageHeading page="profile" actions={can('institution.edit') && !editing && <button className="primary-action" onClick={() => setEditing(true)}>Edit profile</button>} />
      {saved && <Notice tone="success" onClose={() => setSaved(false)}>Institution profile saved.</Notice>}
      {editing && <EditForm inst={i} onCancel={() => setEditing(false)} onSaved={(d) => { inst.setData(d); setEditing(false); setSaved(true); }} />}
      <div className="feature-grid">
        <Panel title="Institution identity" sub="Affiliation, autonomy, accreditation and location">
          <dl className="kv">
            <dt>Name</dt><dd>{i.name}</dd>
            <dt>Type</dt><dd>{i.institution_type || '—'}</dd>
            <dt>Affiliation</dt><dd>{i.university_affiliation || '—'}</dd>
            <dt>Accreditation</dt><dd>{i.accreditation_details || '—'}</dd>
            <dt>Location</dt><dd>{[i.city, i.state, i.country].filter(Boolean).join(', ') || '—'}</dd>
            <dt>Leaders</dt><dd>{i.leaders.length ? i.leaders.map((l) => `${l.name} (${l.role})`).join(', ') : '—'}</dd>
          </dl>
        </Panel>
        <Panel title="Academic portfolio" sub="Programmes, departments and student counts">
          <dl className="kv">
            <dt>Students</dt><dd>{i.student_count ?? '—'}</dd>
            <dt>Faculty</dt><dd>{i.faculty_count ?? '—'}</dd>
            <dt>Departments</dt><dd>{i.department_count}</dd>
            <dt>Programmes</dt><dd>{i.program_count}</dd>
          </dl>
          {depts.data && depts.data.length > 0 && (
            <ul className="plain-list">{depts.data.slice(0, 6).map((d) => <li key={d.id}>{d.name} · {d.program_count} programmes</li>)}</ul>
          )}
        </Panel>
        <Panel title="Regulatory applicability" sub="Benchmark profile used by assessments">
          {profile.loading ? <Loading /> : profile.error ? <ErrorState error={profile.error} /> : !p ? (
            <p className="muted">No benchmark profile is saved yet. InGage staff save it before an assessment cycle.</p>
          ) : (
            <dl className="kv">
              <dt>Institution type</dt><dd>{p.institution_type_name}</dd>
              <dt>Autonomy</dt><dd>{humanize(p.autonomous_status)}</dd>
              <dt>Regulators</dt><dd>{p.approval_bodies.join(', ') || '—'}</dd>
              <dt>Jurisdiction</dt><dd>{p.jurisdiction || '—'}</dd>
              <dt>Programmes</dt><dd>{profile.data!.programmes.length}</dd>
              <dt>Updated</dt><dd>{date(p.updated_at)}</dd>
            </dl>
          )}
        </Panel>
        <Panel title="Technology landscape" sub="Core platforms and data systems">
          {systems.loading ? <Loading /> : !systems.data?.length ? <p className="muted">No systems recorded.</p> : (
            <ul className="plain-list">{systems.data.map((s) => <li key={s.id}>{s.name} {s.tag && <Pill status={s.tag === 'legacy' ? 'at_risk' : 'pending'} label={s.tag_label} />}</li>)}</ul>
          )}
        </Panel>
        <Panel title="Strategic context" sub="Priorities, current AI use, digital maturity">
          <dl className="kv">
            <dt>Priorities</dt><dd>{i.priorities.length ? i.priorities.join(', ') : '—'}</dd>
            <dt>Current AI use</dt><dd>{i.current_ai_usage || '—'}</dd>
            <dt>Digital maturity</dt><dd>{i.digital_maturity_label || '—'}</dd>
          </dl>
          <Dummy title="Investment appetite and constraints" note="No backend fields for budget, procurement or leadership ambition yet.">
            <dl className="kv"><dt>Investment appetite</dt><dd>Medium, staged</dd><dt>Procurement</dt><dd>Annual cycle, April</dd><dt>Ambition</dt><dd>Gold within 12 months</dd></dl>
          </Dummy>
        </Panel>
        <Panel title="Assessment scope" sub="Units, period and benchmark applicability">
          <dl className="kv">
            <dt>Sprint</dt><dd>{sprint.name || sprint.sprint_code}</dd>
            <dt>Academic year</dt><dd>{sprint.academic_year || '—'}</dd>
            <dt>Scope</dt><dd>{sprint.description || '—'}</dd>
          </dl>
          {staff && applicability.data && (
            <p className="muted">Applicability: {Object.entries(applicability.data.counts).map(([k, v]) => `${humanize(k)} ${v}`).join(' · ') || applicability.data.detail}</p>
          )}
        </Panel>
      </div>
      {staff && applicability.data && applicability.data.benchmarks.length > 0 && (
        <>
          <h2 className="section-title">Applicability with reasons</h2>
          <Table columns={['Benchmark', 'Pillar', 'Result', 'Reason']}>
            {applicability.data.benchmarks.map((b) => (
              <tr key={b.benchmark_code}><td><strong>{b.benchmark_code}</strong> {b.title}</td><td>{b.pillar_code}</td><td><Pill status={b.result} /></td><td>{b.reason}</td></tr>
            ))}
          </Table>
        </>
      )}
    </>
  );
}

function EditForm({ inst, onCancel, onSaved }: { inst: InstitutionDetail; onCancel: () => void; onSaved: (d: InstitutionDetail) => void }) {
  const [form, setForm] = useState({
    name: inst.name, institution_type: inst.institution_type, affiliation: inst.university_affiliation,
    city: inst.city, state: inst.state, accreditation_details: inst.accreditation_details, current_ai_usage: inst.current_ai_usage,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try { onSaved((await updateInstitution(inst.id, form)).data); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <Panel title="Edit institution profile">
      <form className="form-grid" onSubmit={submit}>
        <label className="field span-2"><span>Name *</span><input required value={form.name} onChange={set('name')} /></label>
        <label className="field"><span>Institution type</span><input value={form.institution_type} onChange={set('institution_type')} /></label>
        <label className="field"><span>Affiliation</span><input value={form.affiliation} onChange={set('affiliation')} /></label>
        <label className="field"><span>City</span><input value={form.city} onChange={set('city')} /></label>
        <label className="field"><span>State</span><input value={form.state} onChange={set('state')} /></label>
        <label className="field span-2"><span>Accreditation</span><input value={form.accreditation_details} onChange={set('accreditation_details')} /></label>
        <label className="field span-2"><span>Current AI use</span><textarea rows={2} value={form.current_ai_usage} onChange={set('current_ai_usage')} /></label>
        {error && <div className="span-2"><Notice tone="error">{error}</Notice></div>}
        <div className="button-row span-2">
          <button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>
          <button className="primary-action" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Panel>
  );
}
