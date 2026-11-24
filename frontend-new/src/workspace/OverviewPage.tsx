import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { useResource } from '../hooks/useResource';
import { pathOf } from '../navigation';
import { getQuestions } from '../services/capability';
import type { Sprint } from '../types/api';
import { whole } from '../utils/levels';
import { Icon, Stars } from './Icon';
import { AreaBars, FocusCards, LevelLadder, LevelRing, NextLevel, StrengthCards } from './ResultParts';
import { useResultView } from './useResult';

/** The college's dashboard (Vijay, 23 Nov): the level, what you do well, where to focus, and the next step. */
export function OverviewPage() {
  return <RequireSprint>{(sprint) => <OverviewBody sprint={sprint} />}</RequireSprint>;
}

function OverviewBody({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  const provisionalId = cap.provisionalId;
  const questions = useResource(() => getQuestions(sprint.id, provisionalId), `ws-q:${provisionalId}`, !!provisionalId);

  if (cap.loading) return <Loading label="Loading your result…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) {
    return (
      <Empty title="No result yet" action={<Link className="btn primary" to={pathOf('uploads')}>Send your documents</Link>}>
        Send your institution's documents, then run the assessment. Your readiness level and the areas to focus on appear here.
      </Empty>
    );
  }
  const progress = questions.data?.progress;
  const left = progress?.open ?? 0;
  const closed = !!progress?.final_run_id || view.final;

  return (
    <>
      <div className="overview-grid">
        <section className="standing" aria-label="Your readiness">
          <div className="standing-top">
            <h2>Your AI readiness</h2>
            <span className="tag">{view.final ? 'Final result' : 'Stage 1 · from your documents'}</span>
          </div>
          <div className="standing-body">
            <LevelRing view={view} />
            <div className="standing-copy">
              <div className="ws-row"><Stars stars={view.level.stars} size={22} /><h3 style={{ margin: 0 }}>{view.level.name}</h3></div>
              <p style={{ marginTop: 10 }}>{view.level.meaning}</p>
              <p className="muted" style={{ marginTop: 10 }}>{view.summary}</p>
              <Link className="text-btn" style={{ marginTop: 14 }} to={pathOf('cri')}>See your full result <Icon name="chevron" size={14} /></Link>
            </div>
          </div>
          <div className="standing-meta">
            <div><small>Readiness areas</small><strong>{view.areas.length} assessed</strong></div>
            <div><small>Strongest area</small><strong>{view.strengths[0]?.name || '—'}</strong></div>
            <div><small>Next level</small><strong>{view.level.next ? `${view.level.next.name} · ${view.level.pointsToNext} points` : 'Top level'}</strong></div>
          </div>
        </section>

        <section className="next-action">
          <div className="eyebrow">Your next best step</div>
          {closed ? (
            <>
              <h2>Plan the road to {view.level.next?.name || 'staying at the top'}.</h2>
              <p>Your final result is ready. Your pathway shows which steps move you up fastest.</p>
              <Link className="btn olive" to={pathOf('pathway')}><Icon name="route" />See your pathway</Link>
              <div className="mini-stat">
                <div><b>{view.level.stars} ★</b><small>{view.level.name}</small></div>
                {view.level.next && <div><b>{view.level.pointsToNext}</b><small>Points to {view.level.next.name}</small></div>}
              </div>
            </>
          ) : (
            <>
              <h2>Complete your assessment picture.</h2>
              <p>Answer the follow-up questions with a document wherever you can. Your final result comes when you finish.</p>
              <Link className="btn olive" to={pathOf('questionnaire')}><Icon name="assessment" />Continue the questions</Link>
              <div className="mini-stat">
                <div><b>{progress ? left : '—'}</b><small>Questions left</small></div>
                {view.heldPoints > 0 && <div><b>up to {whole(view.heldPoints)}</b><small>Points your answers can add</small></div>}
              </div>
            </>
          )}
        </section>
      </div>

      <div className="spacer" />
      <section className="surface surface-pad">
        <div className="section-head">
          <div><h2>Your nine readiness areas</h2><p>Out of 100 in each area, with its stars</p></div>
          <Link className="text-btn" to={pathOf('areas')}>Open the areas <Icon name="chevron" size={14} /></Link>
        </div>
        <AreaBars view={view} />
      </section>

      <div className="spacer" />
      <div className="section-head"><div><h2>Where you're strong</h2><p>What your own documents show best</p></div></div>
      <StrengthCards view={view} />

      <div className="spacer" />
      <div className="section-head"><div><h2>Where to focus next</h2><p>The areas with the most room to grow, and where to start</p></div>
        <Link className="text-btn" to={pathOf('actions')}>All recommended actions <Icon name="chevron" size={14} /></Link></div>
      <FocusCards view={view} />

      <div className="spacer" />
      <div className="two-col">
        <section className="surface surface-pad">
          <div className="section-head"><h2>Reaching the next level</h2></div>
          <NextLevel view={view} />
        </section>
        <section className="surface surface-pad">
          <div className="section-head"><h2>Your reports</h2></div>
          <p className="muted" style={{ fontSize: 14 }}>A short report for leadership, and a detailed report with every finding and the documents behind it.</p>
          <Link className="btn" style={{ marginTop: 16 }} to={pathOf('reports')}><Icon name="download" />Open reports</Link>
        </section>
      </div>

      <div className="spacer" />
      <section className="surface surface-pad">
        <div className="section-head"><div><h2>Readiness levels</h2><p>One star for every 20 points. The levels are provisional until calibrated across colleges.</p></div></div>
        <LevelLadder score={view.score} />
      </section>
    </>
  );
}
