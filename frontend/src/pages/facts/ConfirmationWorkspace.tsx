import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { listSprintFacts, confirmFact } from '../../api/facts';
import { listSprintGaps, resolveGap } from '../../api/gaps';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Fact, Gap } from '../../types';
import { CheckSquare, ArrowRight } from 'lucide-react';

export const ConfirmationWorkspace: React.FC = () => {
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: factsData,
    loading: factsLoading,
    error: factsError,
    refetch: refetchFacts,
  } = useApiResource<Fact[]>(() => listSprintFacts(sprintId!), [sprintId], isRealSprint);
  const {
    data: gapsData,
    loading: gapsLoading,
    error: gapsError,
    refetch: refetchGaps,
  } = useApiResource<Gap[]>(() => listSprintGaps(sprintId!), [sprintId], isRealSprint);

  const [actionError, setActionError] = useState('');
  const [actingOnId, setActingOnId] = useState<string | null>(null);

  const loading = factsLoading || gapsLoading;
  const error = factsError || gapsError;

  const facts = factsData || [];
  const gaps = gapsData || [];

  const ownedPendingFacts = facts.filter(
    (f) => f.status === 'extracted' && (!user?.role || f.owner_role.toLowerCase() === user.role.toLowerCase()),
  );
  const ownedConflicts = gaps.filter(
    (g) =>
      g.gap_type === 'conflict' &&
      (g.status === 'open' || g.status === 'in_progress') &&
      (!user?.role || g.owner_role.toLowerCase() === user.role.toLowerCase()),
  );
  const readyForBaseline = ownedPendingFacts.length === 0 && ownedConflicts.length === 0;

  const handleConfirmFact = async (factId: string) => {
    setActingOnId(factId);
    setActionError('');
    try {
      await confirmFact(factId);
      refetchFacts();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to confirm fact.'));
    } finally {
      setActingOnId(null);
    }
  };

  const handleResolveConflict = async (gapId: string, value: string) => {
    setActingOnId(gapId);
    setActionError('');
    try {
      await resolveGap(gapId, value);
      refetchGaps();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to resolve conflict.'));
    } finally {
      setActingOnId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="badge-accent">Active Persona: {user?.role}</span>
              <span className="text-sm text-ink-500">({user?.name})</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 mt-1 flex items-center gap-2">
              <CheckSquare className="w-5 h-5 text-brand-800" /> Screen 6: Owner Confirmation Workspace
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Role-filtered workspace showing pending confirmations, evidence reviews, and unresolved items assigned to {user?.role}.
            </p>
          </div>
          <button onClick={() => navigate(`/sprint/${sprintId}/score`)} className="btn-primary shrink-0">
            <span>Proceed to Live CRI Preview</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {loading ? (
        <LoadingState message="Loading confirmation workspace..." />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            refetchFacts();
            refetchGaps();
          }}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass-card p-5">
              <p className="text-sm font-semibold text-ink-500">Pending Facts to Confirm</p>
              <p className="text-2xl font-bold text-ink-900 mt-1 tabular-nums">{ownedPendingFacts.length} Items</p>
              <span className="text-xs text-brand-800 font-medium">High-confidence AI extractions</span>
            </div>
            <div className="glass-card p-5">
              <p className="text-sm font-semibold text-ink-500">Conflicts Assigned to You</p>
              <p className="text-2xl font-bold text-ink-900 mt-1 tabular-nums">{ownedConflicts.length} Items</p>
              <span className="text-xs text-warning font-medium">Requires manual resolution</span>
            </div>
            <div className="glass-card p-5">
              <p className="text-sm font-semibold text-ink-500">Confirmation Approval Status</p>
              <p className={`text-2xl font-bold mt-1 ${readyForBaseline ? 'text-success' : 'text-warning'}`}>
                {readyForBaseline ? 'Ready for Baseline' : 'Pending Review'}
              </p>
              <span className="text-xs text-ink-500 font-medium">Owner signoff {readyForBaseline ? 'active' : 'required'}</span>
            </div>
          </div>

          {/* Confirmation Actions List */}
          <div className="glass-card p-5 sm:p-6 space-y-4">
            <h2 className="eyebrow">Assigned Confirmation Tasks for {user?.role}</h2>
            {ownedPendingFacts.length === 0 && ownedConflicts.length === 0 ? (
              <div className="panel-muted">
                <p className="text-sm text-ink-500">No confirmation tasks assigned to {user?.role} right now.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {ownedPendingFacts.map((fact) => (
                  <div
                    key={fact.id}
                    className="p-4 bg-surface rounded-xl border border-line-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <span className="text-[11px] font-bold text-brand-800 uppercase font-mono tracking-wide">{fact.pillar_label || fact.pillar}</span>
                      <p className="text-sm font-bold text-ink-900 mt-0.5">
                        {fact.field_name}: {String(fact.value)}
                      </p>
                      <p className="text-xs text-ink-500 mt-1">
                        Source: {fact.source_snippet || 'N/A'} | Extraction Confidence: {(fact.confidence_score * 100).toFixed(0)}%
                      </p>
                    </div>
                    <button
                      onClick={() => handleConfirmFact(fact.id)}
                      disabled={actingOnId === fact.id}
                      className="px-3.5 py-1.5 bg-success-solid text-white font-semibold text-sm rounded-lg shadow-card transition-all disabled:opacity-60 hover:brightness-95 shrink-0"
                    >
                      {actingOnId === fact.id ? 'Confirming...' : 'Confirm Record'}
                    </button>
                  </div>
                ))}

                {ownedConflicts.map((gap) => (
                  <div
                    key={gap.id}
                    className="p-4 bg-surface rounded-xl border border-line-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <span className="text-[11px] font-bold text-warning uppercase font-mono tracking-wide">Conflict Resolution</span>
                      <p className="text-sm font-bold text-ink-900 mt-0.5">{gap.title}</p>
                      <p className="text-xs text-ink-500 mt-1">{gap.description || 'Action needed: resolve this conflict.'}</p>
                    </div>
                    <button
                      onClick={() => handleResolveConflict(gap.id, 'Resolved by owner confirmation')}
                      disabled={actingOnId === gap.id}
                      className="btn-primary btn-sm shadow-card shrink-0"
                    >
                      {actingOnId === gap.id ? 'Resolving...' : 'Resolve Conflict'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
