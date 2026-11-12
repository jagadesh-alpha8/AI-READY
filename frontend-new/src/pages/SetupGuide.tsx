import { Empty, ErrorState, KeyValues, Loading, Notice, PageHeading, PageLink, Panel, Pill } from '../components/ui';
import { useSprint } from '../context/SprintContext';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import { dismissGuide, getGuideStatus, resetGuide, skipGuideStep, updateMenuTour, type GuideStatus } from '../services/auth';
import type { PageKey } from '../utils/access';
import { humanize } from '../utils/format';

/** Backend guide step → the screen of this app that does that step (the guide's own target_path is the old app's). */
const STEP_PAGE: Record<string, PageKey> = {
  institution_dna: 'profile',
  sprint_setup: 'sprint',
  upload_documents: 'uploads',
  monitor_processing: 'processing',
  facts_review: 'review',
  gaps_evidence: 'gaps',
  live_cri: 'cri',
  baseline_approval: 'baseline',
  recommendations: 'actions',
  transformation_plan: 'plan',
  reports: 'reports',
};

export function SetupGuide() {
  const { sprint } = useSprint();
  const scope = sprint ? { sprint_id: sprint.id, institution_id: sprint.institution_id } : {};
  const guide = useResource<GuideStatus>(() => getGuideStatus(scope), `guide:${sprint?.id || ''}`);
  const { busy, msg, setMsg, run } = useRunner();
  const g = guide.data;
  const act = (key: string, fn: () => Promise<{ data: GuideStatus }>, ok: string) =>
    run(key, async () => { const res = await fn(); guide.setData(res.data); }, ok);

  return (
    <>
      <PageHeading page="guide" actions={g && (
        <>
          <button className="secondary-button" disabled={!!busy} onClick={() => void act('dismiss', () => dismissGuide(!g.is_dismissed, scope), g.is_dismissed ? 'Guide shown again.' : 'Guide dismissed.')}>
            {g.is_dismissed ? 'Show guide' : 'Dismiss guide'}
          </button>
          <button className="secondary-button" disabled={!!busy} onClick={() => void act('reset', () => resetGuide(scope), 'Guide reset: skipped steps are open again.')}>Reset</button>
        </>
      )} />
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {guide.loading && !g ? <Loading /> : guide.error ? <ErrorState error={guide.error} onRetry={() => void guide.refetch()} /> : !g ? <Empty title="No guide" /> : (
        <>
          <p className="muted">
            {g.institution_name || 'No institution yet'}{g.sprint_code && ` · ${g.sprint_code}`} · {g.completed_count} of {g.total_steps} done
            {g.skipped_count > 0 && `, ${g.skipped_count} skipped`}. Skipping a step changes nothing in the records.
          </p>
          {g.steps.map((s) => {
            const page = STEP_PAGE[s.id];
            return (
              <Panel key={s.id} title={`${s.number}. ${s.title}`} sub={s.purpose}
                actions={<Pill status={s.status === 'completed' ? 'active' : s.status === 'skipped' ? 'neutral' : s.id === g.current_step_id ? 'pending' : s.status} label={s.id === g.current_step_id ? 'Current step' : undefined} />}>
                {s.block_reason && <p className="muted">{s.block_reason}</p>}
                <KeyValues data={s.details} />
                <div className="button-row">
                  {page && s.is_authorized && <PageLink to={page} className={s.id === g.current_step_id ? 'primary-action' : 'secondary-button'}>{s.action_label || 'Open'}</PageLink>}
                  {s.status !== 'completed' && s.is_authorized && (
                    <button className="secondary-button" disabled={!!busy} onClick={() => void act(`skip:${s.id}`, () => skipGuideStep(s.id, s.status !== 'skipped', scope), s.status === 'skipped' ? 'Step resumed.' : 'Step skipped.')}>
                      {s.status === 'skipped' ? 'Resume step' : 'Skip step'}
                    </button>
                  )}
                </div>
              </Panel>
            );
          })}
          {Object.keys(g.menu_tours || {}).length > 0 && (
            <Panel title="Screen tours" sub="Which screen walkthroughs you have finished or dismissed">
              {Object.entries(g.menu_tours).map(([menu, status]) => (
                <div key={menu} className="row-actions">
                  <span>{humanize(menu)}</span><Pill status={status === 'completed' ? 'active' : 'neutral'} label={humanize(String(status))} />
                  <button className="secondary-button" disabled={!!busy} onClick={() => void act(`tour:${menu}`, () => updateMenuTour(menu, 'reset', scope), 'Tour reset.')}>Show again</button>
                </div>
              ))}
            </Panel>
          )}
        </>
      )}
    </>
  );
}
