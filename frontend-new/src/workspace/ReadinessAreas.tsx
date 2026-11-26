import { useEffect, useMemo } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { AreasV6, followUpLinks } from './Areas6';
import { useResource } from '../hooks/useResource';
import { getQuestions } from '../services/capability';
import './v5.css';
import { RequireSprint } from '../components/RequireSprint';
import { ErrorState, Loading } from '../components/ui';
import type { Sprint } from '../types/api';
import { whole } from '../utils/levels';
import { Stars } from './Icon';
import { ChecklistLine, pts } from './ResultParts';
import { NoResult } from './NoResult';
import { useResultView } from './useResult';

/** Results › Readiness areas: the nine areas, each with its four topics; a topic opens its six practices (Areas6). */
export function ReadinessAreas() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  const { hash } = useLocation();
  const [params, setParams] = useSearchParams();
  const area = params.get('area') || (hash ? hash.slice(1) : '');
  const topic = params.get('topic') || '';
  const stage1 = !!view && !view.final;
  // At Stage 1, a practice not found links to its open follow-up question.
  const questions = useResource(() => getQuestions(sprint.id, cap.provisionalId), `areas-q:${cap.provisionalId}`, stage1 && !!cap.provisionalId);
  const followUps = useMemo(() => followUpLinks(questions.data?.progress?.closed ? [] : questions.data?.questions), [questions.data]);
  const set = (key: string, value: string) => {
    const p = new URLSearchParams(params);
    if (value) p.set(key, value); else p.delete(key);
    p.delete('practices');
    setParams(p, { replace: key === 'area' });
  };
  useEffect(() => {
    if (area && !topic) document.getElementById(area)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [area, topic, view]);
  if (cap.loading) return <Loading label="Loading the areas…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <NoResult cap={cap}>Your nine areas appear here once your documents have been read.</NoResult>;
  const v5 = view.run.next_steps?.presentation;
  if (v5) {
    return (
      <div className="v5">
        <AreasV6 v={v5} area={area} topic={topic} followUps={followUps} onArea={(c) => set('area', c)} onTopic={(c) => set('topic', c)} />
      </div>
    );
  }

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {[...view.areas].sort((a, b) => b.score - a.score).map((a) => (
        <section className="surface surface-pad" id={a.code} key={a.code} style={{ scrollMarginTop: 90 }}>
          <div className="section-head">
            <div>
              <h2>{a.name}</h2>
              <p>{a.level.name} · {a.inPlace} of {a.requirements} practices shown in full{a.partly ? `, ${a.partly} in part` : ''}</p>
            </div>
            <div className="ws-row"><Stars stars={a.level.stars} size={18} /><span className="ws-big-number" style={{ fontSize: 24 }}>{whole(a.score)}</span></div>
          </div>
          <div className="ws-bar" style={{ marginBottom: 18 }}>
            <i className={`shown ${a.score < 20 ? 'low' : a.score < 40 ? 'mid' : ''}`} style={{ width: `${a.score}%` }} />
            {a.shown - a.score >= 0.5 && <i className="held" style={{ width: `${a.shown - a.score}%` }} />}
          </div>
          <div className="ws-grid-2">
            <div>
              <h3 style={{ marginBottom: 8 }}>What's in place</h3>
              {a.explanation && <p style={{ fontSize: 14 }}>{a.explanation}</p>}
              {a.quote ? <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Evidence found in {a.quote.source}</p>
                : !a.explanation && <p className="muted" style={{ fontSize: 14 }}>Nothing in this area was found in your documents yet.</p>}
            </div>
            <div>
              <h3 style={{ marginBottom: 8 }}>What to show next</h3>
              {a.missing.length === 0 ? <p className="muted" style={{ fontSize: 14 }}>Everything in this area is shown. Keep the evidence current.</p> : (
                <ul className="ws-plain-list">
                  {a.missing.slice(0, 3).map((m) => <ChecklistLine key={m.id} item={m} />)}
                  {a.missing.length > 3 && <li className="muted">and {a.missing.length - 3} more in the detailed report</li>}
                </ul>
              )}
              {a.room >= 0.5 && <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>Shown in full, this area would add up to {pts(a.room)} to your overall score.</p>}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
