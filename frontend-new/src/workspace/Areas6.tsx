/**
 * Results › Readiness areas in the merged website design (27 Nov 2026): Harsha's structure (search, a status filter,
 * open all, area › four topics › a drawer with the six practices) holding our content (plain names, whole numbers,
 * counts in words, practices that cite the document and page). Everything comes from the reports' own view
 * (presentation.for_screens).
 */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { pathOf } from '../navigation';
import type { ScreenCard, ScreenView } from '../types/capability';
import { Icon } from './Icon';
import { BarV5, Practice, round } from './V5';
import { countsInWords } from '../utils/practices';

export { countsInWords };

type Topic = ScreenCard['topics'][number];
type Status = 'all' | 'shown' | 'partly' | 'missing';
const FILTERS: { key: Status; label: string }[] = [
  { key: 'all', label: 'All' }, { key: 'shown', label: 'In place' }, { key: 'partly', label: 'Partly in place' }, { key: 'missing', label: 'Not found' },
];

const has = (text: string | undefined, q: string) => !!text && text.toLowerCase().includes(q);

/** What a search and a status filter leave of an area: its topics, and in each the practices that matched. */
function visibleTopics(a: ScreenCard, q: string, status: Status) {
  return a.topics.filter((t) => {
    if (status !== 'all' && !t.practices.some((p) => p.status === status)) return false;
    if (!q) return true;
    return has(a.name, q) || has(t.name, q) || has(t.definition, q)
      || t.practices.some((p) => has(p.label_short, q) || has(p.looked_for, q));
  });
}

export function AreasV6({ v, area, topic, followUps, onArea, onTopic }: {
  v: ScreenView; area: string; topic: string;
  /** For a practice not found at Stage 1: the address of its open follow-up question, by practice id. */
  followUps: Map<string, string>;
  onArea: (code: string) => void; onTopic: (code: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<Status>('all');
  const [allOpen, setAllOpen] = useState(false);
  const [open, setOpen] = useState<Set<string>>(() => new Set(area ? [area] : []));
  useEffect(() => { if (area) setOpen((o) => new Set(o).add(area)); }, [area]);
  const q = query.trim().toLowerCase();
  const filtering = !!q || status !== 'all';
  const shown = v.cards.map((a) => ({ a, topics: visibleTopics(a, q, status) })).filter((x) => !filtering || x.topics.length);
  const topics = useMemo(() => v.cards.flatMap((a) => a.topics.map((t) => ({ a, t }))), [v.cards]);
  const at = topics.findIndex((x) => x.t.code === topic);
  const isOpen = (code: string) => allOpen || filtering || open.has(code);
  const toggle = (code: string) => {
    if (allOpen) { setAllOpen(false); setOpen(new Set(v.cards.map((c) => c.code).filter((c) => c !== code))); return; }
    const next = new Set(open);
    if (next.has(code)) next.delete(code); else { next.add(code); onArea(code); }
    setOpen(next);
  };

  return (
    <div className="v6-areas">
      <div className="v6-tools">
        <label className="search-box v6-search"><Icon name="search" />
          <span className="ws-sr">Search topics and practices</span>
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search topics and practices, for example “privacy”" />
        </label>
        <div className="v6-chips" role="group" aria-label="Show practices">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={status === f.key} className={status === f.key ? 'on' : ''} onClick={() => setStatus(f.key)}>{f.label}</button>
          ))}
        </div>
        {!filtering && (
          <button type="button" className="text-btn" onClick={() => { setAllOpen(!allOpen); if (allOpen) setOpen(new Set()); }}>
            {allOpen ? 'Close all' : 'Open all'}
          </button>
        )}
      </div>
      {filtering && (
        <p className="muted v6-count" role="status">
          {shown.reduce((n, x) => n + x.topics.length, 0)} of {topics.length} topics match.
          {' '}<button type="button" className="text-btn" onClick={() => { setQuery(''); setStatus('all'); }}>Show all</button>
        </p>
      )}
      {shown.map(({ a, topics: ts }) => (
        <section key={a.code} id={a.code} className={`v6-area${isOpen(a.code) ? ' open' : ''}`}>
          <button type="button" className="v6-area-head" aria-expanded={isOpen(a.code)} onClick={() => toggle(a.code)}>
            <span className="t"><strong>{a.name}</strong><span>{a.definition}</span></span>
            <span className="r">
              <BarV5 score={a.score} extra={v.stage1 ? a.to_confirm : 0} />
              <b>{round(a.score)}{v.stage1 && a.to_confirm >= 0.5 && <small className="plus">+{round(a.to_confirm)}</small>}</b>
              <span className="lvl">{a.level}</span><i aria-hidden="true">{isOpen(a.code) ? '−' : '+'}</i>
            </span>
          </button>
          {isOpen(a.code) && (
            <div className="v6-area-body">
              {a.card.verdict && <p className="v6-verdict">{a.card.verdict}</p>}
              <h3 className="v6-sub">{filtering ? 'Topics that match' : 'The four topics in this area'}</h3>
              <ul className="v6-topics">
                {ts.map((t) => (
                  <li key={t.code}>
                    <span className="t"><strong>{t.name}</strong>{t.definition && <span>{t.definition}</span>}</span>
                    <span className="c">{countsInWords(t.practices)}</span>
                    <button type="button" className="text-btn" onClick={() => onTopic(t.code)}
                      aria-label={`See the six practices in ${t.name}`}>See the six practices</button>
                  </li>
                ))}
              </ul>
              {a.step && !filtering && (
                <div className="v6-next">{a.step.kind && <span className="v5-kind dark">{a.step.kind}</span>}<strong>Next step: {a.step.title}</strong></div>
              )}
            </div>
          )}
        </section>
      ))}
      {!shown.length && <p className="muted">Nothing matches. Try another word, or show all practices.</p>}
      {at >= 0 && (
        <TopicDrawer key={topics[at].t.code} a={topics[at].a} t={topics[at].t} n={at + 1} total={topics.length} stage1={v.stage1}
          followUps={followUps} onClose={() => onTopic('')}
          onPrev={at > 0 ? () => onTopic(topics[at - 1].t.code) : undefined}
          onNext={at < topics.length - 1 ? () => onTopic(topics[at + 1].t.code) : undefined} />
      )}
    </div>
  );
}

/** One topic's six practices over the list: focus moves in, Tab stays inside, Escape closes, focus goes back. */
function TopicDrawer({ a, t, n, total, stage1, followUps, onClose, onPrev, onNext }: {
  a: ScreenCard; t: Topic; n: number; total: number; stage1: boolean; followUps: Map<string, string>;
  onClose: () => void; onPrev?: () => void; onNext?: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    heading.current?.focus();
    const prior = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prior; if (opener && document.body.contains(opener)) opener.focus(); };
  }, []);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { e.stopPropagation(); onClose(); return; }
    if (e.key !== 'Tab' || !panel.current) return;
    const items = panel.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex="0"]');
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  const summary = t.verdict || t.line;
  return (
    <>
      <div className="drawer-bg" onClick={onClose} aria-hidden="true" />
      <div className="drawer v6-drawer" role="dialog" aria-modal="true" aria-labelledby={`dr-${t.code}`} ref={panel} onKeyDown={onKey}>
        <div className="drawer-top">
          <div>
            <small>{a.name}</small>
            <h2 id={`dr-${t.code}`} ref={heading} tabIndex={-1}>{t.name}</h2>
            {t.definition && <p className="muted">{t.definition}</p>}
            <p className="v6-dcount"><strong>{countsInWords(t.practices)}, out of six practices</strong></p>
            {summary && <p className="v6-dsum">{summary}</p>}
          </div>
          <button type="button" className="text-btn" onClick={onClose}>Close</button>
        </div>
        <div className="drawer-body">
          {t.practices.map((p) => (
            <Practice key={p.id} p={p} stage1={stage1} followUp={stage1 && p.status === 'missing' ? followUps.get(p.id) : undefined} />
          ))}
        </div>
        <div className="drawer-bottom v6-dnav">
          <button type="button" className="text-btn" disabled={!onPrev} onClick={onPrev}>Previous topic</button>
          <span className="muted">Topic {n} of {total}</span>
          <button type="button" className="text-btn" disabled={!onNext} onClick={onNext}>Next topic</button>
        </div>
      </div>
    </>
  );
}

/** The address of each practice's open follow-up question (questions carry the same practice ids). */
export function followUpLinks(questions: { id: string; condition_ids: string[]; status: string; response?: unknown }[] | undefined) {
  const m = new Map<string, string>();
  for (const q of questions || []) {
    if (q.status !== 'open' || q.response) continue;
    for (const id of q.condition_ids) if (!m.has(id)) m.set(id, `${pathOf('questionnaire')}?question=${q.id}`);
  }
  return m;
}
