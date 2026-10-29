import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, ArrowRight, Bell, Calendar, FileText, Info, Lock, ScanLine,
} from 'lucide-react';

import { listSprints } from '../../api/sprints';
import { SelectSprintPrompt } from '../../components/SprintContextBar';
import { useSelectedSprint } from '../../context/SelectedSprintContext';
import { listSprintDocuments } from '../../api/documents';
import { listSprintFacts } from '../../api/facts';
import { listSprintGaps } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { EmptyState, ErrorState, LoadingState } from '../../components/ApiStates';
import { FilterPills, PageHeader } from '../../components/PageHeader';
import type { Fact, Gap, Sprint, SprintDocument } from '../../types';
import { useAccess } from '../../utils/access';

/**
 * Reminders — what is waiting on someone, derived from the sprint's real state.
 *
 * ⚠ Nothing here is *sent*. There is no scheduled-job runner configured and no
 * email provider, so this is a standing "what needs attention" view rather
 * than a notification system. The prototype's version listed hardcoded
 * deadlines that nothing produced; these are computed, and each links to the
 * screen that clears it.
 */

type Severity = 'critical' | 'high' | 'medium';

interface Alert {
  id: string;
  title: string;
  detail: string;
  severity: Severity;
  icon: React.ElementType;
  route?: string;
}

const SEVERITY_BADGE: Record<Severity, string> = {
  critical: 'badge-danger',
  high: 'badge-warning',
  medium: 'badge-info',
};

const SEVERITY_TILE: Record<Severity, string> = {
  critical: 'bg-danger-bg text-danger',
  high: 'bg-warning-bg text-warning',
  medium: 'bg-info-bg text-info',
};

const DAY = 86_400_000;

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / DAY);
}

export const Reminders: React.FC = () => {
  const { canSee } = useAccess();
  const reviewStep = canSee('sprint-confirmation') ? 'confirmation' : 'facts';
  const navigate = useNavigate();
  // The selected sprint is shared by every page (context/SelectedSprintContext.tsx).
  const { sprintId: selectedSprintId } = useSelectedSprint();
  const [filter, setFilter] = useState<Severity | 'all'>('all');

  const { data: sprints, loading, error, refetch } =
    useApiResource<Sprint[]>(() => listSprints(), []);

  const activeSprintId = selectedSprintId;
  const enabled = !!activeSprintId;
  const sprint = sprints?.find((s) => s.id === activeSprintId);

  const { data: documents } = useApiResource<SprintDocument[]>(
    () => listSprintDocuments(activeSprintId), [activeSprintId], enabled);
  const { data: facts } = useApiResource<Fact[]>(
    () => listSprintFacts(activeSprintId), [activeSprintId], enabled);
  const { data: gaps } = useApiResource<Gap[]>(
    () => listSprintGaps(activeSprintId), [activeSprintId], enabled);

  const alerts = useMemo<Alert[]>(() => {
    const list: Alert[] = [];
    const docs = documents ?? [];
    const openGaps = (gaps ?? []).filter((g) => g.status === 'open' || g.status === 'in_progress');
    const blocking = openGaps.filter((g) => g.priority === 'blocking');
    const missingDocs = openGaps.filter((g) => g.gap_type === 'missing_document');
    const unconfirmed = (facts ?? []).filter((f) => f.status === 'extracted');
    const failedDocs = docs.filter((d) => d.status === 'failed' || d.status === 'rejected');
    const ocrFlagged = docs.filter((d) => d.ocr_warnings.length > 0);

    if (blocking.length > 0) {
      list.push({
        id: 'blocking',
        title: `${blocking.length} blocking gap${blocking.length === 1 ? '' : 's'} open`,
        detail: 'The baseline cannot be approved while any of these remain.',
        severity: 'critical', icon: Lock,
        route: `/sprint/${activeSprintId}/gaps`,
      });
    }

    if (missingDocs.length > 0) {
      list.push({
        id: 'missing-docs',
        title: `${missingDocs.length} required document${missingDocs.length === 1 ? '' : 's'} not provided`,
        detail: missingDocs.slice(0, 3).map((g) => g.title.replace(/^Missing /, '')).join(' · ')
          + (missingDocs.length > 3 ? ` · and ${missingDocs.length - 3} more` : ''),
        severity: 'critical', icon: FileText,
        route: `/sprint/${activeSprintId}/upload`,
      });
    }

    if (failedDocs.length > 0) {
      list.push({
        id: 'failed-docs',
        title: `${failedDocs.length} document${failedDocs.length === 1 ? '' : 's'} failed processing`,
        detail: 'These produced no facts. They may be corrupt, password-protected, or an unreadable format.',
        severity: 'high', icon: AlertTriangle,
        route: `/sprint/${activeSprintId}/monitor`,
      });
    }

    const overdue = sprint?.target_completion_date ? daysSince(sprint.target_completion_date) : null;
    if (overdue !== null && overdue > 0 && sprint?.status !== 'completed' && sprint?.status !== 'archived') {
      list.push({
        id: 'overdue',
        title: `Sprint is ${overdue} day${overdue === 1 ? '' : 's'} past its target date`,
        detail: `Target was ${sprint?.target_completion_date}. The sprint is still ${String(sprint?.status).replace(/_/g, ' ')}.`,
        severity: 'high', icon: Calendar,
      });
    }

    if (unconfirmed.length > 0) {
      list.push({
        id: 'unconfirmed',
        title: `${unconfirmed.length} extracted fact${unconfirmed.length === 1 ? '' : 's'} awaiting review`,
        detail: 'An unconfirmed fact contributes nothing to the score until an owner accepts it.',
        severity: unconfirmed.length > 50 ? 'high' : 'medium', icon: Bell,
        route: `/sprint/${activeSprintId}/${reviewStep}`,
      });
    }

    if (ocrFlagged.length > 0) {
      list.push({
        id: 'ocr',
        title: `${ocrFlagged.length} document${ocrFlagged.length === 1 ? '' : 's'} with unreadable pages`,
        detail: 'Scanned pages were flagged and skipped — there is no OCR backend, so their content is missing entirely.',
        severity: 'medium', icon: ScanLine,
        route: '/evidence',
      });
    }

    const order: Severity[] = ['critical', 'high', 'medium'];
    return list.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
  }, [documents, facts, gaps, sprint, activeSprintId, reviewStep]);

  const visible = filter === 'all' ? alerts : alerts.filter((a) => a.severity === filter);

  if (loading) return <LoadingState message="Loading sprints…" />;
  if (error) return <ErrorState message={error} onRetry={refetch} />;

  if (!sprints || sprints.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Bell}
          title="Reminders"
          description="What is waiting on someone — computed from the sprint's real state."
        />
        <EmptyState message="No sprints yet. Nothing to chase." />
      </div>
    );
  }

  if (!activeSprintId) return <SelectSprintPrompt />;

  return (
    <div className="space-y-6">
      <PageHeader
        dataTour="reminders-header"
        icon={Bell}
        title="Reminders"
        description="What is waiting on someone — computed from the sprint's real state."
      />


      <div className="rounded-lg border border-info-line bg-info-bg p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
        <p className="text-sm text-ink-600 min-w-0">
          <strong className="text-info">Nothing is sent. </strong>
          These are computed from this sprint whenever you open the page. Actually delivering a
          reminder needs a scheduled-job runner and an email provider — neither is configured, and
          Celery Beat is deliberately absent.
        </p>
      </div>

      {alerts.length === 0 ? (
        <EmptyState message="Nothing needs attention on this sprint." />
      ) : (
        <>
          <div data-tour="reminders-filters">
            <FilterPills
              options={[
                { id: 'all', label: 'All', count: alerts.length },
                ...(['critical', 'high', 'medium'] as Severity[])
                  .map((s) => ({ id: s, label: s, count: alerts.filter((a) => a.severity === s).length }))
                  .filter((o) => o.count > 0),
              ]}
              active={filter}
              onChange={setFilter}
            />
          </div>

          <div className="space-y-2" data-tour="reminders-list">
            {visible.map((alert) => {
              const Icon = alert.icon;
              return (
                <div
                  key={alert.id}
                  className={`glass-card p-4 flex items-start gap-3 ${
                    alert.severity === 'critical' ? 'border-danger-line' : ''
                  }`}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${SEVERITY_TILE[alert.severity]}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-ink-900">{alert.title}</p>
                    <p className="text-xs text-ink-600 mt-0.5">{alert.detail}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`badge ${SEVERITY_BADGE[alert.severity]}`}>{alert.severity}</span>
                    {alert.route && (
                      <button
                        type="button"
                        onClick={() => navigate(alert.route!)}
                        className="btn-secondary btn-sm"
                      >
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};
