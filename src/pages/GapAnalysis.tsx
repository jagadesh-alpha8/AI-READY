import { useState } from 'react';
import { GapDetailDialog } from '../components/GapDetail';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Pager, Panel, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getPlan } from '../services/assessments';
import { getSprintGapFacets, listSprintGapsPage, markGapUnavailable, resolveGap, skipGap } from '../services/gaps';
import type { Gap, GapFacets, ImprovementPlan, Page, Sprint } from '../types/api';
import { gapClass, gapImpact } from '../utils/gapClass';
import { humanize, tidyText } from '../utils/format';

const PAGE_SIZE = 20;
type GapAction = 'resolve' | 'unavailable' | 'skip';
/** Gap statuses that are still open work (backend GapItem.ACTIVE_STATUSES). */
const ACTIVE = new Set(['open', 'in_progress', 'needs_replacement']);

export function GapAnalysis() {
  return <RequireSprint>{(sprint) => <GapsBody sprint={sprint} />}</RequireSprint>;
}

function GapsBody({ sprint }: { sprint: Sprint }) {
  const { can } = useAccess();
  const [page, setPage] = useState(1);
  const [priority, setPriority] = useState('');
  const [status, setStatus] = useState('open');
  const facets = useResource<GapFacets>(() => getSprintGapFacets(sprint.id), sprint.id);
  const gaps = useResource<Page<Gap>>(() => listSprintGapsPage(sprint.id, { page, page_size: PAGE_SIZE, status, priority, ordering: 'priority' }), `${sprint.id}:${page}:${priority}:${status}`);
  const { cycleId } = useCycle(sprint.institution_id);
  const plan = useResource<ImprovementPlan>(() => getPlan(cycleId), `plan:${cycleId}`, !!cycleId);
  const [action, setAction] = useState<{ gap: Gap; kind: GapAction } | null>(null);
  const [viewing, setViewing] = useState<Gap | null>(null);
  const [done, setDone] = useState('');

  const f = facets.data;
  const evidenceOnly = f ? Object.entries(f.gap_type).filter(([t]) => t !== 'conflict').reduce((n, [, c]) => n + c, 0) : null;

  const act = async (gap: Gap, kind: GapAction, resolution: string) => {
    if (kind === 'resolve') await resolveGap(gap.id, resolution);
    else if (kind === 'unavailable') await markGapUnavailable(gap.id, resolution);
    else await skipGap(gap.id, resolution);
    setDone(`${gap.title}: ${kind === 'resolve' ? 'resolved' : kind === 'skip' ? 'skipped' : 'marked unavailable'}.`);
    void gaps.refetch();
    void facets.refetch();
  };

  /** Resolve / Unavailable / Skip on one row; the same buttons appear in the full-gap view. */
  const gapActions = (g: Gap, before?: () => void) => {
    if (!ACTIVE.has(g.status)) return <span className="muted clamp-2">{tidyText(g.resolution) || humanize(g.status)}</span>;
    if (!can('gaps.resolve')) return <span className="muted">View only</span>;
    if (g.can_act === false) return <span className="muted">{g.act_blocked_reason || 'Another role settles this'}</span>;
    const open = (kind: GapAction) => { before?.(); setAction({ gap: g, kind }); };
    return (
      <div className="row-actions nowrap">
        <button className="primary-action small" disabled={!!g.resolve_blocked_reason} title={g.resolve_blocked_reason} onClick={() => open('resolve')}>Resolve</button>
        <button className="secondary-button" disabled={!!g.close_blocked_reason} title={g.close_blocked_reason} onClick={() => open('unavailable')}>Unavailable</button>
        <button className="secondary-button" disabled={!!g.close_blocked_reason} title={g.close_blocked_reason} onClick={() => open('skip')}>Skip</button>
      </div>
    );
  };

  return (
    <>
      <PageHeading page="gaps" />
      {done && <Notice tone="success" onClose={() => setDone('')}>{done}</Notice>}
      <div className="stat-grid">
        <Stat label="Open gaps" value={f ? f.open : '—'} note={f ? `${f.total} raised in this sprint` : ''} />
        <Stat label="Critical gaps" value={f ? f.priority.blocking || 0 : '—'} note="Blocking, any status" />
        <Stat label="Evidence-only gaps" value={evidenceOnly ?? '—'} note="Any status; no capability change needed" />
        <Stat label="Contradictions" value={f ? f.gap_type.conflict || 0 : '—'} note="Any status; values that disagree" />
      </div>
      <div className="filter-bar">
        <label className="field inline"><span>Status</span>
          <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }}>
            {['open', 'in_progress', 'needs_replacement', 'resolved', 'unavailable', 'skipped'].map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
        </label>
      </div>
      <div className="filter-pills" role="tablist" aria-label="Priority">
        {['', 'blocking', 'high', 'medium', 'optional'].map((p) => (
          <button key={p || 'all'} role="tab" aria-selected={priority === p} className={priority === p ? 'active' : ''} onClick={() => { setPage(1); setPriority(p); }}>
            {p ? humanize(p) : 'All priorities'}
          </button>
        ))}
      </div>
      {gaps.loading && !gaps.data ? <Loading /> : gaps.error ? <ErrorState error={gaps.error} onRetry={() => void gaps.refetch()} /> :
        !gaps.data?.results.length ? <Empty title="No open gaps">Nothing here blocks the assessment.</Empty> : (
          <>
            <Table columns={['Priority gap', 'Class', 'Why it matters', 'Next-level impact', 'Owner', 'Action']}>
              {gaps.data.results.map((g) => (
                <tr key={g.id}>
                  <td className="source-cell">
                    <strong className="clamp-2" title={g.title}>{g.title}</strong>
                    <small className="cell-sub">{g.pillar_label}</small>
                  </td>
                  <td>{gapClass(g.gap_type)}</td>
                  <td>
                    <span className="clamp-2" title={tidyText(g.description)}>{tidyText(g.description)}</span>
                    <button className="link-button" onClick={() => setViewing(g)}>View full gap</button>
                  </td>
                  <td><Pill status={g.priority} label={gapImpact(g.priority)} /><small className="cell-sub">−{g.score_impact} CRI points</small></td>
                  <td>{g.assigned_to_name || g.owner_role_label || humanize(g.owner_role)}</td>
                  <td className="decision-cell">{gapActions(g)}</td>
                </tr>
              ))}
            </Table>
            <Pager page={page} count={gaps.data.count} pageSize={PAGE_SIZE} onPage={setPage} />
          </>
        )}

      <Panel title="Capability, compliance and outcome gaps" sub="From the benchmark assessment's improvement plan">
        {!cycleId ? <p className="muted">No benchmark assessment cycle yet.</p> : plan.loading ? <Loading /> : plan.error ? <ErrorState error={plan.error} /> :
          !plan.data?.gaps.length ? <p className="muted">No plan gaps yet. They are generated once the assessment cycle is finalized.</p> : (
            <Table columns={['Gap', 'Type', 'Severity', 'Closure evidence', 'Status']}>
              {plan.data.gaps.map((g) => (
                <tr key={g.id}>
                  <td><strong>{g.benchmark_title}</strong><small className="cell-sub clamp-2" title={tidyText(g.description)}>{tidyText(g.description)}</small></td>
                  <td>{g.type_label}</td>
                  <td><Pill status={g.severity} label={g.severity_label} /></td>
                  <td>{g.closing_evidence_title || g.initiatives[0]?.expected_evidence || '—'}</td>
                  <td><Pill status={g.status} label={g.status_label} /></td>
                </tr>
              ))}
            </Table>
          )}
      </Panel>

      {viewing && <GapDetailDialog gap={viewing} onClose={() => setViewing(null)} actions={(g) => gapActions(g, () => setViewing(null))} />}
      {action && (
        <ActionDialog
          title={action.kind === 'resolve' ? 'Resolve gap' : action.kind === 'skip' ? 'Skip gap' : 'Mark data unavailable'}
          description={<><b>{action.gap.title}</b><p className="dialog-clamp">{tidyText(action.gap.description)}</p></>}
          fields={[{ name: 'resolution', label: action.kind === 'resolve' ? 'How was it resolved?' : 'Reason', type: 'textarea', required: true }]}
          confirmLabel={action.kind === 'resolve' ? 'Resolve' : 'Confirm'}
          onSubmit={(v) => act(action.gap, action.kind, v.resolution)}
          onClose={() => setAction(null)}
        />
      )}
    </>
  );
}
