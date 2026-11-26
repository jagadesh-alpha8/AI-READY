/**
 * The website's pieces in the approved v5 design (26 Nov 2026), drawn from the same view as the reports
 * (presentation.for_screens), so the screens and the PDFs can't drift apart: the result, the chart, the next level,
 * Where to start, an area card and an area's practices. The main button is chosen by the state (audit finding 11).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { pathOf } from '../navigation';
import type { ScreenPractice, ScreenStep, ScreenView } from '../types/capability';

const STAR = 'M12 2.6l2.9 6.1 6.6.9-4.8 4.6 1.2 6.6L12 17.6 6.1 20.8l1.2-6.6L2.5 9.6l6.6-.9z';

export function StarsV5({ stars, size = 20 }: { stars: number; size?: number }) {
  return (
    <span className="v5-stars" role="img" aria-label={`${stars} of 5 stars`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <svg key={i} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
          <path d={STAR} fill={i < stars ? '#b9a23c' : 'none'} stroke={i < stars ? '#b9a23c' : '#b7c0b9'} strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      ))}
    </span>
  );
}

export const round = (n: number | null | undefined) => Math.round(n ?? 0);
const clamp = (n: number) => Math.max(0, Math.min(100, n));

/** A bar on the 0-100 scale with the four level lines; `extra` (to be confirmed) as a lighter part. */
export function BarV5({ score, extra = 0, big = false }: { score: number; extra?: number; big?: boolean }) {
  const s = clamp(score);
  const w = Math.max(0, Math.min(100 - s, extra));
  return (
    <div className={`v5-bar${big ? ' big' : ''}`}>
      {w >= 0.5 && <b className="wait" style={{ width: `${s + w}%` }} />}
      <b style={{ width: `${s}%` }} />
      {[20, 40, 60, 80].map((x) => <i key={x} style={{ left: `${x}%` }} />)}
    </div>
  );
}

export function HowToRead({ v, page = 'page' }: { v: ScreenView; page?: string }) {
  return (
    <section className="v5-howto" aria-label={`How to read this ${page}`}>
      <h2>How to read this {page}</h2>
      <p>We read the {v.documents.toLocaleString('en-IN')} documents you sent against {v.requirements} practices in nine areas of AI readiness.
        Every score is out of 100 and counts only what those documents show: something you do but have not written down appears as missing.
        {v.stage1 && v.held_whole > 0 && ' The lighter part of a bar is still to be confirmed by your follow-up answers and the documents that support them.'}</p>
    </section>
  );
}

export function ResultV5({ v, tag }: { v: ScreenView; tag?: string }) {
  const held = v.stage1 && v.held_whole > 0;
  return (
    <section className="v5-result" aria-label="Your result">
      <div className="v5-result-l">
        {tag && <span className="v5-tag">{tag}</span>}
        <div className="v5-lname">{v.level.name}</div>
        <StarsV5 stars={v.level.stars} />
        <div className="v5-outof"><b>{v.confirmed_whole}</b> out of 100{held ? ', confirmed' : ''}</div>
      </div>
      <div className="v5-result-r">
        <p className="v5-means">{v.level.meaning}</p>
        <div className="v5-summ">
          {v.summary_lines.map((s) => (
            <div key={s.label}><span className="k">{s.label}</span><span><strong>{s.area}.</strong>{s.fact ? ` ${s.fact}` : ''}</span></div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ChartV5({ v, areasLink = true }: { v: ScreenView; areasLink?: boolean }) {
  const held = v.stage1 && v.held_whole > 0;
  const toNext = v.level.next ? (v.level.points_to_next <= 2 ? `Close to the next level: ${v.level.next}`
    : `${v.level.points_to_next} points to the next level: ${v.level.next}`) : '';
  return (
    <section className="surface surface-pad v5-chart" aria-label="Where you stand">
      <div className="section-head">
        <div><h2>Where you stand, overall and in each of the nine areas</h2>
          <p>{held ? 'The lighter part of each bar is to be confirmed by your follow-up answers.' : 'One star for every 20 points.'}</p></div>
        {areasLink && <Link className="text-btn" to={pathOf('areas')}>Open the areas</Link>}
      </div>
      <div className="v5-gx">
        <div className="v5-gx-row head"><div className="l" /><div className="b bands">
          {v.levels.map((l, i) => <div key={l.name} className={i === v.level_index ? 'on' : ''}><strong>{l.name}</strong><span>{l.from} to {l.to ?? 100}</span></div>)}
        </div><div className="n" /></div>
        <div className="v5-gx-row all">
          <div className="l"><strong>Overall</strong><span>All nine areas together</span></div>
          <div className="b"><BarV5 score={v.score} extra={held ? v.held_points : 0} big />
            <div className="v5-note">{held ? `Up to ${v.held_whole} more point${v.held_whole === 1 ? '' : 's'} to be confirmed` : toNext}</div></div>
          <div className="n">{v.confirmed_whole}{held && <span className="plus">+{v.held_whole}</span>}</div>
        </div>
        {v.cards.map((a) => (
          <div className="v5-gx-row" key={a.code}>
            <div className="l"><strong>{a.name}</strong><span>{a.definition}</span></div>
            <div className="b"><BarV5 score={a.score} extra={held ? a.to_confirm : 0} /></div>
            <div className="n">{round(a.score)}{held && a.to_confirm >= 0.5 && <span className="plus">+{round(a.to_confirm)}</span>}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function NextLevelV5({ v }: { v: ScreenView }) {
  if (!v.level.next) return null;
  return (
    <section className="v5-road">
      <h2>What gets you to {v.level.next}</h2>
      <p>Finishing the basics in every area would bring you to about <strong>{v.basics.whole} out of 100</strong>
        {v.basics.reaches_next ? `, which is ${v.basics.level}.` : `. To reach ${v.level.next}, the next practices in each topic, the ones that show a thing in use, are needed too.`}
        {' '}The basics are the first two practices in each topic: the ones that show a thing has been set up.</p>
    </section>
  );
}

export function WhereToStartV5({ v }: { v: ScreenView }) {
  if (!v.start_here.length) return null;
  return (
    <section className="v5-start">
      <h2>Where to start</h2>
      <p className="muted">The first step in each of your three weakest areas.</p>
      <div className="v5-start-grid">
        {v.start_here.map((s, i) => (
          <Link key={s.area_code} className="v5-start-card" to={`${pathOf('areas')}?area=${s.area_code}`}>
            <div className="v5-start-top"><b>{i + 1}</b>{s.kind && <span className="v5-kind">{s.kind}</span>}</div>
            <strong>{s.title}</strong>
            {s.builds_on && <p>Builds on {s.builds_on.replace(/^Nothing/, 'nothing')}.</p>}
            <span className="v5-area">{s.area}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function StepV5({ s, stage1 }: { s: ScreenStep; stage1: boolean }) {
  return (
    <div className="v5-step">
      <div className="v5-step-t">{s.kind && <span className="v5-kind dark">{s.kind}</span>}<strong>{s.title}</strong></div>
      <dl>
        {s.builds_on && <div><dt>Builds on</dt><dd>{s.builds_on}{s.start && stage1 ? '. If you already have this, send the document with your follow-up answers.' : ''}</dd></div>}
        {s.lead && <div><dt>Lead</dt><dd>{s.lead}</dd></div>}
        <div><dt>Done when</dt><dd>{s.done_when_text}</dd></div>
      </dl>
    </div>
  );
}

const STATUS: Record<string, string> = { shown: 'In place', partly: 'Partly in place', missing: 'Not found' };

export function Practice({ p, stage1, followUp }: { p: ScreenPractice; stage1: boolean; followUp?: string }) {
  // The page cites the documents as the detailed report does (26 Nov); the passage behind a finding is one click away.
  const [passage, setPassage] = useState(false);
  const where = p.evidence_in?.length ? p.evidence_in.join('; ') : p.source;
  return (
    <div className="v5-prow">
      <i className={`v5-mk ${p.status}`} aria-hidden="true" />
      <div>
        <div className="v5-ps"><strong>{p.label_short}</strong><span className={`v5-st ${p.status}`}>{p.label === 'Not started' ? 'Not started' : STATUS[p.status]}</span></div>
        <p><em>We looked for</em> {p.looked_for}</p>
        {(p.found || p.why) && <p><em>We found</em> {[p.found, p.why].filter(Boolean).join(' ')}</p>}
        {where && (
          <p className="v5-ev"><em>Evidence found in</em> {where}
            {p.quote && <button type="button" className="text-btn v5-passage" aria-expanded={passage} onClick={() => setPassage(!passage)}>
              {passage ? 'Hide the passage' : 'Show the passage'}</button>}
          </p>
        )}
        {passage && p.quote && <p className="v5-q">“{p.quote}” <small>{p.source}</small></p>}
        {p.status === 'missing' && p.records && <p><em>Records that would show it</em> {p.records}</p>}
        {followUp && <p><Link className="text-btn v5-fu" to={followUp}>Answer this in the follow-up questions</Link></p>}
        {stage1 && p.follow_up && <p><em>To be confirmed</em> {p.follow_up}</p>}
        {p.status !== 'shown' && (p.next_step || p.done_when) && <p><em>Next</em> {p.next_step || `Done when ${p.done_when}`}</p>}
      </div>
    </div>
  );
}
