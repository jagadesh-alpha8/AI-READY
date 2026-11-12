import { useState } from 'react';
import { useAccess } from '../hooks/useAccess';
import type { useCapability } from '../hooks/useCapability';
import { cancelRun, startRun } from '../services/capability';
import type { Result, Run, ScoreExplanation } from '../types/capability';
import {
  capabilityTone, causeLabel, indicatorScoreLabel, isPartCredit, newKey, partLabel, partTone, pillarScoreLabel, scoreLabel, stateCounts,
  stateLabel, tierLabel,
} from '../utils/capability';
import { errorMessage } from '../utils/errors';
import { dateTime } from '../utils/format';
import { ActionDialog, Bar, Notice, Panel, Pill, Stat } from './ui';

type Cap = ReturnType<typeof useCapability>;

/**
 * How a score was reached (report step). The backend will send it per requirement and per area; until then the
 * space shows what will appear there, so the layout is settled before the data arrives.
 */
export function ScoreExplanationBlock({ explanation, placeholder = true }: { explanation?: ScoreExplanation; placeholder?: boolean }) {
  if (!explanation) {
    return placeholder ? (
      <p className="muted">How this score was reached (what was found and credited, where we looked for what was not found, and the next step) appears here once the report step provides it.</p>
    ) : null;
  }
  return (
    <dl className="kv">
      {explanation.text && <><dt>How it was reached</dt><dd>{explanation.text}</dd></>}
      {explanation.found && <><dt>Found and credited</dt><dd>{explanation.found}</dd></>}
      {explanation.looked && <><dt>Where we looked</dt><dd>{explanation.looked}</dd></>}
      {explanation.next_step && <><dt>Next step</dt><dd>{explanation.next_step}</dd></>}
    </dl>
  );
}

/** Score bounds, evidence resolution and Silver / Gold / Platinum eligibility of one frozen run. */
export function CapabilityStanding({ result, run }: { result: Result; run: Run }) {
  const counts = stateCounts(result);
  const partCredit = isPartCredit(result);
  const causes = run.assessment?.decision_causes;
  return (
    <>
      <div className="stat-grid">
        <Stat label="Institutional AI capability"
          value={!partCredit && result.aggregation === 'independent_conditions' && result.condition_decision_coverage === 0 ? 'Review needed' : scoreLabel(result)}
          note={partCredit ? 'What the documents show, with partial credit' : result.exact_score === null ? 'Bounds: unresolved evidence is not counted as capability' : 'Exact score'} />
        <Stat label="Resolved indicator weight" value={`${result.assessment_coverage}%`} note="Evidence resolution, not model confidence" />
        <Stat label="Decided conditions" value={`${result.condition_decision_coverage}%`} note={`${counts.met} demonstrated · ${counts.not_met} shortfalls`} />
        <Stat label="Unknown / contradictory" value={counts.unknown + counts.conflicting} note="Remain unknown; never a pass or fail" />
      </div>
      {!partCredit && result.lower === 0 && result.exact_score === null && (
        <Notice tone="warn">Zero demonstrated so far does not establish zero capability. Review the evidence needed below.</Notice>
      )}
      {partCredit && (
        <Panel title="Nine readiness areas" sub="Part-credit score per area: a requirement earns credit for each part the documents evidence">
          {result.pillars.map((p) => {
            const d = result.documented?.pillars.find((x) => x.code === p.code);
            return d ? <Bar key={p.code} label={p.code} value={d.score} /> : (
              <div key={p.code} className="bar-row"><span>{p.code}</span><span className="muted">{pillarScoreLabel(result, p.code, p.lower, p.upper)}</span><b /></div>
            );
          })}
          <details className="indicator">
            <summary>How each area score was reached</summary>
            {result.documented?.pillars.some((x) => x.explanation) ? result.documented.pillars.map((x) => (
              <article key={x.code} className="condition"><b>{x.code}</b><ScoreExplanationBlock explanation={x.explanation} /></article>
            )) : <ScoreExplanationBlock />}
          </details>
        </Panel>
      )}
      {causes && (causes.unknown_evidentiary + causes.unknown_review + causes.unknown_processing) > 0 && (
        <Panel title="Why conditions are still unknown" sub="Unknown is read as missing evidence, a review hold or a processing problem">
          <div className="stat-grid">
            <Stat label="Evidence not supplied" value={causes.unknown_evidentiary} note="Upload or request the evidence" />
            <Stat label="Held for review" value={causes.unknown_review} note="Rejected claim or assessor disagreement" />
            <Stat label="Processing problem" value={causes.unknown_processing} note="Re-run once the cause is fixed" />
          </div>
        </Panel>
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
              <summary><b>{i.code}</b> {i.name}<span className="muted"> · {indicatorScoreLabel(a.result, i.code, i.lower, i.upper)}</span></summary>
              <section className="condition">
                <b>How this score was reached</b>
                <ScoreExplanationBlock explanation={i.explanation || a.result.documented?.indicators.find((x) => x.code === i.code)?.explanation} />
              </section>
              {conditions.map((c) => {
                const d = records.get(c.id);
                return (
                  <article key={c.id} className="condition">
                    <div>
                      <Pill tone={capabilityTone(c.state)} label={stateLabel(c.state)} /> <b>{c.id}</b> · {c.level}
                      {typeof d?.credit === 'number' && <span className="muted"> · credit {Math.round(d.credit * 100)}%</span>}
                      {d?.cause && c.state === 'unknown' && <span className="muted"> · {causeLabel(d.cause)}</span>}
                    </div>
                    <p>{c.text}</p>
                    {d?.reason && <p className="muted">{d.reason}</p>}
                    <ScoreExplanationBlock explanation={d?.explanation} placeholder={false} />
                    {!!d?.parts?.length && (
                      <ul className="plain-list">
                        {d.parts.map((part) => (
                          <li key={part.id}><Pill tone={partTone(part.credited_as)} label={partLabel(part.credited_as)} /> {part.finding || part.id}</li>
                        ))}
                      </ul>
                    )}
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
