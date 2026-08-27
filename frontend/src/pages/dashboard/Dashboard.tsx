import React from 'react';
import { useNavigate } from 'react-router-dom';
import { listSprints, deleteSprint, archiveSprint } from '../../api/sprints';
import { getDashboard } from '../../api/dashboard';
import { useApiResource } from '../../hooks/useApiResource';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import type { DashboardData, Sprint } from '../../types';
import { Building, Plus, Play, CheckCircle2, ArrowRight, ShieldCheck, Trash2, Archive } from 'lucide-react';

/** Average of the non-null values in `values`, or null if none are scored
 * yet -- never a fabricated number standing in for "not measured". */
function average(values: (number | null)[]): number | null {
  const known = values.filter((v): v is number => v !== null && v !== undefined);
  if (known.length === 0) return null;
  return known.reduce((sum, v) => sum + v, 0) / known.length;
}

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  const {
    data: sprintsList,
    loading: sprintsLoading,
    error: sprintsError,
    refetch: refetchSprints,
  } = useApiResource<Sprint[]>(() => listSprints(), []);

  const handleDeleteSprint = async (sprint: Sprint) => {
    if (!window.confirm(`Are you sure you want to delete sprint "${sprint.name || sprint.sprint_code}"? This will permanently remove all data associated with it.`)) {
      return;
    }

    try {
      await deleteSprint(sprint.id);
      refetchSprints();
      refetchDashboard();
    } catch (err) {
      console.error('Failed to delete sprint:', err);
      alert('Failed to delete sprint. Only drafts, completed, and archived sprints can be deleted.');
    }
  };

  const handleArchiveSprint = async (sprint: Sprint) => {
    if (!window.confirm(`Archive sprint "${sprint.name || sprint.sprint_code}"? Archiving is required before it can be deleted, but doesn't remove any data by itself.`)) {
      return;
    }

    try {
      await archiveSprint(sprint.id);
      refetchSprints();
      refetchDashboard();
    } catch (err) {
      console.error('Failed to archive sprint:', err);
      alert('Failed to archive sprint. Please try again.');
    }
  };

  const {
    data: dashboard,
    loading: dashboardLoading,
    error: dashboardError,
    refetch: refetchDashboard,
  } = useApiResource<DashboardData>(() => getDashboard(), []);

  const loading = sprintsLoading || dashboardLoading;
  const error = dashboardError || sprintsError;
  const sprints = sprintsList || [];
  const dashboardSprints = Array.isArray(dashboard?.sprints)
    ? dashboard!.sprints
    : dashboard?.sprints?.results || [];

  const avgCri = average(dashboardSprints.map((s) => s.cri));
  const avgConfidence = average(dashboardSprints.map((s) => s.confidence));

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-card p-6 sm:p-8 bg-gradient-to-br from-brand-50 to-card">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-bold uppercase tracking-wide text-brand-800">AIOS Platform</span>
            <h1 className="text-2xl sm:text-3xl font-bold text-ink-900 tracking-tight mt-1 text-balance">AI Readiness Discovery Sprints</h1>
            <p className="text-sm text-ink-600 mt-1.5 max-w-2xl">
              Execute 24-48 hour fast-track AI readiness audits across governance, curriculum, faculty capability, student readiness, labs, research, and placements.
            </p>
          </div>
          <button onClick={() => navigate('/sprint/setup')} className="btn-primary shrink-0">
            <Plus className="w-4 h-4" />
            <span>Create New Discovery Sprint</span>
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Active Sprints</span>
            <Play className="w-4 h-4 text-brand-800" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{dashboard ? dashboard.active_sprints : '—'}</p>
          <span className="text-xs text-brand-800 mt-1 inline-block font-medium">24-48h Discovery Mode</span>
        </div>

        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Institutions Onboarded</span>
            <Building className="w-4 h-4 text-info" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">{dashboard ? dashboard.institution_count : '—'}</p>
          <span className="text-xs text-info mt-1 inline-block font-medium">Autonomous & Affiliated</span>
        </div>

        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Average CRI Score</span>
            <ShieldCheck className="w-4 h-4 text-success" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">
            {avgCri !== null ? avgCri.toFixed(1) : 'N/A'} <span className="text-sm text-ink-500 font-normal">/ 100</span>
          </p>
          <span className="text-xs text-success mt-1 inline-block font-medium">
            {avgCri !== null ? 'Across scored sprints' : 'No sprints scored yet'}
          </span>
        </div>

        <div className="glass-card p-5">
          <div className="flex items-center justify-between text-ink-500">
            <span className="text-sm font-medium">Data Confidence</span>
            <CheckCircle2 className="w-4 h-4 text-warning" />
          </div>
          <p className="text-2xl font-bold text-ink-900 mt-2 tabular-nums">
            {avgConfidence !== null ? `${(avgConfidence * 100).toFixed(0)}%` : 'N/A'}
          </p>
          <span className="text-xs text-warning mt-1 inline-block font-medium">
            {avgConfidence !== null ? 'Verified Evidence' : 'No sprints scored yet'}
          </span>
        </div>
      </div>

      {/* Sprints List Table */}
      <div className="glass-card p-5 sm:p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="eyebrow">Discovery Sprints</h2>
          <span className="text-xs text-ink-500">{sprints.length} sprint records</span>
        </div>

        {loading ? (
          <LoadingState message="Loading discovery sprints..." />
        ) : error ? (
          <ErrorState
            message={error}
            onRetry={() => {
              refetchSprints();
              refetchDashboard();
            }}
          />
        ) : sprints.length === 0 ? (
          <div className="panel-muted">
            <p className="text-sm text-ink-500">No active discovery sprints found.</p>
            <button onClick={() => navigate('/sprint/setup')} className="btn-primary btn-sm mt-3">
              Start First Sprint
            </button>
          </div>
        ) : (
          <div className="table-shell">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Sprint ID</th>
                  <th>Sprint Mode</th>
                  <th>Academic Year</th>
                  <th>Status</th>
                  <th>Created Date</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {sprints.map((sprint) => (
                  <tr key={sprint.id}>
                    <td className="font-mono font-medium text-brand-800">
                      {sprint.id.substring(0, 8)}...
                    </td>
                    <td className="text-ink-900 capitalize font-medium">
                      {(sprint.sprint_mode || sprint.mode || '').replace('_', ' ')}
                    </td>
                    <td className="text-ink-600">{sprint.academic_year || '—'}</td>
                    <td>
                      <span className="badge-brand">{sprint.status}</span>
                    </td>
                    <td className="text-ink-500">
                      {new Date(sprint.created_at).toLocaleDateString()}
                    </td>
                    <td className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {['draft', 'completed', 'archived'].includes(sprint.status) ? (
                          <button
                            onClick={() => handleDeleteSprint(sprint)}
                            className="btn-icon hover:text-danger hover:bg-danger-bg"
                            title="Delete Sprint"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleArchiveSprint(sprint)}
                            className="btn-icon hover:text-warning hover:bg-warning-bg"
                            title="Archive Sprint (required before deleting)"
                          >
                            <Archive className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => navigate(`/sprint/${sprint.id}/upload`)}
                          className="btn-secondary btn-sm ml-1"
                        >
                          <span>Open</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
