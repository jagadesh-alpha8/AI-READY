import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { Icon } from './Icon';
import { ActionCard, ChecklistLine, pts } from './ResultParts';
import { useResultView } from './useResult';

/**
 * Results › Recommended actions: the leadership report's first steps (4 to 6) in full, as the server finished them
 * (capability/next_steps.py), then everything else still to show, area by area, as the "done when" checklist.
 */
export function ActionsPage() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  const [area, setArea] = useState('all');
  if (cap.loading) return <Loading label="Loading your actions…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <Empty title="No result yet" action={<Link className="btn primary" to={pathOf('assessment')}>Go to the assessment</Link>}>Your actions appear once the assessment has run.</Empty>;

  const inSteps = new Set(view.actions.flatMap((a) => a.requirements.map((r) => r.id)));
  // The rest of the checklist, area by area, leaving out what the first steps already cover.
  const rest = view.areas
    .map((a) => ({ code: a.code, name: a.name, items: a.missing.filter((m) => !inSteps.has(m.id)) }))
    .filter((a) => a.items.length);
  const areas = Array.from(new Map([...view.actions.map((a) => [a.area_code, a.area] as const), ...rest.map((a) => [a.code, a.name] as const)]).entries());
  const steps = view.actions.filter((a) => area === 'all' || a.area_code === area);
  const restShown = rest.filter((a) => area === 'all' || a.code === area);

  if (!view.actions.length && !rest.length) {
    return <Empty title="No actions needed">Everything the assessment looks for is shown in your documents. Keep the evidence current.</Empty>;
  }
  const total = view.actions.reduce((n, a) => n + a.points, 0);
  return (
    <>
      <div className="callout"><Icon name="target" />
        <p>{view.actions.length ? `Your first ${view.actions.length} steps are the ones in your leadership report; together about ${pts(total)} are at stake. ` : ''}
          Below them is everything else still to show, area by area. A step counts once a fresh assessment reads the document that shows it.</p>
      </div>
      <div className="filter-pills" role="group" aria-label="Filter by area">
        <button className={area === 'all' ? 'active' : ''} onClick={() => setArea('all')}>All areas</button>
        {areas.map(([code, name]) => <button key={code} className={area === code ? 'active' : ''} onClick={() => setArea(code)}>{name}</button>)}
      </div>
      {steps.length > 0 && <div className="ws-action-list">{steps.map((a) => <ActionCard key={a.key} a={a} n={view.actions.indexOf(a) + 1} />)}</div>}
      {restShown.length > 0 && (
        <section className="surface surface-pad" style={{ marginTop: 20 }}>
          <div className="section-head"><div><h2>Everything else to show</h2><p>Foundations first in each area</p></div></div>
          {restShown.map((a) => (
            <div key={a.code} style={{ marginTop: 14 }}>
              <h3 style={{ marginBottom: 8 }}>{a.name}</h3>
              <ul className="ws-plain-list">{a.items.map((m) => <ChecklistLine key={m.id} item={m} />)}</ul>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
