import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { whole } from '../utils/levels';
import { Icon, Stars } from './Icon';
import { AreaBars, FocusCards, LevelRing, NextLevel, StrengthCards } from './ResultParts';
import { NoResult } from './NoResult';
import { useResultView } from './useResult';

/** Results › Summary: the verdict, the nine areas, strengths, focus and the next level, in plain words. */
export function ResultsSummary() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  if (cap.loading) return <Loading label="Loading your result…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <NoResult cap={cap}>Run the assessment on your documents to see your readiness level.</NoResult>;
  return (
    <>
      {!view.final && (
        <div className="callout"><Icon name="help" />
          <p><strong>This is your Stage 1 result, from your documents alone.</strong> Answer the follow-up questions to confirm it; your final result comes when you finish.
            {view.heldPoints > 0 && ` Your answers can add up to ${whole(view.heldPoints)} points.`}</p>
        </div>
      )}
      <div className="overview-grid">
        <section className="standing">
          <div className="standing-top"><h2>{view.final ? 'Your final result' : 'Your Stage 1 result'}</h2>
            <span className="tag">{view.level.stars} of 5 stars</span></div>
          <div className="standing-body">
            <LevelRing view={view} />
            <div className="standing-copy">
              <div className="ws-row"><Stars stars={view.level.stars} size={22} /><h3 style={{ margin: 0 }}>{view.level.name}</h3></div>
              <p style={{ marginTop: 10 }}>{view.level.meaning}</p>
              <p className="muted" style={{ marginTop: 10 }}>{view.summary}</p>
            </div>
          </div>
        </section>
        <section className="surface surface-pad">
          <div className="section-head"><h2>Reaching the next level</h2></div>
          <NextLevel view={view} />
          <Link className="text-btn" style={{ marginTop: 18 }} to={pathOf('pathway')}>See your pathway <Icon name="chevron" size={14} /></Link>
        </section>
      </div>
      <div className="spacer" />
      <section className="surface surface-pad">
        <div className="section-head"><div><h2>Readiness by area</h2><p>Out of 100 in each area, with its stars</p></div>
          <Link className="text-btn" to={pathOf('areas')}>Open the areas <Icon name="chevron" size={14} /></Link></div>
        <AreaBars view={view} />
      </section>
      <div className="spacer" />
      <div className="section-head"><div><h2>Where you're strong</h2><p>The areas your documents show most fully</p></div></div>
      <StrengthCards view={view} />
      <div className="spacer" />
      <div className="section-head"><div><h2>Where to focus next</h2></div>
        <Link className="text-btn" to={pathOf('actions')}>All recommended actions <Icon name="chevron" size={14} /></Link></div>
      <FocusCards view={view} />
      <div className="spacer" />
      <div className="callout"><Icon name="download" />
        <p>Your <Link to={pathOf('reports')}>reports</Link> have the same picture as a short leadership report, and a detailed report with every finding and the documents behind it.</p>
      </div>
    </>
  );
}
