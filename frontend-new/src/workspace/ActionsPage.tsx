import { useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { areaTitle } from '../utils/areaTitles';
import { pillarName } from '../utils/capability';
import { Icon } from './Icon';
import { pts } from './ResultParts';
import { useResultView } from './useResult';

/**
 * Results › Recommended actions for a college (23 Nov): the priority plan as plain actions, largest gain first, each
 * with what to show and who could lead it. The same actions as the leadership report's "What to do next".
 */
export function ActionsPage() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

const LEVEL_WORD: Record<string, string> = { F: 'Set it up', A: 'Put it in use', O: 'Measure the results' };

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  const [area, setArea] = useState('all');
  if (cap.loading) return <Loading label="Loading your actions…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <Empty title="No result yet" action={<Link className="btn primary" to={pathOf('assessment')}>Go to the assessment</Link>}>Your actions appear once the assessment has run.</Empty>;

  const leads: Record<string, string> = {};
  for (const g of cap.foundation?.goals || []) {
    for (const id of g.target_condition_ids) leads[id] ||= g.suggested_role.replace(/ \(suggested\)$/, '');
  }
  const actions = [...(view.plan?.actions || [])].sort((a, b) => b.score_gain - a.score_gain).map((a) => {
    const code = a.pillar || a.indicator.split('.')[0];
    return {
      key: a.indicator, title: areaTitle(a.indicator, a.name), code, area: pillarName(code), points: a.score_gain,
      lead: a.condition_ids.map((id) => leads[id]).find(Boolean) || '',
      steps: a.conditions.map((c) => ({ text: c.requirement, stage: LEVEL_WORD[c.level] || '', part: c.credit > 0 })),
    };
  });
  const areas = Array.from(new Map(actions.map((a) => [a.code, a.area])).entries());
  const shown = actions.filter((a) => area === 'all' || a.code === area);
  const total = actions.reduce((n, a) => n + a.points, 0);

  if (!actions.length) {
    return <Empty title="No actions needed">Everything the assessment looks for is shown in your documents. Keep the evidence current.</Empty>;
  }
  return (
    <>
      <div className="callout"><Icon name="target" />
        <p>{actions.length} actions, largest gain first. Together they could add about {pts(total)}. A step counts once a fresh assessment reads the document that shows it.</p>
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
              <div className="ws-row" style={{ justifyContent: 'space-between' }}>
                <h3>{a.title}</h3>
                <span className="tag">up to {pts(a.points)}</span>
              </div>
              <p className="ws-source">{a.area}{a.lead ? ` · Led by: ${a.lead}` : ''}</p>
              <ul className="ws-plain-list" style={{ marginTop: 10 }}>
                {a.steps.map((s) => <li key={s.text}><strong>{s.stage}:</strong> {s.text}{s.part ? <span className="muted"> (partly shown already)</span> : null}</li>)}
              </ul>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
