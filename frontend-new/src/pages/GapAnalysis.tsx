import { useState } from 'react';
import { GapDetailDialog } from '../components/GapDetail';
import { RequireSprint } from '../components/RequireSprint';
import { ActionDialog, Empty, ErrorState, Loading, Notice, PageHeading, Pager, Panel, Pill, Stat, Table } from '../components/ui';
import { useAccess } from '../hooks/useAccess';
import { useCycle } from '../hooks/useCycle';
import { useResource } from '../hooks/useResource';
import { getCycleBenchmark, getPlan, updatePlanGap, validatePlanGap } from '../services/assessments';
import { assignGap, chooseConflictValue, getSprintGapFacets, listSprintGapsPage, markGapUnavailable, resolveGap, skipGap, uploadGapEvidence } from '../services/gaps';
import { listEvidenceAssignees } from '../services/evidenceRequests';
import type { EvidenceAssignee } from '../types/workflow';
import type { Gap, GapDetail, GapFacets, ImprovementPlan, Page, PlanGap, Sprint } from '../types/api';
import { gapClass, gapImpact } from '../utils/gapClass';
import { humanize, tidyText } from '../utils/format';

const PAGE_SIZE = 20;
type GapAction = 'resolve' | 'unavailable' | 'skip';
/** Gap types a document upload can close (backend GapUploadEvidenceView). */
const UPLOADABLE = new Set(['missing_document', 'low_confidence']);
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
  const [extra, setExtra] = useState<{ gap: Gap; kind: 'assign' | 'upload' } | { gap: GapDetail; kind: 'choose'; factId: string; side: string } | null>(null);
  const [planAct, setPlanAct] = useState<{ gap: PlanGap; kind: 'update' | 'validate'; evidence?: { value: string; label: string }[] } | null>(null);
  const staffPlan = can('assessments.manage');
  const openValidate = async (g: PlanGap) => {
    const res = await getCycleBenchmark(cycleId, g.benchmark_code);
    const evidence = res.data.requests.flatMap((r) => r.items.filter((i) => i.status === 'accepted').map((i) => ({ value: i.id, label: `${i.title} · ${r.title}` })));
    setPlanAct({ gap: g, kind: 'validate', evidence });
  };
  const assignees = useResource<EvidenceAssignee[]>(() => listEvidenceAssignees(sprint.id), `assignees:${sprint.id}`, can('sprint.manage'));
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
    const more = (kind: 'assign' | 'upload') => { before?.(); setExtra({ gap: g, kind }); };
    return (
      <div className="row-actions">
        {UPLOADABLE.has(g.gap_type) && <button className="secondary-button" onClick={() => more('upload')}>Upload evidence</button>}
        {can('sprint.manage') && <button className="secondary-button" onClick={() => more('assign')}>Assign</button>}
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
            <Table columns={['Gap', 'Type', 'Severity', 'Closure evidence', 'Status', '']}>
              {plan.data.gaps.map((g) => (
                <tr key={g.id}>
                  <td><strong>{g.benchmark_title}</strong><small className="cell-sub clamp-2" title={tidyText(g.description)}>{tidyText(g.description)}</small></td>
                  <td>{g.type_label}</td>
                  <td><Pill status={g.severity} label={g.severity_label} /></td>
                  <td>{g.closing_evidence_title || g.initiatives[0]?.expected_evidence || '—'}</td>
                  <td><Pill status={g.status} label={g.status_label} /></td>
                  <td>{staffPlan && g.status !== 'closed' && (
                    <div className="row-actions nowrap">
                      <button className="secondary-button" onClick={() => setPlanAct({ gap: g, kind: 'update' })}>Update</button>
                      {g.status !== 'validated' && <button className="secondary-button" onClick={() => void openValidate(g).catch(() => setPlanAct({ gap: g, kind: 'validate', evidence: [] }))}>Validate</button>}
                    </div>
                  )}</td>
                </tr>
              ))}
            </Table>
          )}
      </Panel>

      {planAct?.kind === 'update' && (
        <ActionDialog title={`Update: ${planAct.gap.benchmark_title}`} confirmLabel="Save"
          fields={[
            { name: 'status', label: 'Status', type: 'select', required: true, initial: planAct.gap.status, options: ['open', 'planned', 'in_progress', 'closed'].map((v) => ({ value: v, label: humanize(v) })) },
            { name: 'root_cause', label: 'Root cause', type: 'textarea' },
          ]}
          onSubmit={async (v) => { await updatePlanGap(planAct.gap.id, { status: v.status, root_cause: v.root_cause || undefined }); setDone('Plan gap updated.'); void plan.refetch(); }}
          onClose={() => setPlanAct(null)} />
      )}
      {planAct?.kind === 'validate' && (
        <ActionDialog title={`Validate: ${planAct.gap.benchmark_title}`} confirmLabel="Validate with evidence"
          description={planAct.evidence?.length ? 'Close the gap with accepted evidence of the same college and benchmark.' : 'No accepted evidence for this benchmark yet. Submit and accept it in Benchmark cycles first.'}
          fields={[
            { name: 'evidence_item', label: 'Accepted evidence', type: 'select', required: true, options: planAct.evidence || [] },
            { name: 'note', label: 'Note', type: 'textarea', required: true },
          ]}
          onSubmit={async (v) => { await validatePlanGap(planAct.gap.id, { evidence_item: v.evidence_item, note: v.note }); setDone('Plan gap validated by evidence.'); void plan.refetch(); }}
          onClose={() => setPlanAct(null)} />
      )}
      {viewing && <GapDetailDialog gap={viewing} onClose={() => setViewing(null)} actions={(g) => gapActions(g, () => setViewing(null))}
        onChoose={(g, factId, side) => { setViewing(null); setExtra({ gap: g, kind: 'choose', factId, side }); }} />}
      {extra?.kind === 'assign' && (
        <ActionDialog title={`Assign: ${extra.gap.title}`} confirmLabel="Assign"
          fields={[
            { name: 'assigned_to', label: 'Assign to (blank = unassign)', type: 'select', options: (assignees.data || []).map((a) => ({ value: a.id, label: `${a.name} · ${a.role}` })), initial: '' },
            { name: 'due_date', label: 'Due date', type: 'date', initial: extra.gap.due_date || '' },
            { name: 'note', label: 'Note', type: 'textarea' },
          ]}
          onSubmit={async (v) => { await assignGap(extra.gap.id, v.assigned_to || null, v.due_date || null, v.note); setDone(v.assigned_to ? 'Gap assigned.' : 'Gap unassigned.'); void gaps.refetch(); }}
          onClose={() => setExtra(null)} />
      )}
      {extra?.kind === 'upload' && (
        <ActionDialog title={`Upload evidence: ${extra.gap.title}`} confirmLabel="Upload"
          description="The file is stored in this sprint and processed like any other upload; the gap updates once it is processed."
          fields={[{ name: 'file', label: 'Evidence file', type: 'file', required: true }]}
          onSubmit={async (_v, files) => {
            if (!files.file) throw new Error('Choose a file.');
            const res = await uploadGapEvidence(extra.gap.id, files.file);
            setDone(res.data.reused ? 'This file was already in the sprint; it is now linked to the gap.' : 'Evidence uploaded and queued for processing.');
            void gaps.refetch(); void facets.refetch();
          }}
          onClose={() => setExtra(null)} />
      )}
      {extra?.kind === 'choose' && (
        <ActionDialog title={`Use value ${extra.side}?`} confirmLabel="Settle contradiction"
          description="The chosen fact is confirmed and the competing values are rejected, with your reason in their history."
          fields={[{ name: 'reason', label: 'Reason', type: 'textarea', required: true }]}
          onSubmit={async (v) => { await chooseConflictValue(extra.gap.id, extra.factId, v.reason); setDone('Contradiction settled.'); void gaps.refetch(); void facets.refetch(); }}
          onClose={() => setExtra(null)} />
      )}
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
