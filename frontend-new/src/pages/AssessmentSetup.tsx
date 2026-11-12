import { useState } from 'react';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Table, Tabs } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import {
  createTemplate, deleteTemplate, getAssessmentReference, getCollegeProfile, listAssessmentColleges, listScoreRules, listTemplates,
  saveCollegeProfile, saveScoreRule, updateTemplate,
} from '../services/assessments';
import type { CollegeProfile } from '../types/api';
import type { AssessmentReference, ScoreRules, TransformationTemplate } from '../types/workflow';
import { date, humanize } from '../utils/format';

const TABS = [
  { key: 'templates', label: 'Plan templates' },
  { key: 'rules', label: 'Score rules' },
  { key: 'profiles', label: 'College profiles' },
] as const;

export function AssessmentSetup() {
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>('templates');
  return (
    <>
      <PageHeading page="assessmentsetup" />
      <Tabs tabs={TABS} value={tab} onChange={setTab} label="Assessment setup" />
      {tab === 'templates' && <Templates />}
      {tab === 'rules' && <Rules />}
      {tab === 'profiles' && <Profiles />}
    </>
  );
}

function Templates() {
  const [benchmark, setBenchmark] = useState('');
  const list = useResource<TransformationTemplate[]>(() => listTemplates(benchmark || undefined), `tpl:${benchmark}`);
  const [editing, setEditing] = useState<TransformationTemplate | 'new' | null>(null);
  const { busy, msg, setMsg, run } = useRunner();
  const t = editing === 'new' ? null : editing;
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="filter-bar">
        <label className="field inline"><span>Benchmark code</span><input value={benchmark} placeholder="All" onChange={(e) => setBenchmark(e.target.value.trim())} /></label>
        <button className="primary-action" onClick={() => setEditing('new')}>New template</button>
      </div>
      {list.loading ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> :
        !list.data?.length ? <Empty title="No templates">Templates turn a gap into an initiative with tasks when a plan is generated.</Empty> : (
          <Table columns={['Benchmark', 'Gap type', 'Template', 'Tasks', 'Updated', '']}>
            {list.data.map((x) => (
              <tr key={x.id}>
                <td>{x.benchmark_code || 'Any'}</td>
                <td>{humanize(x.gap_type)}</td>
                <td><strong>{x.title}</strong><small className="cell-sub clamp-2">{x.intervention}</small></td>
                <td>{x.tasks.length}</td>
                <td>{date(x.updated_at)}</td>
                <td><div className="row-actions nowrap">
                  <button className="secondary-button" onClick={() => setEditing(x)}>Edit</button>
                  <button className="secondary-button" disabled={!!busy} onClick={() => void run(`d:${x.id}`, async () => { await deleteTemplate(x.id); await list.refetch(); }, 'Template deleted.')}>Delete</button>
                </div></td>
              </tr>
            ))}
          </Table>
        )}
      {editing && (
        <ActionDialog title={t ? 'Edit template' : 'New template'} confirmLabel="Save"
          fields={[
            { name: 'benchmark_code', label: 'Benchmark code (blank = any)', initial: t?.benchmark_code || '' },
            { name: 'gap_type', label: 'Gap type', type: 'select', required: true, initial: t?.gap_type || '', options: ['compliance', 'capability', 'evidence', 'outcome', 'dependency'].map((v) => ({ value: v, label: humanize(v) })) },
            { name: 'title', label: 'Title', required: true, initial: t?.title || '' },
            { name: 'intervention', label: 'Intervention', type: 'textarea', required: true, initial: t?.intervention || '' },
            { name: 'expected_evidence', label: 'Expected evidence', type: 'textarea', initial: t?.expected_evidence || '' },
            { name: 'expected_outcome', label: 'Expected outcome', type: 'textarea', initial: t?.expected_outcome || '' },
            { name: 'tasks', label: 'Tasks, one per line', type: 'textarea', initial: (t?.tasks || []).join('\n') },
          ]}
          onSubmit={async (v) => {
            const body = { benchmark_code: v.benchmark_code, gap_type: v.gap_type, title: v.title, intervention: v.intervention,
              expected_evidence: v.expected_evidence, expected_outcome: v.expected_outcome, tasks: v.tasks.split('\n').map((x) => x.trim()).filter(Boolean) };
            if (t) await updateTemplate(t.id, body); else await createTemplate(body);
            await list.refetch();
            setMsg({ tone: 'success', text: 'Template saved.' });
          }}
          onClose={() => setEditing(null)} />
      )}
    </>
  );
}

function Rules() {
  const rules = useResource<ScoreRules>(listScoreRules, 'score-rules');
  const [editing, setEditing] = useState<ScoreRules['rules'][number] | null>(null);
  const [done, setDone] = useState('');
  return (
    <>
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      {rules.loading ? <Loading /> : rules.error ? <ErrorState error={rules.error} onRetry={() => void rules.refetch()} /> : (
        <Panel title="Composite score weights per benchmark" sub={rules.data?.scoring_model ? `Scoring model ${rules.data.scoring_model}` : 'Weights must add up to 1'}>
          <Table columns={['Benchmark', 'Compliance', 'Maturity', 'Evidence', 'Outcome', 'Status', '']}>
            {rules.data!.rules.map((r) => (
              <tr key={r.benchmark_code}>
                <td><strong>{r.benchmark_code}</strong><small className="cell-sub clamp-2">{r.title}</small></td>
                <td>{r.weights?.compliance ?? '—'}</td><td>{r.weights?.maturity ?? '—'}</td><td>{r.weights?.evidence_confidence ?? '—'}</td><td>{r.weights?.outcome ?? '—'}</td>
                <td><Pill status={r.status} />{r.approved_by && <small className="cell-sub">{r.approved_by}</small>}</td>
                <td><button className="secondary-button" onClick={() => setEditing(r)}>Edit</button></td>
              </tr>
            ))}
          </Table>
        </Panel>
      )}
      {editing && (
        <ActionDialog title={`Weights for ${editing.benchmark_code}`} confirmLabel="Save weights"
          fields={[
            { name: 'compliance_weight', label: 'Compliance', type: 'number', required: true, initial: editing.weights?.compliance || '0.25' },
            { name: 'maturity_weight', label: 'Maturity', type: 'number', required: true, initial: editing.weights?.maturity || '0.25' },
            { name: 'evidence_weight', label: 'Evidence confidence', type: 'number', required: true, initial: editing.weights?.evidence_confidence || '0.25' },
            { name: 'outcome_weight', label: 'Outcome', type: 'number', required: true, initial: editing.weights?.outcome || '0.25' },
            { name: 'note', label: 'Reason for the change', type: 'textarea', required: true, initial: '' },
          ]}
          onSubmit={async (v) => {
            const sum = ['compliance_weight', 'maturity_weight', 'evidence_weight', 'outcome_weight'].reduce((n, k) => n + Number(v[k]), 0);
            if (Math.abs(sum - 1) > 0.001) throw new Error(`The weights add up to ${sum.toFixed(3)}; they must add up to 1.`);
            await saveScoreRule(editing.benchmark_code, { compliance_weight: v.compliance_weight, maturity_weight: v.maturity_weight, evidence_weight: v.evidence_weight, outcome_weight: v.outcome_weight, note: v.note });
            await rules.refetch();
            setDone('Weights saved.');
          }}
          onClose={() => setEditing(null)} />
      )}
    </>
  );
}

function Profiles() {
  const colleges = useResource<{ id: string; name: string; city: string; has_profile: boolean }[]>(listAssessmentColleges, 'assess-colleges');
  const ref = useResource<AssessmentReference>(getAssessmentReference, 'assess-ref');
  const [chosen, setChosen] = useState('');
  const profile = useResource<CollegeProfile>(() => getCollegeProfile(chosen), `cp:${chosen}`, !!chosen);
  const [editing, setEditing] = useState(false);
  const [done, setDone] = useState('');
  const p = profile.data;
  const r = ref.data;
  return (
    <>
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      {colleges.loading ? <Loading /> : colleges.error ? <ErrorState error={colleges.error} /> : (
        <Table columns={['College', 'City', 'Profile', '']}>
          {(colleges.data || []).map((c) => (
            <tr key={c.id}><td>{c.name}</td><td>{c.city || '—'}</td><td><Pill status={c.has_profile ? 'active' : 'pending'} label={c.has_profile ? 'Saved' : 'Missing'} /></td>
              <td><button className="secondary-button" onClick={() => setChosen(c.id)}>Open</button></td></tr>
          ))}
        </Table>
      )}
      {chosen && (profile.loading && !p ? <Loading /> : profile.error ? <ErrorState error={profile.error} /> : p && (
        <Panel title={p.institution_name} sub={r?.current_release ? `Current release ${r.current_release}` : undefined} actions={<button className="primary-action" onClick={() => setEditing(true)}>Edit profile</button>}>
          <dl className="kv">
            <dt>Institution type</dt><dd>{p.profile?.institution_type_name || '—'}</dd>
            <dt>Autonomous status</dt><dd>{humanize(p.profile?.autonomous_status) || '—'}</dd>
            <dt>Approval bodies</dt><dd>{p.profile?.approval_bodies.join(', ') || '—'}</dd>
            <dt>Jurisdiction</dt><dd>{p.profile?.jurisdiction || '—'}</dd>
            <dt>Programmes</dt><dd>{p.programmes.map((x) => `${x.name} (${x.programme_type_name || x.programme_type}, ${x.approval_body})`).join('; ') || '—'}</dd>
          </dl>
        </Panel>
      ))}
      {editing && p && r && (
        <ActionDialog title={`Benchmark profile: ${p.institution_name}`} confirmLabel="Save profile"
          description="Programmes: one per line as Name | programme type code | approval body."
          fields={[
            { name: 'institution_type', label: 'Institution type', type: 'select', required: true, initial: p.profile?.institution_type || '', options: r.institution_types.map((o) => ({ value: o.code, label: o.name })) },
            { name: 'autonomous_status', label: 'Autonomous status', type: 'select', required: true, initial: p.profile?.autonomous_status || '', options: r.autonomous_statuses.map((o) => ({ value: o.code, label: o.name })) },
            { name: 'approval_bodies', label: `Approval bodies, comma separated (${r.approval_bodies.join(', ')})`, initial: p.profile?.approval_bodies.join(', ') || '' },
            { name: 'jurisdiction', label: 'Jurisdiction', initial: p.profile?.jurisdiction || '' },
            { name: 'programmes', label: `Programmes (types: ${r.programme_types.map((t) => t.code).join(', ')})`, type: 'textarea', initial: p.programmes.map((x) => `${x.name} | ${x.programme_type} | ${x.approval_body}`).join('\n') },
          ]}
          onSubmit={async (v) => {
            const programmes = v.programmes.split('\n').map((l) => l.split('|').map((x) => x.trim())).filter((x) => x[0])
              .map(([name, programme_type = '', approval_body = '']) => ({ name, programme_type, approval_body }));
            await saveCollegeProfile(chosen, {
              institution_type: v.institution_type, autonomous_status: v.autonomous_status, jurisdiction: v.jurisdiction,
              approval_bodies: v.approval_bodies.split(',').map((x) => x.trim()).filter(Boolean), programmes,
            });
            await Promise.all([profile.refetch(), colleges.refetch()]);
            setDone('Profile saved. New cycles use it; existing cycles keep their frozen copy.');
          }}
          onClose={() => setEditing(false)} />
      )}
    </>
  );
}
