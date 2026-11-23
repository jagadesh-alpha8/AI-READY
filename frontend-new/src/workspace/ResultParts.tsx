import { Link } from 'react-router-dom';
import { pathOf } from '../navigation';
import { LEVELS, levelFor, whole } from '../utils/levels';
import { Icon, Stars } from './Icon';
import type { AreaView, ResultView } from './useResult';

/** "1 point", "3 points"; at least 1 when there is anything at all. */
export const pts = (n: number) => { const v = Math.max(1, Math.round(n)); return `${v} point${v === 1 ? '' : 's'}`; };

/** The score ring with the level's stars and name inside. */
export function LevelRing({ view, size = 190 }: { view: ResultView; size?: number }) {
  const deg = Math.max(0, Math.min(100, view.score)) * 3.6;
  const heldDeg = Math.max(0, Math.min(100, view.shownScore)) * 3.6;
  return (
    <div className="score-ring" style={{
      width: size, height: size,
      background: `conic-gradient(var(--green) 0deg ${deg}deg, #c9dd94 ${deg}deg ${heldDeg}deg, #edf1e9 ${heldDeg}deg 360deg)`,
    }} role="img" aria-label={`${view.level.name}, ${view.level.stars} of 5 stars, score ${whole(view.score)} out of 100`}>
      <div className="score-inner" style={{ width: size - 24, height: size - 24 }}>
        <div className="ws-level">
          <Stars stars={view.level.stars} size={17} />
          <b>{whole(view.score)}</b>
          <small>out of 100</small>
          <span className="ws-level-name">{view.level.name}</span>
        </div>
      </div>
    </div>
  );
}

/** The nine areas as bars: solid = counts now; hatched = shown in the documents, held until the follow-up answers. */
export function AreaBars({ view, link = true }: { view: ResultView; link?: boolean }) {
  const anyHeld = view.areas.some((a) => a.shown - a.score >= 0.5);
  const sorted = [...view.areas].sort((a, b) => b.score - a.score);
  return (
    <>
      <div className="ws-bars">
        {sorted.map((a) => {
          const tone = a.score < 20 ? 'low' : a.score < 40 ? 'mid' : '';
          return (
            <div className="ws-bar-row" key={a.code}>
              <span>{link ? <Link to={`${pathOf('areas')}#${a.code}`} style={{ color: 'inherit', textDecoration: 'none' }}>{a.name}</Link> : a.name}</span>
              <div className="ws-bar" aria-hidden="true">
                <i className={`shown ${tone}`} style={{ width: `${Math.min(100, a.score)}%` }} />
                {a.shown - a.score >= 0.5 && <i className="held" style={{ width: `${Math.min(100, a.shown) - Math.min(100, a.score)}%` }} />}
              </div>
              <Stars stars={a.level.stars} size={14} label={`${a.name}: ${a.level.name}`} />
              <b>{whole(a.score)}</b>
            </div>
          );
        })}
      </div>
      <div className="ws-legend">
        <span><i className="shown" />Counts now</span>
        {anyHeld && <span><i className="held" />{view.final ? 'Shown in your documents; not confirmed by follow-up answers' : 'Shown in your documents; counts once your follow-up answers confirm it'}</span>}
        <span>Stars: one per 20 points</span>
      </div>
    </>
  );
}

export function StrengthCards({ view }: { view: ResultView }) {
  if (!view.strengths.length) return <p className="muted">Nothing is shown in full yet. The focus areas below are where to start.</p>;
  return (
    <div className="ws-cards">
      {view.strengths.map((a) => (
        <article className="ws-card strong" key={a.code}>
          <div className="ws-row" style={{ justifyContent: 'space-between' }}><h3>{a.name}</h3><Stars stars={a.level.stars} size={14} /></div>
          <p>{a.inPlace} of {a.requirements} practices shown in full{a.partly ? `, ${a.partly} in part` : ''}.</p>
          {a.quote && <><p className="ws-quote">“{a.quote.text}”</p><span className="ws-source">{a.quote.source}</span></>}
        </article>
      ))}
    </div>
  );
}

export function FocusCards({ view }: { view: ResultView }) {
  return (
    <div className="ws-cards">
      {view.focus.map((a) => (
        <article className="ws-card focus" key={a.code}>
          <div className="ws-row" style={{ justifyContent: 'space-between' }}><h3>{a.name}</h3><Stars stars={a.level.stars} size={14} /></div>
          <p>{a.score === 0 ? 'Nothing found in your documents yet.' : `${a.inPlace + a.partly} of ${a.requirements} practices shown so far.`}</p>
          {a.missing[0] && <p><strong>Start with:</strong> {a.missing[0]}</p>}
          {a.pointsAvailable > 0 && <span className="ws-source">Up to {pts(a.pointsAvailable)} more</span>}
        </article>
      ))}
    </div>
  );
}

/** What reaching the next level takes. */
export function NextLevel({ view }: { view: ResultView }) {
  const next = view.level.next;
  if (!next) return <p>You are at the top level. Keep your evidence current as practice grows.</p>;
  return (
    <div>
      <div className="ws-row" style={{ marginBottom: 12 }}>
        <span className="ws-big-number">{view.level.pointsToNext}</span>
        <span>points to <strong>{next.name}</strong> <Stars stars={next.stars} size={14} /></span>
      </div>
      {view.toNextLevel.length > 0 && (() => {
        const total = view.toNextLevel.reduce((n, x) => n + x.points, 0);
        return (
          <>
            <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>The steps that add the most:</p>
            <ul className="ws-plain-list">
              {view.toNextLevel.map((x) => <li key={x.name}><strong>{x.name}</strong> <span className="muted">({x.area}, up to {pts(x.points)})</span></li>)}
            </ul>
            {total < view.level.pointsToNext && (
              <p className="muted" style={{ fontSize: 13, marginTop: 10 }}>Together these add about {pts(total)}; the rest comes from the focus areas.</p>
            )}
          </>
        );
      })()}
    </div>
  );
}

/** The five levels, with where the college is and the next one marked. */
export function LevelLadder({ score }: { score: number }) {
  const here = levelFor(score);
  return (
    <div className="ws-ladder">
      {LEVELS.map((l) => (
        <div key={l.name} className={`ws-rung ${l.name === here.name ? 'here' : l.name === here.next?.name ? 'next' : ''}`}>
          <Stars stars={l.stars} size={15} />
          <h3>{l.name}</h3>
          <small>{l.from === 0 ? 'Under 20' : l.from === 80 ? '80 and above' : `${l.from}–${l.from + 19}`}</small>
          <p>{l.meaning}</p>
          {l.name === here.name && <span className="tag"><Icon name="check" size={12} /> You are here</span>}
          {l.name === here.next?.name && <span className="tag">Next · {here.pointsToNext} points away</span>}
        </div>
      ))}
    </div>
  );
}

export type { AreaView };
