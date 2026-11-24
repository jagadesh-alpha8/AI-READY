import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { Icon } from './Icon';
import { useResultView } from './useResult';

/**
 * Transformation › Choose a pace for a college (23 Nov): the same foundation goals on three timescales, phase by
 * phase, with who could lead each goal and what it asks the college to show.
 */
export function PacePage() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

const PACE_TEXT: Record<string, string> = {
  Immediate: 'Everything at once, for a college ready to commit staff time and budget now.',
  Progressive: 'In steady steps, each goal building on the last. Suits most colleges.',
  Gradual: 'One step at a time, alongside other priorities.',
};

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  if (cap.loading) return <Loading label="Loading the paces…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  const plan = cap.foundation;
  if (!view || !plan) return <Empty title="No result yet" action={<Link className="btn primary" to={pathOf('assessment')}>Go to the assessment</Link>}>The paces appear once the assessment has run.</Empty>;
  if (!plan.goals.length) return <Empty title="Your foundations are in place">Every foundation goal is already shown in your documents. See your pathway for what the next level takes.</Empty>;

  const goal = Object.fromEntries(plan.goals.map((g) => [g.id, g]));
  const text: Record<string, string> = {};
  for (const ind of view.result.indicators) for (const c of ind.conditions) text[c.id] = c.text;

  return (
    <>
      <div className="route-grid">
        {plan.routes.map((r) => (
          <article className={`route ${r.name === 'Progressive' ? 'recommended' : ''}`} key={r.name}>
            {r.name === 'Progressive' && <div className="route-band">Suits most colleges</div>}
            <div className="route-content">
              <h3>{r.name}</h3>
              <p>{PACE_TEXT[r.name] || ''}</p>
              <div className="duration">{r.indicative_duration}</div>
              <small>{plan.goals.length} goals in {r.batches.length} phase{r.batches.length === 1 ? '' : 's'}</small>
              <ol className="ws-plain-list" style={{ marginTop: 16 }}>
                {r.batches.map((b, i) => (
                  <li key={i}><strong>Phase {i + 1}:</strong> {b.map((id) => goal[id]?.title || id).join('; ')}</li>
                ))}
              </ol>
            </div>
          </article>
        ))}
      </div>
      <p className="muted" style={{ fontSize: 13, margin: '14px 0 0' }}>The same goals at every pace; only the timing changes. The timings are indicative: confirm staff time, budget and purchasing before you commit.</p>
      <div className="spacer" />
      <div className="section-head"><div><h2>The foundation goals</h2><p>What each goal asks you to show, and who could lead it</p></div></div>
      <div className="ws-cards">
        {plan.goals.map((g, i) => (
          <article className="ws-card" key={g.id}>
            <span className="tag">Goal {i + 1}</span>
            <h3>{g.title}</h3>
            <span className="ws-source">Led by: {g.suggested_role.replace(/ \(suggested\)$/, '')}</span>
            <ul className="ws-plain-list" style={{ fontSize: 13 }}>
              {g.target_condition_ids.slice(0, 3).map((id) => <li key={id}>{text[id] || id}</li>)}
              {g.target_condition_ids.length > 3 && <li className="muted">and {g.target_condition_ids.length - 3} more</li>}
            </ul>
            {g.depends_on.length > 0 && <span className="ws-source">After: {g.depends_on.map((id) => goal[id]?.title || id).join('; ')}</span>}
          </article>
        ))}
      </div>
      <div className="spacer" />
      <div className="callout"><Icon name="route" />
        <p>Have your own plan already? Check it against these goals.</p>
        <Link className="text-btn" to={pathOf('plancompare')}>Check your own plan <Icon name="chevron" size={14} /></Link>
      </div>
    </>
  );
}
