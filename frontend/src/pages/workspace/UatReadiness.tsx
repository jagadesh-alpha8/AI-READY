import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardCheck, Circle, XCircle } from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { listSprintDocuments } from '../../api/documents';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { listReports } from '../../api/reports';
import { getBaseline } from '../../api/baseline';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { PageHeader } from '../../components/PageHeader';
import type { Fact, Gap, Report, Sprint, SprintBaseline, SprintDocument } from '../../types';

/**
 * UAT Readiness — is this engagement actually ready to hand over?
 *
 * Every check below is COMPUTED from the sprint's real state. The prototype
 * shipped a hand-written checklist of engineering tasks ("Responsive design",
 * "Backend contracts documented") which described the *product*, not the
 * client's engagement, and which nothing could ever tick automatically.
 *
 * What this cannot do is record a sign-off: there is no model for that. It
 * answers "is it ready", not "has the client accepted it".
 */

type CheckState = 'pass' | 'fail' | 'unknown';

interface Check {
  label: string;
  state: CheckState;
  detail: string;
  /** Where to go and fix it. */
  route?: string;
  blocking: boolean;
}

const STATE_ICON = {
  pass: CheckCircle2,
  fail: XCircle,
  unknown: Circle,
} as const;

const STATE_TONE = {
  pass: 'text-success',
  fail: 'text-danger',
  unknown: 'text-ink-500/60',
} as const;

export const UatReadiness: React.FC = () => {
  const navigate = useNavigate();
  // The selected sprint is shared by every page (context/SelectedSprintContext.tsx).
  const { sprintId: selectedSprintId } = useSelectedSprint();

  const { data: sprints, loading, error, refetch } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = selectedSprintId;
  const enabled = !!activeSprintId;

  const { data: documents } = useApiResource<SprintDocument[]>(
    () => listSprintDocuments(activeSprintId), [activeSprintId], enabled);
  const { data: facts } = useApiResource<Fact[]>(
    () => listSprintFacts(activeSprintId), [activeSprintId], enabled);
  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId), [activeSprintId], enabled);
  const { data: reports } = useApiResource<Report[]>(
    () => listReports(activeSprintId), [activeSprintId], enabled);
  const { data: baseline } = useApiResource<SprintBaseline>(
    () => getBaseline(activeSprintId), [activeSprintId], enabled);

  const checks = useMemo<Check[]>(() => {
    const docs = documents ?? [];
    const allGaps = gaps ?? [];
    const openGaps = allGaps.filter((g) => g.status === 'open' || g.status === 'in_progress');
    const missingDocs = openGaps.filter((g) => g.gap_type === 'missing_document');
    const blocking = openGaps.filter((g) => g.priority === 'blocking');
    const unconfirmed = (facts ?? []).filter((f) => f.status === 'extracted');
    const failedDocs = docs.filter((d) => d.status === 'failed' || d.status === 'rejected');
    const unprocessed = docs.filter((d) => d.status !== 'processed');
    const ready = (reports ?? []).filter((r) => r.status === 'ready');
    const baselineStatus = baseline?.baseline?.status ?? null;

    return [
      {
        label: 'Required documents provided',
        state: allGaps.length === 0 ? 'unknown' : missingDocs.length === 0 ? 'pass' : 'fail',
        detail: allGaps.length === 0
          ? 'Not assessed — gap detection has not run on this sprint yet.'
          : missingDocs.length === 0
            ? 'Every required document type has been uploaded.'
            : `${missingDocs.length} required document type(s) still missing.`,
        route: `/sprint/${activeSprintId}/upload`,
        blocking: true,
      },
      {
        label: 'All documents processed',
        state: docs.length === 0 ? 'unknown' : unprocessed.length === 0 ? 'pass' : 'fail',
        detail: docs.length === 0
          ? 'No documents uploaded yet.'
          : unprocessed.length === 0
            ? `All ${docs.length} document(s) processed successfully.`
            : `${unprocessed.length} of ${docs.length} not processed`
              + (failedDocs.length > 0 ? `, ${failedDocs.length} failed.` : '.'),
        route: `/sprint/${activeSprintId}/monitor`,
        blocking: true,
      },
      {
        label: 'Extracted facts reviewed',
        state: (facts ?? []).length === 0 ? 'unknown' : unconfirmed.length === 0 ? 'pass' : 'fail',
        detail: (facts ?? []).length === 0
          ? 'No facts extracted yet.'
          : unconfirmed.length === 0
            ? 'Every extracted fact has been confirmed, corrected or rejected.'
            : `${unconfirmed.length} fact(s) still awaiting an owner's review.`,
        route: `/sprint/${activeSprintId}/facts`,
        blocking: true,
      },
      {
        label: 'No blocking gaps outstanding',
        state: allGaps.length === 0 ? 'unknown' : blocking.length === 0 ? 'pass' : 'fail',
        detail: allGaps.length === 0
          ? 'Not assessed.'
          : blocking.length === 0
            ? `${openGaps.length} gap(s) open, none blocking.`
            : `${blocking.length} blocking gap(s) must be resolved before sign-off.`,
        route: `/sprint/${activeSprintId}/gaps`,
        blocking: true,
      },
      {
        label: 'Baseline approved',
        state: baselineStatus === null ? 'unknown'
          : baselineStatus === 'approved' || baselineStatus === 'provisional' ? 'pass' : 'fail',
        detail: baselineStatus === null
          ? 'No baseline record yet.'
          : baselineStatus === 'approved' ? 'Baseline approved and the score is locked.'
            : baselineStatus === 'provisional'
              ? 'Approved provisionally — blocking gaps were outstanding at approval.'
              : `Baseline is ${String(baselineStatus).replace(/_/g, ' ')}.`,
        route: `/sprint/${activeSprintId}/approval`,
        blocking: true,
      },
      {
        label: 'Report generated',
        state: (reports ?? []).length === 0 ? 'fail' : ready.length > 0 ? 'pass' : 'fail',
        detail: ready.length > 0
          ? `${ready.length} report version(s) ready for delivery.`
          : 'No report has been generated for this sprint.',
        route: `/sprint/${activeSprintId}/report`,
        blocking: false,
      },
    ];
  }, [documents, facts, gaps, reports, baseline, activeSprintId]);

  const passed = checks.filter((c) => c.state === 'pass').length;
  const failing = checks.filter((c) => c.state === 'fail');
  const blockers = failing.filter((c) => c.blocking);
  const unknown = checks.filter((c) => c.state === 'unknown').length;

  if (loading) return <LoadingState message="Loading sprints…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={ClipboardCheck}
          title="UAT Readiness"
          description="Whether this engagement is ready to hand over — every check computed from the sprint's real state."
        />
        <EmptyState message="No sprints yet. There is nothing to sign off until one runs." />
      </div>
    );
  }

  if (!activeSprintId) return <SelectSprintPrompt />;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={ClipboardCheck}
        title="UAT Readiness"
        description="Whether this engagement is ready to hand over — every check computed from the sprint's real state."
      />


      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Metric label="Checks passing" value={`${passed} / ${checks.length}`} tone={passed === checks.length ? 'success' : 'default'} />
        <Metric label="Blocking failures" value={blockers.length} tone={blockers.length > 0 ? 'danger' : 'success'} />
        <Metric label="Not yet assessed" value={unknown} />
        <Metric
          label="Ready to hand over"
          value={blockers.length === 0 && unknown === 0 ? 'Yes' : 'No'}
          tone={blockers.length === 0 && unknown === 0 ? 'success' : 'danger'}
        />
      </div>

      {blockers.length > 0 && (
        <div className="rounded-lg border border-danger-line bg-danger-bg p-4 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
          <p className="text-sm text-ink-600 min-w-0">
            <strong className="text-danger">Not ready to hand over. </strong>
            {blockers.length} blocking check{blockers.length === 1 ? '' : 's'} still failing —
            each row below links to where it is fixed.
          </p>
        </div>
      )}

      <div className="space-y-2">
        {checks.map((check) => {
          const Icon = STATE_ICON[check.state];
          return (
            <div key={check.label} className="glass-card p-4 flex items-start gap-3">
              <Icon className={`w-[18px] h-[18px] shrink-0 mt-0.5 ${STATE_TONE[check.state]}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink-900">{check.label}</p>
                <p className="text-xs text-ink-600 mt-0.5">{check.detail}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {check.blocking && check.state === 'fail' && (
                  <span className="badge badge-danger">Blocking</span>
                )}
                {check.route && check.state !== 'pass' && (
                  <button
                    type="button"
                    onClick={() => navigate(check.route!)}
                    className="btn-secondary btn-sm"
                  >
                    <span>Fix</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-sm text-ink-500">
        These checks say whether the work is ready. They do not record that a client has accepted it
        — there is no sign-off model in the platform, so acceptance still happens outside it.
      </p>
    </div>
  );
};

const Metric: React.FC<{
  label: string;
  value: number | string;
  tone?: 'default' | 'danger' | 'success';
}> = ({ label, value, tone = 'default' }) => (
  <div className="glass-card p-5">
    <p className="text-sm font-medium text-ink-500">{label}</p>
    <p className={`text-2xl font-bold mt-1 tabular-nums ${
      tone === 'danger' ? 'text-danger' : tone === 'success' ? 'text-success' : 'text-ink-900'
    }`}>
      {value}
    </p>
  </div>
);
