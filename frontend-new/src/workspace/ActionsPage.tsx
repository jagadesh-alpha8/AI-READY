import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { Icon } from './Icon';
import { allActions } from './plain';
import { pts } from './ResultParts';
import { useResultView } from './useResult';

/**
 * Results › Recommended actions for a college (23 Nov): the priority plan as plain actions, largest gain first, each
 * with what to show and who could lead it. The same actions as the leadership report's "What to do next".
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

  const records = new Map((view.run.assessment?.records || []).map((r) => [r.condition_id, r]));
  const first = new Set(view.actions.map((a) => a.code));
  // The leadership report's six first steps come first, then every other key indicator with something unfinished.
  const actions = [...view.actions, ...allActions(view.result, records, view.leads).filter((a) => !first.has(a.code))]
    .map((a) => ({ key: a.code, title: a.title, code: a.areaCode, area: a.area, points: a.points, lead: a.lead, step: a.step, steps: a.show }));
  const areas = Array.from(new Map(actions.map((a) => [a.code, a.area])).entries());
  const shown = actions.filter((a) => area === 'all' || a.code === area);
  const total = actions.reduce((n, a) => n + a.points, 0);

  if (!actions.length) {
    return <Empty title="No actions needed">Everything the assessment looks for is shown in your documents. Keep the evidence current.</Empty>;
  }
  return (
    <>
      <div className="callout"><Icon name="target" />
        <p>The first {Math.min(6, actions.length)} are the steps in your leadership report; the rest follow, largest gain first. Shown in full, all {actions.length} would add about {pts(total)}. A step counts once a fresh assessment reads the document that shows it.</p>
      </div>
      <div className="filter-pills" role="group" aria-label="Filter by area">
        <button className={area === 'all' ? 'active' : ''} onClick={() => setArea('all')}>All areas</button>
        {areas.map(([code, name]) => <button key={code} className={area === code ? 'active' : ''} onClick={() => setArea(code)}>{name}</button>)}
      </div>
      <div className="ws-action-list">
        {shown.map((a, i) => (
          <article className="ws-action" key={a.key}>
            <span className="ws-action-n">{i + 1}</span>
            <div>
              <h3>{a.title}</h3>
              <p className="ws-source">{a.area}{a.lead ? ` · Suggested lead: ${a.lead}` : ''}</p>
              <ul className="ws-plain-list" style={{ marginTop: 10 }}>
                {a.steps.map((s) => <li key={s}><strong>{a.step}:</strong> {s}</li>)}
              </ul>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
