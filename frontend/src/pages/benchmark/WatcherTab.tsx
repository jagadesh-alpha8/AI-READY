import React, { useState } from 'react';
import { CheckCircle2, Eye, EyeOff, Play, RefreshCw, XCircle } from 'lucide-react';

import {
  checkFeedNow, getWatcherSummary, listChangeEvents, listWatcherFeeds, listWatcherRuns, proposeFromEvent,
  reviewChangeEvent, setFeedEnabled, startWatcherRun,
} from '../../api/benchmarks';
import type {
  ChangeStatus, SourceChangeEventInfo, SourceFeedInfo, WatcherRunInfo, WatcherSummary,
} from '../../api/benchmarks';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import { getErrorMessage } from '../../utils/errors';
import { SourceUpdatesGuide } from './SourceUpdatesGuide';

/**
 * Stage 4: the daily watcher. It checks the official pages people have turned on,
 * keeps a copy of each page, and lists what changed. It never changes a source,
 * requirement, benchmark or release: a person reviews every change here.
 */

const KIND_BADGE: Record<string, string> = {
  new_document: 'badge-brand', new_version: 'badge-brand', content_change: 'badge-neutral',
  withdrawal: 'badge-danger', access_change: 'badge-warning',
};
const STATUS_BADGE: Record<ChangeStatus, string> = {
  triaged: 'badge-warning', under_review: 'badge-brand', accepted: 'badge-success', rejected: 'badge-neutral',
  ignored: 'badge-neutral',
};
const RESULT_BADGE: Record<string, string> = {
  baseline: 'badge-brand', unchanged: 'badge-neutral', changed: 'badge-warning', failed: 'badge-danger',
  skipped: 'badge-warning',
};
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—');

type View = 'changes' | 'pages' | 'runs';

export const WatcherTab: React.FC = () => {
  const summary = useApiResource<WatcherSummary>(() => getWatcherSummary(), []);
  const [view, setView] = useState<View>('changes');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const s = summary.data;

  const runNow = async () => {
    setErr(''); setMsg('');
    try { setMsg((await startWatcherRun()).data.detail); } catch (e) { setErr(getErrorMessage(e)); }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-500">
        The watcher checks the official pages you turn on, once a day. It keeps a copy of each page and lists what
        changed — a new document, a removed document, or changed text. It never changes anything by itself:
        each change waits here for a person to decide.
      </p>
      <SourceUpdatesGuide current="watcher" />
      {summary.loading && <LoadingState message="Loading watcher…" />}
      {summary.error && <ErrorState message={summary.error} onRetry={summary.refetch} />}
      {s && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="glass-card p-3">
            <p className="text-ink-500">Daily check</p>
            <p className="text-sm font-bold text-ink-900">{s.schedule_enabled ? `On (${s.schedule_hour_utc}:30 UTC)` : 'Off'}</p>
          </div>
          <div className="glass-card p-3">
            <p className="text-ink-500">Pages watched</p>
            <p className="text-sm font-bold text-ink-900">{s.feeds_enabled} of {s.feeds}</p>
          </div>
          <div className="glass-card p-3">
            <p className="text-ink-500">Changes to review</p>
            <p className="text-sm font-bold text-ink-900">{s.open_events}{s.new_events ? ` (${s.new_events} new)` : ''}</p>
          </div>
          <div className="glass-card p-3">
            <p className="text-ink-500">Last run</p>
            <p className="text-sm font-bold text-ink-900">{s.last_run ? when(s.last_run.started_at) : 'Never'}</p>
            {s.last_run && <p className="text-ink-500">{s.last_run.status.replace('_', ' ')}</p>}
          </div>
        </div>
      )}
      {s && s.feeds === 0 && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-xs text-ink-700">
          <strong>No source pages are set up yet.</strong> Watched pages come from the Source Register's "Watch Feeds"
          sheet (import_source_register). Until there is at least one, the watcher has nothing to check.
        </div>
      )}
      {s && s.feeds > 0 && s.feeds_enabled === 0 && (
        <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-xs text-ink-700">
          <strong>{s.feeds} page(s) are set up, but none is turned on.</strong> Turn pages on in <em>Watched pages</em>;
          only turned-on pages are checked.
        </div>
      )}
      {s && !s.schedule_enabled && (
        <div className="rounded-lg border border-line-200 bg-surface p-3 text-xs text-ink-700">
          <strong>The daily check is off on this server</strong> (WATCHER_ENABLED is not set), so nothing is checked
          automatically. To check by hand: turn a page on in <em>Watched pages</em>, then use <em>Check now</em> on that
          page or <em>Check all now</em> above the list. New changes appear under <em>Changes</em>.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(['changes', 'pages', 'runs'] as View[]).map((v) => (
          <button key={v} className={view === v ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'} onClick={() => setView(v)}>
            {v === 'changes' ? 'Changes' : v === 'pages' ? 'Watched pages' : 'Run history'}
          </button>
        ))}
        <span className="flex-1" />
        <button className="btn-secondary btn-sm" onClick={runNow} disabled={!s?.feeds_enabled}
          title={s?.feeds_enabled ? 'Check every watched page now' : 'Turn on at least one page first'}>
          <Play className="w-3.5 h-3.5" /> Check all now
        </button>
      </div>
      {msg && <p className="text-xs text-success">{msg}</p>}
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}

      {view === 'changes' && <ChangesView onChanged={summary.refetch} />}
      {view === 'pages' && <PagesView onChanged={summary.refetch} />}
      {view === 'runs' && <RunsView />}
    </div>
  );
};

const ChangesView: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const [filter, setFilter] = useState<'open' | 'all'>('open');
  const events = useApiResource<SourceChangeEventInfo[]>(() => listChangeEvents(filter), [filter]);
  return (
    <div className="space-y-2">
      <select className="input text-xs w-auto" value={filter} onChange={(e) => setFilter(e.target.value as 'open' | 'all')}>
        <option value="open">Waiting for a decision</option>
        <option value="all">All changes</option>
      </select>
      {events.loading && <LoadingState message="Loading changes…" />}
      {events.error && <ErrorState message={events.error} onRetry={events.refetch} />}
      {(events.data || []).map((e) => (
        <EventCard key={e.id} event={e} onDone={() => { events.refetch(); onChanged(); }} />
      ))}
      {events.data && events.data.length === 0 && (
        <p className="text-sm text-ink-500">{filter === 'open' ? 'Nothing waiting for a decision.' : 'No changes detected yet.'}</p>
      )}
    </div>
  );
};

const EventCard: React.FC<{ event: SourceChangeEventInfo; onDone: () => void }> = ({ event: e, onDone }) => {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const decide = async (status: Exclude<ChangeStatus, 'triaged'>) => {
    setErr('');
    try { await reviewChangeEvent(e.id, status, note); onDone(); } catch (x) { setErr(getErrorMessage(x)); }
  };
  const d = e.details || {};
  const imp = e.impact || {};
  const decided = !['triaged', 'under_review'].includes(e.status);

  return (
    <div className="glass-card p-3 text-xs space-y-2">
      <button className="w-full text-left flex items-center gap-2 flex-wrap" onClick={() => setOpen(!open)}>
        <span className={`badge ${KIND_BADGE[e.change_kind]}`}>{e.change_kind_label}</span>
        <span className="font-mono text-ink-500">{e.source_code}</span>
        <span className="text-ink-900 flex-1 min-w-0">{e.summary}</span>
        <span className="text-ink-500" title="How important the change looks (0-100)">importance {Math.round(Number(e.materiality_score))}</span>
        <span className={`badge ${STATUS_BADGE[e.status]}`}>{e.status_label}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-line-200 pt-2">
          <p className="text-ink-500">
            {e.source_title} · found {when(e.detected_at)} ·{' '}
            {e.endpoint_url && <a className="text-brand-600 underline" href={e.endpoint_url} target="_blank" rel="noreferrer">open the official page</a>}
          </p>
          {d.added && d.added.length > 0 && (
            <div><p className="font-bold text-ink-900">New documents listed</p>
              {d.added.map(([t, u]) => <p key={u}>+ <a className="text-brand-600 underline" href={u} target="_blank" rel="noreferrer">{t || u}</a></p>)}
            </div>
          )}
          {d.removed && d.removed.length > 0 && (
            <div><p className="font-bold text-ink-900">No longer listed</p>
              {d.removed.map(([t, u]) => <p key={u} className="text-ink-700">− {t || u}</p>)}
            </div>
          )}
          {d.added_lines && d.added_lines.length > 0 && (
            <div><p className="font-bold text-ink-900">Text added</p>{d.added_lines.map((l, i) => <p key={i}>+ {l}</p>)}</div>
          )}
          {d.removed_lines && d.removed_lines.length > 0 && (
            <div><p className="font-bold text-ink-900">Text removed</p>{d.removed_lines.map((l, i) => <p key={i} className="text-ink-700">− {l}</p>)}</div>
          )}
          <div className="rounded-lg border border-line-200 bg-surface p-2">
            <p className="font-bold text-ink-900">What this could affect</p>
            {imp.note && <p className="text-ink-500">{imp.note}</p>}
            {!!imp.requirements?.length && <p>Requirements: {imp.requirements.join(', ')}</p>}
            {!!imp.benchmarks?.length && <p>Benchmarks: {imp.benchmarks.join(', ')}</p>}
            {!!imp.published_releases?.length && <p>Published releases: {imp.published_releases.join(', ')}</p>}
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-secondary btn-sm" onClick={async () => {
              setErr('');
              try { await proposeFromEvent(e.id); setErr('Candidate created — see the Candidates tab.'); }
              catch (x) { setErr(getErrorMessage(x)); }
            }}>Create a benchmark candidate</button>
            <span className="text-ink-500">Material changes get one automatically; use this for anything else worth an expert review.</span>
          </div>
          {decided ? (
            <p className="text-ink-500">Decided by {e.reviewed_by || '—'} on {when(e.reviewed_at)}{e.review_note ? ` — “${e.review_note}”` : ''}</p>
          ) : (
            <div className="space-y-2">
              <input className="input text-xs" placeholder="Note (needed for accept / reject / ignore)" value={note} onChange={(x) => setNote(x.target.value)} />
              <div className="flex flex-wrap gap-2">
                {e.status !== 'under_review' && <button className="btn-secondary btn-sm" onClick={() => decide('under_review')}>Looking into it</button>}
                <button className="btn-primary btn-sm" onClick={() => decide('accepted')}><CheckCircle2 className="w-3.5 h-3.5" /> Accept — real change</button>
                <button className="btn-secondary btn-sm" onClick={() => decide('rejected')}><XCircle className="w-3.5 h-3.5" /> Reject</button>
                <button className="btn-secondary btn-sm" onClick={() => decide('ignored')}>Ignore (noise)</button>
              </div>
              <p className="text-ink-500">Accepting only records the decision. Adding a new source version or editing a benchmark is still done by hand, through the normal review.</p>
            </div>
          )}
          {err && <InlineError message={err} onDismiss={() => setErr('')} />}
        </div>
      )}
    </div>
  );
};

const PagesView: React.FC<{ onChanged: () => void }> = ({ onChanged }) => {
  const [q, setQ] = useState('');
  const [only, setOnly] = useState<'' | 'true' | 'false'>('');
  const feeds = useApiResource<SourceFeedInfo[]>(() => listWatcherFeeds({ ...(only ? { enabled: only } : {}), ...(q ? { q } : {}) }), [q, only]);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [result, setResult] = useState<Record<string, string>>({});

  const run = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id); setErr('');
    try { await fn(); feeds.refetch(); onChanged(); } catch (e) { setErr(getErrorMessage(e)); } finally { setBusy(''); }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input className="input text-xs flex-1 min-w-[12rem]" placeholder="Search by code, title or address" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input text-xs w-auto" value={only} onChange={(e) => setOnly(e.target.value as '' | 'true' | 'false')}>
          <option value="">All pages</option>
          <option value="true">Watched</option>
          <option value="false">Not watched</option>
        </select>
      </div>
      <p className="text-xs text-ink-500">
        Pages start switched off. Open the address first and make sure it is the official page that lists the documents,
        then turn it on. Each site's robots.txt is respected.
      </p>
      {err && <InlineError message={err} onDismiss={() => setErr('')} />}
      {feeds.loading && <LoadingState message="Loading pages…" />}
      {feeds.error && <ErrorState message={feeds.error} onRetry={feeds.refetch} />}
      {(feeds.data || []).map((f) => (
        <div key={f.id} className="glass-card p-3 text-xs space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-ink-500">{f.source_code}</span>
            <span className="text-ink-900 flex-1 min-w-0 truncate">{f.source_title}</span>
            <span className="badge badge-neutral">{f.feed_type_label}</span>
            {f.last_result && <span className={`badge ${RESULT_BADGE[f.last_result] || 'badge-neutral'}`}>{f.last_result}</span>}
            {f.open_events > 0 && <span className="badge badge-warning">{f.open_events} to review</span>}
          </div>
          <a className="text-brand-600 underline break-all" href={f.endpoint_url} target="_blank" rel="noreferrer">{f.endpoint_url}</a>
          <p className="text-ink-500">
            Last checked {when(f.last_checked_at)} · {f.snapshot_count} saved cop{f.snapshot_count === 1 ? 'y' : 'ies'}
            {f.last_error ? ` · ${f.last_error}` : ''}
            {result[f.id] ? ` · ${result[f.id]}` : ''}
          </p>
          {f.feed_type !== 'manual_upload' ? (
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={busy === f.id} onClick={() => run(f.id, () => setFeedEnabled(f.id, !f.enabled))}>
                {f.enabled ? <><EyeOff className="w-3.5 h-3.5" /> Stop watching</> : <><Eye className="w-3.5 h-3.5" /> Watch daily</>}
              </button>
              <button className="btn-secondary btn-sm" disabled={busy === f.id} onClick={() => run(f.id, async () => {
                const r = (await checkFeedNow(f.id)).data.result;
                setResult((m) => ({ ...m, [f.id]: r.result === 'baseline' ? 'first copy saved' : `${r.result}${r.events ? `, ${r.events} change(s)` : ''}` }));
              })}>
                <RefreshCw className={`w-3.5 h-3.5 ${busy === f.id ? 'animate-spin' : ''}`} /> Check now
              </button>
            </div>
          ) : <p className="text-ink-500">Manual upload: nothing to watch; new versions are added by a person.</p>}
        </div>
      ))}
      {feeds.data && feeds.data.length === 0 && <p className="text-sm text-ink-500">No pages match.</p>}
    </div>
  );
};

const RunsView: React.FC = () => {
  const runs = useApiResource<WatcherRunInfo[]>(() => listWatcherRuns(), []);
  if (runs.loading) return <LoadingState message="Loading runs…" />;
  if (runs.error) return <ErrorState message={runs.error} onRetry={runs.refetch} />;
  return (
    <div className="space-y-2">
      {(runs.data || []).map((r) => (
        <div key={r.id} className="glass-card p-3 text-xs space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-ink-900 font-bold">{when(r.started_at)}</span>
            <span className={`badge ${r.status === 'complete' ? 'badge-success' : r.status === 'running' ? 'badge-brand' : 'badge-danger'}`}>{r.status.replace('_', ' ')}</span>
            <span className="text-ink-500">{r.feeds_checked} page(s) checked · {r.changes_detected} change(s) · by {r.trigger}</span>
          </div>
          {r.failure_detail.map((f) => <p key={f.url} className="text-danger">{f.source_code}: {f.error}</p>)}
        </div>
      ))}
      {runs.data && runs.data.length === 0 && <p className="text-sm text-ink-500">No runs yet.</p>}
    </div>
  );
};
