import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { RequireSprint } from '../components/RequireSprint';
import { Empty, ErrorState, Loading } from '../components/ui';
import { pathOf } from '../navigation';
import type { Sprint } from '../types/api';
import { whole } from '../utils/levels';
import { Stars } from './Icon';
import { pts } from './ResultParts';
import { useResultView } from './useResult';

/** Results › Readiness areas: one card per area, what's in place, what's missing, and the next step. */
export function ReadinessAreas() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { cap, view } = useResultView(sprint.id);
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [hash, view]);
  if (cap.loading) return <Loading label="Loading the areas…" />;
  if (cap.error) return <ErrorState error={cap.error} onRetry={() => void cap.runs.refetch()} />;
  if (!view) return <Empty title="No result yet" action={<Link className="btn primary" to={pathOf('assessment')}>Go to the assessment</Link>}>Run the assessment to see the nine areas.</Empty>;

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
              {a.quote ? (
                <div style={{ marginTop: 10 }}><p className="ws-quote" style={{ fontSize: 13, fontStyle: 'italic', borderLeft: '3px solid var(--olive)', paddingLeft: 12 }}>“{a.quote.text}”</p>
                  <small>{a.quote.source}</small></div>
              ) : !a.explanation && <p className="muted" style={{ fontSize: 14 }}>Nothing in this area was found in your documents yet.</p>}
            </div>
            <div>
              <h3 style={{ marginBottom: 8 }}>What to show next</h3>
              {a.missing.length === 0 ? <p className="muted" style={{ fontSize: 14 }}>Everything in this area is shown. Keep the evidence current.</p> : (
                <ul className="ws-plain-list">
                  {a.missing.slice(0, 3).map((m) => <li key={m}>{m}</li>)}
                  {a.missing.length > 3 && <li className="muted">and {a.missing.length - 3} more in the detailed report</li>}
                </ul>
              )}
              {a.pointsAvailable > 0 && <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>The recommended actions here would add up to {pts(a.pointsAvailable)}.</p>}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
