import { useState, type FormEvent } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { CheckItem, ErrorState, Loading, Notice, PageHeading, Panel, Pill, Stat } from '../components/ui';
import { useSprint } from '../context/SprintContext';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getInstitution } from '../services/institutions';
import { getSprintOverview, getWorkSummary, updateSprint } from '../services/sprints';
import type { InstitutionDetail, Sprint, SprintOverview, WorkSummary } from '../types/api';
import { errorMessage } from '../utils/errors';
import { date, humanize } from '../utils/format';

const PIPELINE = ['draft', 'collecting', 'processing', 'reviewing', 'scoring', 'baseline_pending', 'baseline_approved', 'report_ready', 'completed'];

export function SprintSetup() {
  return <RequireSprint>{(sprint) => <SprintBody sprint={sprint} />}</RequireSprint>;
}

function daysBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000);
}

function SprintBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const { reload } = useSprint();
  const overview = useResource<SprintOverview>(() => getSprintOverview(sprint.id), sprint.id);
  const work = useResource<WorkSummary>(() => getWorkSummary(sprint.id), sprint.id);
  const inst = useResource<InstitutionDetail>(() => getInstitution(sprint.institution_id), sprint.institution_id);
  const { detail: cycle } = useCycle(sprint.institution_id);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  if (overview.loading) return <Loading label="Loading the sprint…" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />;
  const o = overview.data!;
  const duration = daysBetween(sprint.start_date, sprint.target_completion_date);
  const remaining = daysBetween(new Date().toISOString().slice(0, 10), sprint.target_completion_date);
  const stepIndex = PIPELINE.indexOf(sprint.status);

  return (
    <>
      <PageHeading page="sprint" />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <div className="stat-grid">
        <Stat label="Sprint duration" value={duration === null ? '—' : `${duration} days`} note={remaining === null ? 'Set dates below' : remaining >= 0 ? `${remaining} days remaining` : `${-remaining} days past target`} />
        <Stat label="Completion" value={`${sprint.completion_percentage}%`} note={humanize(sprint.status)} />
        <Stat label="Evidence owners" value={work.data ? work.data.by_role.length : '—'} note="Roles with outstanding work" />
        <Stat label="Open decisions" value={work.data ? work.data.totals.pending_facts + work.data.totals.open_gaps : '—'} note={work.data ? `${work.data.totals.overdue} overdue` : ''} />
      </div>
      <div className="content-grid">
        <Panel title="Sprint timeline" sub="Collection, review and assessment milestones">
          <ol className="timeline">
            {PIPELINE.map((s, i) => (
              <li key={s} className={i < stepIndex ? 'done' : i === stepIndex ? 'current' : ''}>
                <span aria-hidden="true">{i < stepIndex ? '✓' : i + 1}</span>{humanize(s)}
              </li>
            ))}
          </ol>
          <p className="muted">Start {date(sprint.start_date)} · Target {date(sprint.target_completion_date)}</p>
          {can('sprint.manage') && <DatesForm sprint={sprint} onDone={async () => { await reload(); setMsg({ tone: 'success', text: 'Sprint updated.' }); }} onError={(t) => setMsg({ tone: 'error', text: t })} />}
        </Panel>
        <Panel title="Readiness checklist">
          <div className="check-list">
            <CheckItem done={!!sprint.description}>Scope recorded for the sprint</CheckItem>
            <CheckItem done={!!cycle.data?.release_label}>Benchmark release selected {cycle.data?.release_label && `(${cycle.data.release_label})`}</CheckItem>
            <CheckItem done={inst.data?.coordinator?.state === 'active'}>Customer team invited and active</CheckItem>
            <CheckItem done={o.documents.total > 0}>Evidence collection started ({o.documents.total} documents)</CheckItem>
            <CheckItem done={!!sprint.start_date && !!sprint.target_completion_date}>Review and sign-off dates confirmed</CheckItem>
            <CheckItem done={!!work.data?.ready_for_baseline_review}>Ready for baseline review</CheckItem>
          </div>
          {work.data && work.data.blockers.length > 0 && (
            <ul className="plain-list muted">{work.data.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
          )}
          <p className="muted"><Pill status={sprint.status} /> {sprint.sprint_code}</p>
        </Panel>
      </div>
    </>
  );
}

function DatesForm({ sprint, onDone, onError }: { sprint: Sprint; onDone: () => Promise<void>; onError: (t: string) => void }) {
  const [form, setForm] = useState({ start_date: sprint.start_date || '', target_completion_date: sprint.target_completion_date || '', description: sprint.description });
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await updateSprint(sprint.id, { start_date: form.start_date || null, target_completion_date: form.target_completion_date || null, description: form.description });
      await onDone();
    } catch (err) { onError(errorMessage(err)); } finally { setBusy(false); }
  };
  return (
    <form className="form-grid" onSubmit={submit}>
      <label className="field"><span>Start</span><input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></label>
      <label className="field"><span>Target completion</span><input type="date" value={form.target_completion_date} onChange={(e) => setForm({ ...form, target_completion_date: e.target.value })} /></label>
      <label className="field span-2"><span>Scope</span><textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
      <button className="primary-action span-2" disabled={busy}>{busy ? 'Saving…' : 'Save sprint plan'}</button>
    </form>
  );
}
