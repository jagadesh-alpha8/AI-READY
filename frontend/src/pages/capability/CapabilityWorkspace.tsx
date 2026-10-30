import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import * as api from '../../api/capability';
import type {
  Action,
  Advice,
  ActionState,
  Assessment,
  Job,
  Result,
  Run,
  Recommendation,
} from '../../api/capability';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { useAccess } from '../../utils/access';
import { getErrorMessage } from '../../utils/errors';
import {
  scoreLabel,
  active,
  stateLabel,
  tierLabel,
  actionsFor,
  attempt,
} from './presentation';

type Mode = 'standing' | 'actions' | 'report';

/** Only GET loaders belong here. Cleanup prevents responses from a previous selection being displayed. */
export function useCapabilityRead<T>(
  fetcher: () => Promise<{ data: T }>,
  deps: React.DependencyList,
  enabled = true,
) {
  const fn = useRef(fetcher);
  fn.current = fetcher;
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const [state, setState] = useState<{
    data: T | null;
    error: string;
    loading: boolean;
  }>({ data: null, error: '', loading: enabled });
  useEffect(() => {
    let live = true;
    if (!enabled) {
      setState({ data: null, error: '', loading: false });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: '' }));
    fn.current()
      .then(({ data }) => {
        if (live) setState({ data, error: '', loading: false });
      })
      .catch((error) => {
        if (live)
          setState((s) => ({
            ...s,
            loading: false,
            error: getErrorMessage(error, 'Unable to load this assessment.'),
          }));
      });
    return () => {
      live = false;
    };
  }, [enabled, version, ...deps]);
  return { ...state, reload };
}
function usePoll(job: Job | null | undefined, reload: () => void) {
  const running = active(job);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(reload, 3000);
    return () => window.clearInterval(timer);
  }, [running, reload]);
}
const ErrorMessage = ({ message }: { message: string }) =>
  message ? (
    <p
      role="alert"
      className="panel-muted border border-danger-line text-danger"
    >
      {message}
    </p>
  ) : null;

export function CapabilitySummary({ result }: { result: Result }) {
  return (
    <section className="space-y-4" aria-label="Current capability standing">
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="glass-card p-5">
          <p className="text-sm text-ink-600">Institutional AI capability</p>
          <p className="text-3xl font-bold text-brand-800 mt-2">
            {scoreLabel(result)}
          </p>
          <p className="text-sm mt-2">
            {result.exact_score === null
              ? 'Bounds reflect unresolved evidence. The upper bound is not demonstrated capability.'
              : 'Exact score under this assessment’s experimental rubric.'}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-sm text-ink-600">Resolved indicator weight</p>
          <p className="text-3xl font-bold mt-2">
            {result.assessment_coverage}%
          </p>
          <p className="text-sm mt-2">
            Evidence resolution, separate from capability.
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-sm text-ink-600">Decided conditions</p>
          <p className="text-3xl font-bold mt-2">
            {result.condition_decision_coverage}%
          </p>
          <p className="text-sm mt-2">
            Unknown and conflicting conditions remain unresolved.
          </p>
        </div>
      </div>
      <div className="panel-muted text-sm">
        Experimental internal criteria · {result.methodology}. These tiers are
        not external accreditation standards. Evidence resolution is not model
        confidence.
      </div>
      <div className="grid sm:grid-cols-3 gap-4">
        {result.tiers.map((t) => (
          <div className="glass-card p-5" key={t.name}>
            <h3 className="font-bold">{t.name}</h3>
            <p>{tierLabel(t.eligibility)}</p>
            <p className="text-xs mt-2">
              Overall threshold {t.threshold}; pillar floor {t.pillar_floor};{' '}
              {Object.keys(t.gates).length} indicator gates.
            </p>
          </div>
        ))}
      </div>
      <details className="glass-card p-4">
        <summary className="cursor-pointer font-semibold">
          Nine pillar bounds
        </summary>
        <div className="grid sm:grid-cols-3 gap-3 mt-3">
          {result.pillars.map((p) => (
            <div key={p.code}>
              {p.code}: {p.lower}–{p.upper} / 100
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
export function CapabilityEvidence({ run }: { run: Run }) {
  const [filter, setFilter] = useState('all');
  const assessment = run.assessment!;
  const records = new Map(assessment.records.map((r) => [r.condition_id, r]));
  const labels = new Map(
    run.source_manifest.flatMap((d) =>
      d.pages.map(
        (p) => [p.page_id, `${d.filename} · version ${d.version}`] as const,
      ),
    ),
  );
  return (
    <section className="space-y-3" aria-label="Indicator evidence">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold">All 36 indicators</h2>
        <label>
          Show conditions{' '}
          <select
            className="input ml-2"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All evidence states</option>
            {['met', 'not_met', 'unknown', 'conflicting'].map((s) => (
              <option key={s} value={s}>
                {stateLabel(s)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-sm text-ink-600">
        Source excerpts and the institution profile are frozen to this
        assessment. New uploads require a new assessment; they do not update
        this score.
      </p>
      {assessment.result.indicators.map((i) => (
        <details className="glass-card p-4" key={i.code}>
          <summary className="cursor-pointer font-semibold">
            {i.code} · {i.name}{' '}
            <span className="font-normal">
              — level {i.lower_level}–{i.upper_level} · {i.lower}–{i.upper} /
              100
            </span>
          </summary>
          {i.conditions
            .filter((c) => filter === 'all' || c.state === filter)
            .map((c) => {
              const decision = records.get(c.id);
              return (
                <article
                  key={c.id}
                  id={c.id}
                  className="border-t border-line pt-4 mt-4 space-y-2"
                >
                  <h3 className="font-semibold">
                    {c.id} · {stateLabel(c.state)}
                  </h3>
                  <p>{c.text}</p>
                  <p className="text-sm text-ink-600">{decision?.reason}</p>
                  <p className="text-sm">
                    Completion evidence: {c.completion_evidence}
                  </p>
                  {decision?.citations.map((cite, index) => (
                    <blockquote
                      key={index}
                      className="panel-muted whitespace-pre-wrap"
                    >
                      <p>{cite.quote}</p>
                      <p className="text-xs mt-2">
                        {labels.get(cite.source_id) || 'Frozen source page'} ·
                        Page ID {cite.source_id}
                      </p>
                    </blockquote>
                  ))}
                </article>
              );
            })}
        </details>
      ))}
    </section>
  );
}
export function CapabilityPathways({
  assessment,
  recommendation,
  plan,
}: {
  assessment: Assessment;
  recommendation: Recommendation | null;
  plan?: Recommendation['plan'];
}) {
  const next = recommendation?.plan.next_overall || plan?.next_overall;
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-bold">Next improvements and tier pathways</h2>
      <p className="panel-muted">
        Sufficient conditional scenarios, not optimal plans or guaranteed score
        increases. Evidence must be reassessed before scores or tiers change.
      </p>
      {next && (
        <div className="glass-card p-4">
          <h3 className="font-semibold">
            Next overall threshold: {next.target ?? 'No higher threshold'}
          </h3>
          <p>
            {next.policy.basis} ({next.policy.version})
          </p>
          <p className="text-sm mt-2">
            {next.requirement_ids.length} requirements in this conditional
            scenario.
          </p>
        </div>
      )}
      <div className="grid md:grid-cols-3 gap-4">
        {assessment.pathways.map((p) => (
          <details key={p.target} className="glass-card p-4">
            <summary className="cursor-pointer font-bold">
              {p.target}:{' '}
              {p.already_demonstrated
                ? 'Already demonstrated'
                : `${p.requirement_ids.length} requirements`}
            </summary>
            <p className="my-3 text-sm">{p.note}</p>
            <p>
              Scenario sufficient:{' '}
              {p.scenario_sufficient
                ? 'Yes, if every listed requirement is demonstrated'
                : 'No'}
            </p>
            <ul className="list-disc pl-5 mt-3 text-sm">
              {p.requirement_ids.map((id) => (
                <li key={id}>{id}</li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

export function CapabilityWorkspace({ mode = 'standing' }: { mode?: Mode }) {
  const params = useParams<{ sprintId: string }>();
  const selected = useSelectedSprint();
  const sprint = params.sprintId || selected.sprintId;
  return sprint ? (
    <Workspace key={sprint} sprint={sprint} mode={mode} />
  ) : (
    <div className="panel-muted">
      Select a sprint to view its institutional capability assessment.
    </div>
  );
}
function Workspace({ sprint, mode }: { sprint: string; mode: Mode }) {
  const { can } = useAccess();
  const [query, setQuery] = useSearchParams();
  const [page, setPage] = useState(1);
  const runs = useCapabilityRead(
    () => api.listRuns(sprint, page),
    [sprint, page],
  );
  const runId = query.get('run') || runs.data?.results[0]?.id;
  const [population, setPopulation] = useState('');
  const [period, setPeriod] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ signature: string; key: string } | null>(null);
  const choose = (id: string) => {
    const q = new URLSearchParams(query);
    q.set('run', id);
    q.delete('advice');
    setQuery(q);
  };
  async function start(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    const body = {
      population: population.trim(),
      reference_period: period.trim(),
    };
    pending.current = attempt(pending.current, JSON.stringify(body), () =>
      crypto.randomUUID(),
    );
    try {
      const response = await api.startRun(sprint, body, pending.current.key);
      pending.current = null;
      choose(response.data.id);
      runs.reload();
    } catch (e) {
      setError(
        getErrorMessage(
          e,
          'Start failed. Retry with the same inputs to reuse this request safely.',
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <header data-tour="capability-header" className="glass-card p-6">
        <p className="eyebrow">Institutional AI capability</p>
        <h1 className="text-2xl font-bold mt-2">
          {mode === 'actions'
            ? 'Recommendations and action plan'
            : mode === 'report'
              ? 'Capability report and export'
              : 'Readiness and evidence'}
        </h1>
        <p className="text-ink-600 mt-2">
          Your institution’s demonstrated capability, unresolved evidence and
          next steps.
        </p>
        <nav
          className="flex flex-wrap gap-3 mt-4"
          aria-label="Capability sections"
        >
          {[
            ['score', 'Standing'],
            ['recommendations', 'Recommendations'],
            ['report', 'Report'],
          ].map(([route, label]) => (
            <Link
              key={route}
              className="btn-secondary"
              to={`/sprint/${sprint}/${route}${runId ? `?run=${runId}${query.has('advice') ? `&advice=${query.get('advice') || ''}` : ''}` : ''}`}
            >
              {label}
            </Link>
          ))}
        </nav>
      </header>
      <ErrorMessage message={runs.error} />
      {runs.error && (
        <button className="btn-secondary" onClick={runs.reload}>
          Retry history
        </button>
      )}
      <section
        data-tour="capability-history"
        className="glass-card p-4 space-y-3"
      >
        <label className="font-semibold block">
          Assessment history{' '}
          <select
            aria-label="Assessment history"
            className="input block w-full mt-2"
            value={runId || ''}
            onChange={(e) => choose(e.target.value)}
          >
            <option value="">Select assessment</option>
            {runId && !runs.data?.results.some((r) => r.id === runId) && (
              <option value={runId}>Selected assessment {runId}</option>
            )}
            {runs.data?.results.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString()} · {r.status} ·{' '}
                {r.reference_period}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-3">
          <button
            className="btn-secondary"
            disabled={!runs.data?.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            Newer history
          </button>
          <button
            className="btn-secondary"
            disabled={!runs.data?.next}
            onClick={() => setPage((p) => p + 1)}
          >
            Older history
          </button>
          <button className="btn-secondary" onClick={runs.reload}>
            Refresh
          </button>
        </div>
      </section>
      {can('sprint.manage') && (
        <details data-tour="capability-start" className="glass-card p-4">
          <summary className="cursor-pointer font-semibold">
            Start a new evidence assessment
          </summary>
          <form onSubmit={start} className="space-y-3 mt-3">
            <p>
              Starting uses model credits within configured request and cost
              limits. Refreshing and viewing history do not. New uploads are
              assessed only by a new run.
            </p>
            <label className="block">
              Population to assess
              <input
                required
                maxLength={2000}
                className="input block w-full mt-1"
                value={population}
                onChange={(e) => setPopulation(e.target.value)}
                placeholder="All faculty and students across the institution"
              />
            </label>
            <label className="block">
              Reference period
              <input
                required
                maxLength={200}
                className="input block w-full mt-1"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                placeholder="2025–26"
              />
            </label>
            <p className="text-sm">
              {runs.data?.enabled
                ? 'Inference enabled. Confirm the scope and period before starting.'
                : 'Assessment inference is disabled by the deployment administrator.'}
            </p>
            <button
              className="btn-primary whitespace-normal max-w-full"
              disabled={
                busy ||
                !runs.data?.enabled ||
                runs.data.results.some(active) ||
                !population.trim() ||
                !period.trim()
              }
            >
              {busy ? 'Starting…' : 'Start assessment (uses model credits)'}
            </button>
            <ErrorMessage message={error} />
          </form>
        </details>
      )}
      {runId ? (
        <RunWorkspace
          key={runId}
          sprint={sprint}
          runId={runId}
          mode={mode}
          refreshHistory={runs.reload}
        />
      ) : (
        <p className="panel-muted">
          {runs.loading
            ? 'Loading assessment history…'
            : 'No capability assessment exists yet. Upload and process evidence, then start an assessment. No score has been inferred from legacy CRI.'}
        </p>
      )}
      <details className="glass-card p-4">
        <summary>Legacy CRI records</summary>
        <p className="text-sm mt-2">
          Historical CRI and its approval workflow use the previous methodology.
          They do not determine capability scores or block these reports.
        </p>
        <div className="flex gap-3 flex-wrap mt-3">
          <Link to={`/sprint/${sprint}/legacy-score`}>Legacy score</Link>
          <Link to={`/sprint/${sprint}/approval`}>Legacy baseline</Link>
          <Link to={`/sprint/${sprint}/legacy-recommendations`}>
            Legacy advice
          </Link>
          <Link to={`/sprint/${sprint}/legacy-report`}>Legacy reports</Link>
        </div>
      </details>
    </div>
  );
}
function RunWorkspace({
  sprint,
  runId,
  mode,
  refreshHistory,
}: {
  sprint: string;
  runId: string;
  mode: Mode;
  refreshHistory: () => void;
}) {
  const { can } = useAccess();
  const run = useCapabilityRead(
    () => api.getRun(sprint, runId),
    [sprint, runId],
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  usePoll(run.data, run.reload);
  const lastStatus = useRef<string>();
  useEffect(() => {
    if (run.data && lastStatus.current !== run.data.status) {
      lastStatus.current = run.data.status;
      refreshHistory();
    }
  }, [run.data?.status, refreshHistory]);
  if (!run.data)
    return (
      <section>
        <ErrorMessage message={run.error} />
        <button className="btn-secondary" onClick={run.reload}>
          {run.loading ? 'Loading assessment…' : 'Retry assessment'}
        </button>
      </section>
    );
  const data = run.data;
  async function cancel() {
    setBusy(true);
    setError('');
    try {
      await api.cancelRun(sprint, runId);
      run.reload();
      refreshHistory();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <section className="glass-card p-4">
        <h2 className="font-bold">{data.profile.name}</h2>
        <p>
          {data.population} · {data.reference_period} · {data.status}
        </p>
        <p className="text-sm">
          Requests reserved: {data.requests_reserved}; conservative cost
          reserved: ${data.reserved_cost_usd}.
        </p>
        <p className="text-xs break-all mt-2">
          Run {runId} · Frozen inputs {data.inputs_hash}
        </p>
        {data.stalled && (
          <p role="alert">
            This job may be stalled. Cancel it before explicitly starting a new
            budgeted run; it will not replay automatically.
          </p>
        )}
        {active(data) && can('sprint.manage') && (
          <button
            className="btn-secondary mt-3"
            disabled={busy}
            onClick={cancel}
          >
            Cancel assessment
          </button>
        )}
        <ErrorMessage message={run.error || error} />
      </section>
      {!data.assessment ? (
        <div className="panel-muted">
          <h2 className="font-semibold">No completed capability score</h2>
          <p>
            {data.completed_indicators || 0} / 36 indicators processed;{' '}
            {data.partial_decisions.length} partial condition decisions
            retained.
          </p>
          {data.error && (
            <p>
              {data.error.error_code}: {data.error.next_action}
            </p>
          )}
          <p>
            Incomplete, failed and cancelled runs never publish a headline
            score.
          </p>
        </div>
      ) : (
        <>
          <CapabilitySummary result={data.assessment.result} />
          <RecommendationWorkspace
            key={runId}
            sprint={sprint}
            run={data}
            mode={mode}
          />
          {mode === 'standing' && <CapabilityEvidence run={data} />}
        </>
      )}
    </div>
  );
}
function RecommendationWorkspace({
  sprint,
  run,
  mode,
}: {
  sprint: string;
  run: Run;
  mode: Mode;
}) {
  const { can } = useAccess();
  const [query, setQuery] = useSearchParams();
  const [page, setPage] = useState(1);
  const history = useCapabilityRead(
    () => api.listAdvice(sprint, run.id, page),
    [sprint, run.id, page],
  );
  const id = query.has('advice')
    ? query.get('advice') || undefined
    : history.data?.results[0]?.id;
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<string | null>(null);
  const choose = (id: string) => {
    const q = new URLSearchParams(query);
    q.set('run', run.id);
    q.set('advice', id);
    setQuery(q);
  };
  async function start() {
    setBusy(true);
    setError('');
    pending.current ||= crypto.randomUUID();
    try {
      const response = await api.startAdvice(sprint, run.id, pending.current);
      pending.current = null;
      choose(response.data.id);
      history.reload();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4">
      <div className="glass-card p-4 space-y-3">
        <h2 className="font-bold">Recommendation versions</h2>
        <p>
          Deterministic plans are available immediately. Tailoring uses model
          credits only when you explicitly request it. Missing evidence gets
          evidence requests, not development prescriptions.
        </p>
        <label className="block">
          Version{' '}
          <select
            aria-label="Recommendation version"
            className="input block w-full mt-2"
            value={id || ''}
            onChange={(e) => choose(e.target.value)}
          >
            <option value="">Deterministic assessment plan</option>
            {id && !history.data?.results.some((r) => r.id === id) && (
              <option value={id}>Selected version {id}</option>
            )}
            {history.data?.results.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString()} · {r.status}
              </option>
            ))}
          </select>
        </label>
        <div className="flex gap-3 flex-wrap">
          <button
            className="btn-secondary"
            disabled={!history.data?.previous}
            onClick={() => setPage((p) => p - 1)}
          >
            Newer versions
          </button>
          <button
            className="btn-secondary"
            disabled={!history.data?.next}
            onClick={() => setPage((p) => p + 1)}
          >
            Older versions
          </button>
          {can('sprint.manage') && (
            <button
              className="btn-primary whitespace-normal max-w-full"
              disabled={
                busy ||
                !history.data?.enabled ||
                history.data.results.some(active)
              }
              onClick={start}
            >
              {busy ? 'Starting…' : 'Tailor a new version (uses model credits)'}
            </button>
          )}
          <button className="btn-secondary" onClick={history.reload}>
            Refresh versions
          </button>
        </div>
        {history.data && !history.data.enabled && (
          <p className="text-sm">
            Tailoring is disabled. The deterministic plan and historical
            versions remain readable.
          </p>
        )}
        <ErrorMessage message={history.error || error} />
      </div>
      {id ? (
        <AdviceWorkspace
          key={id}
          sprint={sprint}
          run={run}
          id={id}
          mode={mode}
          refreshHistory={history.reload}
        />
      ) : (
        <>
          <CapabilityPathways
            assessment={run.assessment!}
            recommendation={null}
            plan={run.deterministic_plan}
          />
          {mode === 'actions' && (
            <Actions
              sprint={sprint}
              run={run}
              recommendation={null}
              reload={() => {}}
            />
          )}
          {mode === 'report' && <ReportExport sprint={sprint} run={run} />}
        </>
      )}
    </section>
  );
}
function AdviceWorkspace({
  sprint,
  run,
  id,
  mode,
  refreshHistory,
}: {
  sprint: string;
  run: Run;
  id: string;
  mode: Mode;
  refreshHistory: () => void;
}) {
  const { can } = useAccess();
  const detail = useCapabilityRead(
    () => api.getAdvice(sprint, run.id, id),
    [sprint, run.id, id],
  );
  const [error, setError] = useState('');
  usePoll(detail.data, detail.reload);
  const lastStatus = useRef<string>();
  useEffect(() => {
    if (detail.data && lastStatus.current !== detail.data.status) {
      lastStatus.current = detail.data.status;
      refreshHistory();
    }
  }, [detail.data?.status, refreshHistory]);
  if (!detail.data)
    return (
      <div>
        <ErrorMessage message={detail.error} />
        <button onClick={detail.reload} className="btn-secondary">
          {detail.loading ? 'Loading version…' : 'Retry version'}
        </button>
      </div>
    );
  const recommendation = detail.data;
  async function cancel() {
    try {
      await api.cancelAdvice(sprint, run.id, id);
      detail.reload();
      refreshHistory();
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }
  return (
    <div className="space-y-4">
      <div className="panel-muted">
        <p>
          Version {id} · {recommendation.status} ·{' '}
          {recommendation.fallback
            ? 'Deterministic plan; model tailoring is unavailable or not needed.'
            : 'Grounded model advice; proposed steps require local feasibility review.'}
        </p>
        <p>
          Requests reserved: {recommendation.requests_reserved}; cost reserved:
          ${recommendation.reserved_cost_usd}.
        </p>
        {recommendation.stalled && (
          <p role="alert">
            Generation may be stalled; cancel and inspect billing before
            starting another version.
          </p>
        )}
        {recommendation.error && (
          <p>
            {recommendation.error.error_code}:{' '}
            {recommendation.error.next_action}
          </p>
        )}
        {active(recommendation) && can('sprint.manage') && (
          <button className="btn-secondary" onClick={cancel}>
            Cancel tailoring
          </button>
        )}
        <ErrorMessage message={detail.error || error} />
      </div>
      <CapabilityPathways
        assessment={run.assessment!}
        recommendation={recommendation}
      />
      {mode === 'actions' && (
        <Actions
          sprint={sprint}
          run={run}
          recommendation={recommendation}
          reload={detail.reload}
        />
      )}
      {mode === 'report' && (
        <ReportExport
          sprint={sprint}
          run={run}
          recommendation={recommendation}
        />
      )}
    </div>
  );
}
function Actions({
  sprint,
  run,
  recommendation,
  reload,
}: {
  sprint: string;
  run: Run;
  recommendation: Recommendation | null;
  reload: () => void;
}) {
  const actions = actionsFor(
    run.assessment!,
    recommendation,
    run.deterministic_plan,
  );
  const [filter, setFilter] = useState('all');
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-bold">Requirement-linked actions</h2>
      <p>
        Completing an action updates workflow only. Scores change only after
        evidence is reassessed.
      </p>
      <label>
        Action type{' '}
        <select
          className="input ml-2"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All</option>
          <option value="supply_evidence">Evidence requests</option>
          <option value="resolve_contradiction">
            Contradiction resolution
          </option>
          <option value="develop_capability">
            Documented capability shortfalls
          </option>
        </select>
      </label>
      {actions
        .filter((a) => filter === 'all' || a.type === filter)
        .map((action) => (
          <ActionCard
            key={`${recommendation?.id || 'base'}:${action.id}`}
            sprint={sprint}
            runId={run.id}
            action={action}
            advice={recommendation?.tailoring?.advice.find(
              (a) => a.condition_id === action.id,
            )}
            recommendation={recommendation}
            reload={reload}
          />
        ))}
      {!actions.length && (
        <p className="panel-muted">
          No additional actions are selected by this assessment’s deterministic
          plan.
        </p>
      )}
    </section>
  );
}
function ActionCard({
  sprint,
  runId,
  action,
  advice,
  recommendation,
  reload,
}: {
  sprint: string;
  runId: string;
  action: Action;
  advice?: Advice;
  recommendation: Recommendation | null;
  reload: () => void;
}) {
  const { can } = useAccess();
  const saved = recommendation?.action_states.find(
    (s) => s.condition_id === action.id,
  );
  const [owner, setOwner] = useState(saved?.owner || '');
  const [status, setStatus] = useState<ActionState['status']>(
    saved?.status || 'proposed',
  );
  const [feasibility, setFeasibility] = useState<ActionState['feasibility']>(
    saved?.feasibility || 'unreviewed',
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!recommendation) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await api.updateAction(sprint, runId, recommendation.id, action.id, {
        owner,
        status,
        feasibility,
      });
      setMessage('Workflow saved. Assessment scores unchanged.');
      reload();
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="glass-card p-4">
      <summary className="cursor-pointer font-semibold">
        {action.id} · {action.type.replace(/_/g, ' ')} ·{' '}
        {status.replace(/_/g, ' ')}
      </summary>
      <div className="space-y-3 mt-4">
        <p>{action.requirement}</p>
        <p>{action.suggestion}</p>
        <p className="text-sm">
          Canonical completion evidence: {action.completion_evidence}
        </p>
        {advice && (
          <>
            <p>
              Suggested role: {advice.suggested_role}. Effort estimate:{' '}
              {advice.effort}.
            </p>
            <ol className="list-decimal pl-6">
              {advice.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
            <p>Suggested completion evidence: {advice.completion_evidence}</p>
            <p>
              Dependencies: {advice.dependencies.join(', ') || 'None proposed'}
            </p>
            {advice.basis.map((c, i) => (
              <blockquote className="panel-muted" key={i}>
                {c.quote}
                <p className="text-xs mt-2">Frozen source page {c.source_id}</p>
              </blockquote>
            ))}
          </>
        )}
        {recommendation && can('sprint.manage') ? (
          <form className="grid sm:grid-cols-3 gap-3" onSubmit={save}>
            <label>
              Owner
              <input
                className="input w-full"
                maxLength={200}
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
              />
            </label>
            <label>
              Feasibility
              <select
                className="input w-full"
                value={feasibility}
                onChange={(e) =>
                  setFeasibility(e.target.value as ActionState['feasibility'])
                }
              >
                {['unreviewed', 'feasible', 'blocked'].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select
                className="input w-full"
                value={status}
                onChange={(e) =>
                  setStatus(e.target.value as ActionState['status'])
                }
              >
                {['proposed', 'in_progress', 'completed', 'dismissed'].map(
                  (s) => (
                    <option key={s} value={s}>
                      {s.replace(/_/g, ' ')}
                    </option>
                  ),
                )}
              </select>
            </label>
            <button className="btn-secondary" disabled={busy}>
              {busy ? 'Saving…' : 'Save workflow'}
            </button>
          </form>
        ) : (
          <p className="text-sm">
            Create a recommendation version to track ownership and completion
            independently of scores.
          </p>
        )}
        <p role="status">{message}</p>
        <ErrorMessage message={error} />
      </div>
    </details>
  );
}
function ReportExport({
  sprint,
  run,
  recommendation,
}: {
  sprint: string;
  run: Run;
  recommendation?: Recommendation;
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function download(format: 'html' | 'json') {
    setBusy(true);
    setError('');
    try {
      await api.downloadCapabilityReport(
        sprint,
        run.id,
        format,
        recommendation?.id,
      );
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="glass-card p-5 space-y-3">
      <h2 className="text-xl font-bold">Export this pinned assessment</h2>
      <p>
        Includes all 36 indicators, condition evidence, source versions,
        uncertainty and tier pathways
        {recommendation
          ? ', plus this recommendation version and current workflow'
          : ''}
        . No baseline approval is required.
      </p>
      <p>
        Open the downloaded HTML report in your browser, then choose Print →
        Save as PDF. Exporting does not invoke a model.
      </p>
      <div className="flex flex-wrap gap-3">
        <button
          className="btn-primary whitespace-normal max-w-full"
          disabled={busy}
          onClick={() => download('html')}
        >
          Download printable HTML report
        </button>
        <button
          className="btn-secondary"
          disabled={busy}
          onClick={() => download('json')}
        >
          Download assessment JSON
        </button>
      </div>
      <ErrorMessage message={error} />
    </section>
  );
}
