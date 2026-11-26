import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { whole } from '../utils/levels';
import { Icon, Stars } from './Icon';
import { LevelLadder, NextLevel } from './ResultParts';
import { NoResult } from './NoResult';
import { useResultView } from './useResult';

/** Transformation › Your pathway: the five levels, where you are, what the next one takes, and the foundation goals. */
export function PathwayPage() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  if (cap.loading) return <Loading label="Loading your pathway…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <NoResult cap={cap}>Your pathway appears once the assessment has run.</NoResult>;
  const goals = cap.foundation?.goals || [];
  const routes = cap.foundation?.routes || [];

  return (
    <>
      <section className="surface surface-pad">
        <div className="section-head"><div><h2>Five levels of AI readiness</h2><p>One star for every 20 points. Provisional until calibrated across colleges.</p></div></div>
        <LevelLadder score={view.score} />
      </section>
      <div className="spacer" />
      <div className="two-col">
        <section className="surface surface-pad">
          <div className="section-head"><h2>Your next level</h2></div>
          <NextLevel view={view} />
        </section>
        <section className="surface surface-pad">
          <div className="section-head"><h2>Choose your pace</h2></div>
          {routes.length === 0 ? <p className="muted">The paces appear with the foundation goals.</p> : (
            <div className="check-list">
              {routes.map((r) => (
                <div className="check-item" key={r.name} style={{ justifyContent: 'space-between' }}>
                  <span><strong>{r.name}</strong></span><span className="muted">{r.indicative_duration}</span>
                </div>
              ))}
            </div>
          )}
          <p className="muted" style={{ fontSize: 13, marginTop: 14 }}>The same goals at every pace; only the timing changes.</p>
          <Link className="text-btn" style={{ marginTop: 12 }} to={pathOf('plan')}>Compare the paces <Icon name="chevron" size={14} /></Link>
        </section>
      </div>
      <div className="spacer" />
      <div className="section-head"><div><h2>Your foundation goals</h2><p>The first goals on the way up, built on what you already have</p></div>
        <Link className="text-btn" to={pathOf('plancompare')}>Check your own plan against them <Icon name="chevron" size={14} /></Link></div>
      {goals.length === 0 ? <p className="muted">No foundation goals: the foundations are already shown.</p> : (
        <div className="ws-cards">
          {goals.map((g, i) => (
            <article className="ws-card" key={g.id}>
              <span className="tag">Goal {i + 1}</span>
              <h3>{g.title}</h3>
              <p style={{ fontSize: 13 }}>{g.improvement_steps[0]}</p>
              <span className="ws-source">Led by: {g.suggested_role.replace(/ \(suggested\)$/, '')}</span>
              <span className="ws-source">{g.target_condition_ids.length} practice{g.target_condition_ids.length === 1 ? '' : 's'} to show</span>
            </article>
          ))}
        </div>
      )}
      <div className="spacer" />
      <div className="callout"><Icon name="target" />
        <p>Each step counts once a fresh assessment reads the documents that show it. <Stars stars={view.level.stars} size={13} /> today, {whole(view.score)} points.</p>
      </div>
    </>
  );
}
