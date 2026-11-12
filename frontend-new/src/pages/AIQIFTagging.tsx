import { useState } from 'react';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Pager, Panel, Pill, Stat, Table, Tabs, type DialogField } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useResource } from '../hooks/useResource';
import { useRunner } from '../hooks/useRunner';
import {
  addFactMapping, autoCheckAIQIFQueue, confirmProfileSuggestion, decideFactKind, editFactMapping, getAIQIFExpertQueue, getAIQIFSummary,
  getProfileSuggestion, listSprintFactsPage, reopenFactMapping, reviewFactMapping,
} from '../services/facts';
import type { AIQIFMapping, Fact, Page, Sprint } from '../types/api';
import type { AIQIFExpertQueue, AIQIFSummary, ProfileSuggestion } from '../types/workflow';
import { humanize, pct, valueText } from '../utils/format';

const PAGE_SIZE = 20;
const RELATIONSHIPS = [
  { value: 'direct', label: 'Direct evidence' },
  { value: 'supporting', label: 'Supporting evidence' },
  { value: 'contextual', label: 'Context only (never counts)' },
];
const KINDS = [
  { value: 'ai_evidence', label: 'AI evidence' },
  { value: 'context', label: 'Context' },
  { value: 'profile', label: 'Institution profile' },
];

type TabKey = 'review' | 'all' | 'expert' | 'profile';
type Act =
  | { kind: 'review'; fact: Fact; tag: AIQIFMapping; decision: 'confirm' | 'reject' }
  | { kind: 'edit' | 'reopen'; fact: Fact; tag: AIQIFMapping }
  | { kind: 'add' | 'factkind'; fact: Fact };

export function AIQIFTagging() {
  return <RequireSprint>{(sprint) => <Body sprint={sprint} />}</RequireSprint>;
}

function Body({ sprint }: { sprint: Sprint }) {
  const { role, staff } = useAccess();
  const superAdmin = role === 'super_admin';
  const tabs = [
    { key: 'review' as const, label: 'Tags to review' },
    { key: 'all' as const, label: 'All tagged facts' },
    ...(superAdmin ? [{ key: 'expert' as const, label: 'Expert queue' }] : []),
    ...(staff ? [{ key: 'profile' as const, label: 'Profile from documents' }] : []),
  ];
  const [tab, setTab] = useState<TabKey>('review');
  const summary = useResource<AIQIFSummary>(() => getAIQIFSummary(sprint.id), `aiqif:${sprint.id}`);
  const s = summary.data;
  return (
    <>
      <PageHeading page="aiqif" />
      {summary.error ? <ErrorState error={summary.error} onRetry={() => void summary.refetch()} /> : (
        <div className="stat-grid">
          <Stat label="AI evidence" value={s ? s.ai_evidence : '—'} note={s ? `of ${s.facts} facts` : ''} />
          <Stat label="Context / profile" value={s ? `${s.context} / ${s.profile}` : '—'} note="Never cover an indicator" />
          <Stat label="Not classified" value={s ? s.not_classified : '—'} />
          <Stat label="Expert queue" value={s ? s.expert_queue.total : '—'} note={s ? `${s.expert_queue.tags} tags · ${s.expert_queue.facts} facts${s.coverage_provisional ? ' · coverage provisional' : ''}` : ''} />
        </div>
      )}
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="AI-QIF views" />
      {tab === 'review' && <FactTags sprint={sprint} status="needs_review" onChanged={() => void summary.refetch()} />}
      {tab === 'all' && <FactTags sprint={sprint} status="" onChanged={() => void summary.refetch()} />}
      {tab === 'expert' && <ExpertQueue sprint={sprint} onChanged={() => void summary.refetch()} />}
      {tab === 'profile' && <ProfileFromDocuments sprint={sprint} />}
    </>
  );
}

/** Facts with their AI-QIF tags and the reviewer's actions on each tag. */
function FactTags({ sprint, status, onChanged, facts: given }: { sprint: Sprint; status: string; onChanged: () => void; facts?: Fact[] }) {
  const [page, setPage] = useState(1);
  const list = useResource<Page<Fact>>(() => listSprintFactsPage(sprint.id, { page, page_size: PAGE_SIZE, aiqif_mapping_status: status || undefined }),
    `tags:${sprint.id}:${status}:${page}`, !given);
  const facts = given || list.data?.results || [];
  return (
    <>
      {!given && list.loading && !list.data ? <Loading /> : !given && list.error ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> :
        !facts.length ? <Empty title="Nothing here">No facts with tags in this state.</Empty> : (
          <>
            <TagTable facts={facts} onChanged={() => { void list.refetch(); onChanged(); }} />
            {!given && list.data && <Pager page={page} count={list.data.count} pageSize={PAGE_SIZE} onPage={setPage} />}
          </>
        )}
    </>
  );
}

function TagTable({ facts, onChanged }: { facts: Fact[]; onChanged: () => void }) {
  const { can } = useAccess();
  const [act, setAct] = useState<Act | null>(null);
  const [done, setDone] = useState('');
  const review = can('facts.review');

  const fields = (a: Act): DialogField[] => {
    if (a.kind === 'review') return [{ name: 'note', label: 'Note', type: 'textarea', required: a.decision === 'reject' }];
    if (a.kind === 'reopen') return [{ name: 'note', label: 'Why reopen this decision?', type: 'textarea', required: true }];
    if (a.kind === 'factkind') return [
      { name: 'kind', label: 'This fact is', type: 'select', required: true, options: KINDS, initial: a.fact.fact_kind || '' },
      { name: 'note', label: 'Note', type: 'textarea' },
    ];
    return [
      { name: 'indicator', label: 'Indicator code (e.g. AIQIF-C4.1)', required: true, initial: a.kind === 'edit' ? a.tag.indicator_code : '' },
      { name: 'relationship', label: 'Relationship', type: 'select', required: true, options: RELATIONSHIPS, initial: a.kind === 'edit' ? a.tag.relationship || 'supporting' : 'supporting' },
      { name: 'note', label: 'Note', type: 'textarea' },
    ];
  };
  const submit = async (a: Act, v: Record<string, string>) => {
    if (a.kind === 'review') await reviewFactMapping(a.fact.id, a.tag.indicator_code, a.decision, v.note);
    else if (a.kind === 'reopen') await reopenFactMapping(a.fact.id, a.tag.indicator_code, v.note);
    else if (a.kind === 'factkind') await decideFactKind(a.fact.id, v.kind as 'ai_evidence' | 'context' | 'profile', v.note);
    else if (a.kind === 'add') await addFactMapping(a.fact.id, v.indicator.trim(), v.relationship as 'direct', v.note);
    else if (a.kind === 'edit') await editFactMapping(a.fact.id, a.tag.indicator_code, { indicator_code: v.indicator.trim(), relationship: v.relationship, note: v.note });
    setDone('Saved. Coverage updates at the next recalculation.');
    onChanged();
  };
  const title = (a: Act) => a.kind === 'review' ? `${a.decision === 'confirm' ? 'Confirm' : 'Reject'} ${a.tag.indicator_code}`
    : a.kind === 'reopen' ? `Reopen ${a.tag.indicator_code}` : a.kind === 'edit' ? `Edit ${a.tag.indicator_code}` : a.kind === 'add' ? 'Add an indicator tag' : 'What is this fact?';

  return (
    <>
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      <Table columns={['Fact', 'Kind', 'Indicator tags', '']}>
        {facts.map((f) => (
          <tr key={f.id}>
            <td className="source-cell"><strong>{f.field_name}</strong><small className="cell-sub clamp-2">{valueText(f.value)}</small></td>
            <td>{humanize(f.fact_kind || 'unclassified')}{f.kind_needs_check && <small className="cell-sub">Needs a check</small>}</td>
            <td>
              {!f.aiqif_mappings.length ? <span className="muted">No tags</span> : f.aiqif_mappings.map((t) => (
                <div key={t.indicator_code} className="condition">
                  <div>
                    <b>{t.indicator_code}</b> {t.indicator_name} · {pct(t.confidence)} · {humanize(t.relationship || '')}{' '}
                    <Pill status={t.review_status === 'confirmed' ? 'active' : t.review_status === 'rejected' ? 'blocked' : 'pending'} label={humanize(t.review_status || t.status)} />
                    {t.counts === false && t.counts_reason && <small className="cell-sub">{t.counts_reason}</small>}
                  </div>
                  {review && (
                    <div className="row-actions">
                      {t.review_status !== 'confirmed' && <button className="secondary-button" onClick={() => setAct({ kind: 'review', fact: f, tag: t, decision: 'confirm' })}>Confirm</button>}
                      {t.review_status !== 'rejected' && <button className="secondary-button" onClick={() => setAct({ kind: 'review', fact: f, tag: t, decision: 'reject' })}>Reject</button>}
                      <button className="secondary-button" onClick={() => setAct({ kind: 'edit', fact: f, tag: t })}>Edit</button>
                      {t.review_status && t.review_status !== 'unreviewed' && <button className="secondary-button" onClick={() => setAct({ kind: 'reopen', fact: f, tag: t })}>Reopen</button>}
                    </div>
                  )}
                </div>
              ))}
            </td>
            <td>{review && (
              <div className="row-actions">
                <button className="secondary-button" onClick={() => setAct({ kind: 'add', fact: f })}>Add tag</button>
                <button className="secondary-button" onClick={() => setAct({ kind: 'factkind', fact: f })}>Set kind</button>
              </div>
            )}</td>
          </tr>
        ))}
      </Table>
      {act && <ActionDialog title={title(act)} confirmLabel="Save" fields={fields(act)} onSubmit={(v) => submit(act, v)} onClose={() => setAct(null)} />}
    </>
  );
}

function ExpertQueue({ sprint, onChanged }: { sprint: Sprint; onChanged: () => void }) {
  const queue = useResource<AIQIFExpertQueue>(() => getAIQIFExpertQueue(sprint.id), `expert:${sprint.id}`);
  const { busy, msg, setMsg, run } = useRunner();
  return (
    <>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      <Panel title="Expert queue" sub="Facts and tags only the AI-QIF expert settles. Auto-check applies earlier decisions on the same evidence first."
        actions={<button className="secondary-button" disabled={!!busy} onClick={() => void run('auto', async () => {
          const res = await autoCheckAIQIFQueue(sprint.id); await queue.refetch(); onChanged(); return res.data;
        }, (r) => { const d = r as { precedent_decisions: number; ai_check: string; expert_queue: { total: number } }; return `${d.precedent_decisions} settled from earlier decisions; AI check ${d.ai_check}; ${d.expert_queue.total} left.`; })}>
          {busy === 'auto' ? 'Checking…' : 'Auto-check queue'}
        </button>}>
        {queue.loading && !queue.data ? <Loading /> : queue.error ? <ErrorState error={queue.error} onRetry={() => void queue.refetch()} /> :
          !queue.data?.facts.length ? <p className="muted">The expert queue is empty.</p> : (
            <TagTable facts={queue.data.facts} onChanged={() => { void queue.refetch(); onChanged(); }} />
          )}
      </Panel>
    </>
  );
}

function ProfileFromDocuments({ sprint }: { sprint: Sprint }) {
  const sug = useResource<ProfileSuggestion>(() => getProfileSuggestion(sprint.id), `ps:${sprint.id}`);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState('');
  const p = sug.data;
  return (
    <>
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      {sug.loading && !p ? <Loading /> : sug.error ? <ErrorState error={sug.error} onRetry={() => void sug.refetch()} /> : p && (
        <Panel title={`Benchmark profile read from ${p.institution_name}'s documents`} sub="The profile decides which benchmarks apply; a person confirms it"
          actions={<button className="primary-action" onClick={() => setConfirming(true)}>Review and confirm</button>}>
          <dl className="kv">
            <dt>Institution type</dt><dd>{p.suggested.institution_type.value || '—'}{p.suggested.institution_type.conflict && ' (documents disagree)'}</dd>
            <dt>Autonomous status</dt><dd>{p.suggested.autonomous_status.value || '—'}{p.suggested.autonomous_status.conflict && ' (documents disagree)'}</dd>
            <dt>Approval bodies</dt><dd>{p.suggested.approval_bodies.join(', ') || '—'}</dd>
            <dt>Programmes</dt><dd>{p.suggested.programmes.map((x) => `${x.name} (${x.programme_type}, ${x.approval_body})`).join('; ') || '—'}</dd>
            <dt>Saved profile</dt><dd>{p.current ? `${p.current.institution_type} · ${p.current.autonomous_status}` : 'None yet'}</dd>
          </dl>
        </Panel>
      )}
      {confirming && p && (
        <ActionDialog title="Confirm the benchmark profile" confirmLabel="Save profile"
          description="Programmes are kept as read from the documents; edit them in Assessment setup if needed."
          fields={[
            { name: 'institution_type', label: 'Institution type', type: 'select', required: true, initial: p.suggested.institution_type.value || p.current?.institution_type || '', options: p.options.institution_types.map((o) => ({ value: o.code, label: o.name })) },
            { name: 'autonomous_status', label: 'Autonomous status', type: 'select', required: true, initial: p.suggested.autonomous_status.value || p.current?.autonomous_status || '', options: p.options.autonomous_statuses.map((o) => ({ value: o.code, label: o.name })) },
            { name: 'approval_bodies', label: `Approval bodies, comma separated (${p.options.approval_bodies.join(', ')})`, initial: p.suggested.approval_bodies.join(', ') },
          ]}
          onSubmit={async (v) => {
            await confirmProfileSuggestion(sprint.id, {
              institution_type: v.institution_type, autonomous_status: v.autonomous_status,
              approval_bodies: v.approval_bodies.split(',').map((x) => x.trim()).filter(Boolean), programmes: p.suggested.programmes,
            });
            setDone('Benchmark profile saved.');
            void sug.refetch();
          }}
          onClose={() => setConfirming(false)} />
      )}
    </>
  );
}
