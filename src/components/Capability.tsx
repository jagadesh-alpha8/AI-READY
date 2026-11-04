import { useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import type { useCapability } from '../hooks/useCapability';
import { cancelRun, startRun } from '../services/capability';
import type { Result, Run } from '../types/capability';
import { capabilityTone, newKey, scoreLabel, stateCounts, stateLabel, tierLabel } from '../utils/capability';
import { errorMessage } from '../utils/errors';
import { dateTime } from '../utils/format';
import { ActionDialog, Notice, Panel, Pill, Stat } from './ui';

type Cap = ReturnType<typeof useCapability>;

/** Score bounds, evidence resolution and Silver / Gold / Platinum eligibility of one frozen run. */
export function CapabilityStanding({ result, run }: { result: Result; run: Run }) {
  const counts = stateCounts(result);
  return (
    <>
      <div className="stat-grid">
        <Stat label="Institutional AI capability" value={result.aggregation === 'independent_conditions' && result.condition_decision_coverage === 0 ? 'Review needed' : scoreLabel(result)}
          note={result.exact_score === null ? 'Bounds: unresolved evidence is not counted as capability' : 'Exact score'} />
        <Stat label="Resolved indicator weight" value={`${result.assessment_coverage}%`} note="Evidence resolution, not model confidence" />
        <Stat label="Decided conditions" value={`${result.condition_decision_coverage}%`} note={`${counts.met} demonstrated · ${counts.not_met} shortfalls`} />
        <Stat label="Unknown / contradictory" value={counts.unknown + counts.conflicting} note="Remain unknown; never a pass or fail" />
      </div>
      {result.lower === 0 && result.exact_score === null && (
        <Notice tone="warn">Zero demonstrated so far does not establish zero capability. Review the evidence needed below.</Notice>
      )}
      <Panel title="Maturity eligibility" sub={`${result.methodology} · frozen ${dateTime(run.created_at)} · ${run.reference_period || 'default scope'}`}>
        {result.badge_policy === 'not_calibrated' ? (
          <p className="muted">Silver, Gold and Platinum standards are being calibrated. A readiness score alone does not award a maturity badge.</p>
        ) : (
          <div className="tier-grid">
            {result.tiers.map((t) => (
              <article key={t.name} className={`tier-card ${t.name.toLowerCase()}`}>
                <span>Eligibility</span>
                <h2>{t.name}</h2>
                <Pill tone={capabilityTone(t.eligibility)} label={tierLabel(t.eligibility)} />
                <ul>
                  <li>Overall threshold {t.threshold ?? '—'}</li>
                  <li>Pillar floor {t.pillar_floor ?? '—'}</li>
                  <li>{Object.keys(t.gates).length} indicator gates</li>
                </ul>
              </article>
            ))}
          </div>
        )}
        <p className="muted">Experimental internal criteria; these tiers are not external accreditation standards.</p>
      </Panel>
    </>
  );
}

/** Every indicator and its conditions with state, reason and cited source excerpts. */
export function CapabilityEvidence({ run }: { run: Run }) {
  const [filter, setFilter] = useState('all');
  const a = run.assessment!;
  const records = new Map(a.records.map((r) => [r.condition_id, r]));
  const labels = new Map(run.source_manifest.flatMap((d) => d.pages.map((p) => [p.page_id, `${d.filename} · v${d.version}`] as const)));
  return (
    <Panel title={`Indicators (${a.result.indicators.length})`} sub="Source excerpts are frozen to this assessment; new uploads need a new run"
      actions={(
        <label className="field inline"><span>Conditions</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All states</option>
            {['met', 'not_met', 'unknown', 'conflicting'].map((s) => <option key={s} value={s}>{stateLabel(s)}</option>)}
          </select>
        </label>
      )}>
      <div className="indicator-list">
        {a.result.indicators.map((i) => {
          const conditions = i.conditions.filter((c) => filter === 'all' || c.state === filter);
          if (filter !== 'all' && conditions.length === 0) return null;
          return (
            <details key={i.code} className="indicator">
              <summary><b>{i.code}</b> {i.name}<span className="muted"> · {i.lower}–{i.upper} / 100</span></summary>
              {conditions.map((c) => {
                const d = records.get(c.id);
                return (
                  <article key={c.id} className="condition">
                    <div><Pill tone={capabilityTone(c.state)} label={stateLabel(c.state)} /> <b>{c.id}</b> · {c.level}</div>
                    <p>{c.text}</p>
                    {d?.reason && <p className="muted">{d.reason}</p>}
                    <p className="muted">Closure evidence: {c.completion_evidence}</p>
                    {d?.citations.map((cite, n) => (
                      <blockquote key={n}><p>{cite.quote}</p><cite>{labels.get(cite.source_id) || 'Frozen source page'}</cite></blockquote>
                    ))}
                  </article>
                );
              })}
            </details>
          );
        })}
      </div>
    </Panel>
  );
}

/** Run status and the explicit "start a new run" control (uses model credits; CanManageSprint). */
export function CapabilityRunControl({ sprintId, cap }: { sprintId: string; cap: Cap }) {
  const { can } = useAccess();
  const [confirming, setConfirming] = useState(false);
  const [key] = useState(newKey);
  const [msg, setMsg] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const newest = cap.newest;

  return (
    <Panel title="Evidence-based capability assessment" sub={newest ? `Latest run ${dateTime(newest.created_at)}` : 'No run yet'}
      actions={newest && <Pill status={newest.status === 'queued' ? 'pending' : newest.status} label={newest.stalled ? 'Stalled' : newest.status} />}>
      {msg && <Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice>}
      {cap.running && <Notice tone="info">Assessment in progress. This view refreshes every few seconds.</Notice>}
      {!cap.enabled && <p className="muted">Assessment inference is disabled by the deployment administrator. Existing results stay readable.</p>}
      <div className="button-row">
        {can('sprint.manage') && (
          <button className="primary-action" disabled={!cap.enabled || cap.running} onClick={() => setConfirming(true)}>Start new assessment</button>
        )}
        {can('sprint.manage') && cap.running && newest && (
          <button className="secondary-button" onClick={async () => {
            try { await cancelRun(sprintId, newest.id); await cap.runs.refetch(); setMsg({ tone: 'success', text: 'Run cancelled.' }); }
            catch (e) { setMsg({ tone: 'error', text: errorMessage(e) }); }
          }}>Cancel run</button>
        )}
      </div>
      {confirming && (
        <ActionDialog
          title="Start a new capability assessment?"
          description="This uses model credits within the configured limits. It freezes the current verified sources; earlier assessments stay unchanged."
          fields={[]}
          confirmLabel="Start (uses credits)"
          onSubmit={async () => {
            await startRun(sprintId, key);
            await cap.runs.refetch();
            setMsg({ tone: 'success', text: 'Assessment started.' });
          }}
          onClose={() => setConfirming(false)}
        />
      )}
    </Panel>
  );
}
