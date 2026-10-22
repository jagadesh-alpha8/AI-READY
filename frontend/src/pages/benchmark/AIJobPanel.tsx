import React, { useCallback, useEffect, useState } from 'react';
import { Bot, Loader2, RotateCcw } from 'lucide-react';

import { aiJobAction, listAIJobs, startAIJob } from '../../api/benchmarks';
import type { StudioAIJob, StudioAIKind } from '../../api/benchmarks';
import { getErrorMessage } from '../../utils/errors';

/**
 * One AI preparation step in Benchmark Studio (backend services/studio_ai.py): its status and next action,
 * a Start / Retry button, model, confidence and citations, and -- once the draft is ready -- whatever the
 * page renders for review (`children`). AI output is never approved here: the page's own buttons apply or
 * dismiss it through the backend, which checks every transition.
 */
const NEXT: Record<string, string> = {
  queued: 'Waiting for an AI router…',
  running: 'AI is preparing the draft…',
  ready: 'Draft ready - review it below.',
  applied: 'Applied by a reviewer.',
  dismissed: 'Dismissed by a reviewer.',
  failed: 'Failed - nothing was applied. Retry, or do it by hand.',
};

const BADGE: Record<string, string> = {
  queued: 'badge-info', running: 'badge-info', ready: 'badge-warning', applied: 'badge-success',
  dismissed: 'badge-neutral', failed: 'badge-danger',
};

export function useAIJob(kind: StudioAIKind, targetId: string | null | undefined) {
  const [job, setJob] = useState<StudioAIJob | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    if (!targetId) return;
    try {
      const res = await listAIJobs({ kind, target_id: targetId, latest: true });
      setJob(res.data[0] || null);
    } catch (err) {
      setError(getErrorMessage(err, 'Could not load the AI status.'));
    }
  }, [kind, targetId]);
  useEffect(() => { setJob(null); load(); }, [load]);
  const active = job?.status === 'queued' || job?.status === 'running';
  useEffect(() => {
    if (!active) return undefined;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [active, load]);
  return { job, setJob, reload: load, error, setError };
}

export const AIJobPanel: React.FC<{
  kind: StudioAIKind;
  targetId: string;
  title: string;
  /** What starting it does, e.g. "Draft L3/L2/L1, evidence and applicability". */
  startLabel: string;
  /** Called when the job finishes or a reviewer acts on it, so the page can reload its own data. */
  onChanged?: () => void;
  /** The ready (or applied) draft, for review. */
  children?: (job: StudioAIJob, act: (action: 'dismiss' | 'apply' | 'propose' | 'candidate', body?: Record<string, unknown>) => Promise<void>) => React.ReactNode;
  disabled?: string;
}> = ({ kind, targetId, title, startLabel, onChanged, children, disabled }) => {
  const { job, setJob, error, setError } = useAIJob(kind, targetId);
  const [busy, setBusy] = useState(false);
  const [lastStatus, setLastStatus] = useState<string | undefined>();

  useEffect(() => {
    if (job && lastStatus && lastStatus !== job.status && onChanged) onChanged();
    setLastStatus(job?.status);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  const run = async (fn: () => Promise<{ data: StudioAIJob }>) => {
    setBusy(true);
    setError('');
    try {
      const res = await fn();
      setJob(res.data);
    } catch (err) {
      setError(getErrorMessage(err, 'The AI action failed.'));
    } finally {
      setBusy(false);
    }
  };
  const act = (action: 'dismiss' | 'apply' | 'propose' | 'candidate', body: Record<string, unknown> = {}) =>
    run(() => aiJobAction(job!.id, action, body));
  const active = job?.status === 'queued' || job?.status === 'running';
  const canStart = !job || ['applied', 'dismissed', 'ready'].includes(job.status);

  return (
    <div className="rounded-lg border border-brand-500/30 bg-brand-50/40 p-3 text-xs space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Bot className="w-4 h-4 text-brand-800" />
        <span className="font-bold text-ink-900">{title}</span>
        {job && <span className={BADGE[job.status]}>{job.status_label}</span>}
        {active && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-800" />}
        <span className="ml-auto flex gap-1.5">
          {job?.status === 'failed' && (
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => run(() => aiJobAction(job.id, 'retry'))}>
              <RotateCcw className="w-3 h-3" /> Retry
            </button>
          )}
          {canStart && (
            <button className="btn-secondary btn-sm" disabled={busy || !!disabled} title={disabled || ''}
              onClick={() => run(() => startAIJob(kind, targetId))}>
              {job ? 'Run again' : startLabel}
            </button>
          )}
        </span>
      </div>
      {disabled && !job && <p className="text-ink-500">{disabled}</p>}
      {job && <p className="text-ink-600">{NEXT[job.status]}</p>}
      {error && <p className="text-danger">{error}</p>}
      {job?.status === 'failed' && <p className="text-danger whitespace-pre-wrap">{job.error}</p>}
      {job && ['ready', 'applied', 'dismissed'].includes(job.status) && (
        <>
          <p className="text-ink-500">
            {job.model}{job.confidence != null ? ` · confidence ${Math.round(job.confidence * 100)}%` : ''}
            {job.finished_at ? ` · ${new Date(job.finished_at).toLocaleString()}` : ''}
            {job.decided_by ? ` · ${job.status} by ${job.decided_by}` : ''}
          </p>
          {children?.(job, act)}
          {job.citations.length > 0 && (
            <details>
              <summary className="cursor-pointer text-ink-600">Sources cited ({job.citations.length})</summary>
              <ul className="mt-1 space-y-0.5">
                {job.citations.map((c, i) => (
                  <li key={i} className="text-ink-600">
                    {Object.entries(c).map(([k, v]) => `${k}: ${typeof v === 'string' ? `"${v}"` : String(v)}`).join(' · ')}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {job.status === 'ready' && kind !== 'benchmark_content' && (
            <button className="text-ink-500 hover:underline" disabled={busy} onClick={() => act('dismiss')}>Dismiss this draft</button>
          )}
        </>
      )}
    </div>
  );
};
