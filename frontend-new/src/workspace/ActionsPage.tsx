import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import type { Sprint } from '../types/api';
import { Icon } from './Icon';
import { ActionCard, ChecklistLine } from './ResultParts';
import { NoResult } from './NoResult';
import { useResultView } from './useResult';
import { NextLevelV5 } from './V5';
import type { ScreenView } from '../types/capability';
import './v5.css';

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
  if (!view) return <NoResult cap={cap}>Your steps appear once your documents have been read.</NoResult>;
  const v5 = view.run.next_steps?.presentation;
  if (v5?.steps.length) return <StepsV6 v={v5} />;

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
  return (
    <>
      <div className="callout"><Icon name="target" />
        <p>{view.actions.length ? 'One step in each area, weakest area first, the same as in your leadership report. ' : ''}
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

/** Plan › Steps (merged design, 27 Nov): what gets you to the next level, then the nine steps as built, the three to
 * start with first. */
function StepsV6({ v }: { v: ScreenView }) {
  const first = new Set(v.start_here.map((s) => s.area_code));
  const steps = [...v.steps.filter((s) => first.has(s.area_code)), ...v.steps.filter((s) => !first.has(s.area_code))];
  return (
    <div className="v5">
      <NextLevelV5 v={v} />
      <section className="surface surface-pad v6-steps">
        <h2>{steps.length === 9 ? 'Nine steps' : `${steps.length} steps`}</h2>
        <ol>
          {steps.map((s) => (
            <li key={s.area_code}>
              <div className="v6-step-tags">{s.kind && <span className="v5-kind dark">{s.kind}</span>}
                {first.has(s.area_code) && <span className="v6-start">Start here</span>}<span className="muted">{s.area}</span></div>
              <strong>{s.title}</strong>
              <dl>
                {s.builds_on && <div><dt>Builds on</dt><dd>{s.builds_on}</dd></div>}
                {s.lead && <div><dt>Lead</dt><dd>{s.lead}</dd></div>}
                <div><dt>Done when</dt><dd>{s.done_when_text}</dd></div>
              </dl>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
