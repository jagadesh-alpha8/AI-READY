import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listRecommendations, generateRecommendations, updateRecommendation } from '../../api/recommendations';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Recommendation } from '../../types';
import { Sparkles, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useAccess } from '../../utils/access';

/** How each status reads on a card; "accepted" is unmistakable (it goes into the report). */
const STATUS_CHIP: Record<Recommendation['status'], { label: string; cls: string }> = {
  draft: { label: 'Not reviewed', cls: 'badge-neutral' },
  edited: { label: 'Edited - not accepted yet', cls: 'badge-warning' },
  accepted: { label: 'Accepted for report', cls: 'badge-success' },
  completed: { label: 'Completed', cls: 'badge-success' },
  hidden: { label: 'Hidden from report', cls: 'badge-neutral' },
};
const isIn = (r: Recommendation) => r.status === 'accepted' || r.status === 'completed';
/** Undo / unhide goes back to what it was before: edited if its text was changed, otherwise not reviewed. */
const reopened = (r: Recommendation): Recommendation['status'] => (r.edited_text ? 'edited' : 'draft');

export const RecommendationsReview: React.FC = () => {
  const { can, step } = useAccess();
  const { sprintId } = useParams<{ sprintId: string }>();
  const navigate = useNavigate();
  const isRealSprint = !!sprintId && sprintId !== 'demo-sprint-id';

  const {
    data: recsData,
    setData: setRecs,
    loading,
    error,
    refetch,
  } = useApiResource<Recommendation[]>(() => listRecommendations(sprintId!), [sprintId], isRealSprint);
  const recs = recsData || [];

  const [generating, setGenerating] = useState(false);
  const [actionError, setActionError] = useState('');
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const handleGenerate = async () => {
    if (!isRealSprint) {
      setActionError('No active sprint is selected. Set up a sprint first.');
      return;
    }
    setGenerating(true);
    setActionError('');
    try {
      const res = await generateRecommendations(sprintId!);
      setRecs(res.data);
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to generate recommendations.'));
    } finally {
      setGenerating(false);
    }
  };

  const handleStatusUpdate = async (recId: string, status: Recommendation['status']) => {
    setUpdatingId(recId);
    setActionError('');
    try {
      const { data: saved } = await updateRecommendation(recId, { status });
      // Show the new status at once, then move on to the next card still to accept.
      const next = recs.map((r) => (r.id === recId ? { ...r, ...saved, status } : r));
      setRecs(next);
      if (status === 'accepted') {
        const after = next.slice(next.findIndex((r) => r.id === recId) + 1)
          .find((r) => !isIn(r) && r.status !== 'hidden');
        if (after) setTimeout(() => document.getElementById(`rec-${after.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
      }
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to update recommendation status.'));
    } finally {
      setUpdatingId(null);
    }
  };

  const handleEditSubmit = async (recId: string) => {
    setUpdatingId(recId);
    setActionError('');
    try {
      await updateRecommendation(recId, { description: editValue });
      setEditingId(null);
      setEditValue('');
      refetch();
    } catch (err) {
      setActionError(getErrorMessage(err, 'Failed to edit recommendation.'));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-5 sm:p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-ink-900 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-brand-800" /> Step {step('sprint-recommendations')}: Contextual Improvement Recommendations
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Data-cited, department-specific recommendations matched from the InGage intervention library based on gaps and scores.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {can('recommendations.generate') && (
              <button onClick={handleGenerate} disabled={generating} className="btn-secondary">
                <Sparkles className="w-3.5 h-3.5" />
                <span>{generating ? 'Generating...' : 'Generate Recommendations'}</span>
              </button>
            )}
            <button onClick={() => navigate(`/sprint/${sprintId}/report`)} className="btn-primary shrink-0">
              <span>Proceed to Executive Report</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {actionError && <InlineError message={actionError} onDismiss={() => setActionError('')} />}

      {/* Recommendations Cards List */}
      <div className="space-y-4">
        {loading ? (
          <LoadingState message="Loading recommendations..." />
        ) : error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : recs.length === 0 ? (
          <div className="glass-card p-8 text-center space-y-3">
            {can('recommendations.generate') ? (
              <>
                <p className="text-sm text-ink-500">No recommendations generated yet. Click 'Generate Recommendations'.</p>
                <button onClick={handleGenerate} disabled={generating} className="btn-primary btn-sm">
                  {generating ? 'Generating...' : 'Generate Recommendations Now'}
                </button>
              </>
            ) : (
              <p className="text-sm text-ink-500">No recommendations yet. They appear here once InGage or your institution generates them.</p>
            )}
          </div>
        ) : (
          <>
          <p className="text-sm text-ink-700" role="status">
            <strong className="tabular-nums">{recs.filter(isIn).length}</strong> of {recs.filter((r) => r.status !== 'hidden').length} accepted for the report
          </p>
          {recs.map((rec) => (
            <div key={rec.id} id={`rec-${rec.id}`}
              className={`glass-card-hover p-5 sm:p-6 space-y-4 scroll-mt-24 ${isIn(rec) ? 'border-2 border-success-line'
                : rec.status === 'hidden' ? 'opacity-60' : ''}`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-line-100 pb-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="badge-brand">{rec.pillar?.replace('_', ' ')}</span>
                  <span className="text-xs font-semibold text-ink-500">Owner: {rec.owner_role}</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono font-bold text-success bg-success-bg px-2 py-0.5 rounded border border-success-line tabular-nums">
                    +{rec.expected_score_lift} CRI Lift
                  </span>
                  <span className="text-xs text-ink-500">Timeline: {rec.timeline}</span>
                </div>
              </div>

              <div>
                <p className="text-xs font-bold text-warning uppercase tracking-wide font-mono">Trigger Data &amp; Gap:</p>
                <p className="text-sm text-ink-600 italic mt-0.5">&ldquo;{rec.trigger_gap}&rdquo;</p>
              </div>

              <div>
                <p className="text-xs font-bold text-ink-900 uppercase tracking-wide">Recommended Improvement Action:</p>
                {editingId === rec.id ? (
                  <div className="mt-1 space-y-2">
                    <textarea
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      rows={3}
                      className="input font-medium"
                    />
                    <div className="flex items-center gap-2">
                      <button onClick={() => handleEditSubmit(rec.id)} disabled={updatingId === rec.id} className="btn-primary btn-sm">
                        {updatingId === rec.id ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        onClick={() => { setEditingId(null); setEditValue(''); }}
                        className="btn-secondary btn-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-ink-900 leading-relaxed mt-1 font-medium bg-surface p-3 rounded-lg border border-line-200">
                    {rec.edited_text || rec.recommendation_text}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between pt-2 flex-wrap gap-2">
                <span className={`badge ${STATUS_CHIP[rec.status]?.cls || 'badge-neutral'} inline-flex items-center gap-1`}>
                  {isIn(rec) && <CheckCircle2 className="w-3.5 h-3.5" />}
                  {STATUS_CHIP[rec.status]?.label || rec.status}
                </span>
                {can('recommendations.edit') && <div className="flex items-center gap-2 flex-wrap">
                  {isIn(rec) ? (
                    <button onClick={() => handleStatusUpdate(rec.id, reopened(rec))} disabled={updatingId === rec.id}
                      className="btn-secondary btn-sm" title="Take it out of the report again">
                      {updatingId === rec.id ? 'Saving…' : 'Undo accept'}
                    </button>
                  ) : rec.status !== 'hidden' && (
                    <button onClick={() => handleStatusUpdate(rec.id, 'accepted')} disabled={updatingId === rec.id}
                      className="btn-primary btn-sm">
                      {updatingId === rec.id ? 'Accepting…' : 'Accept for Report'}
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setEditingId(rec.id);
                      setEditValue(rec.edited_text || rec.recommendation_text);
                    }}
                    disabled={updatingId === rec.id}
                    className="btn-secondary btn-sm"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleStatusUpdate(rec.id, rec.status === 'hidden' ? reopened(rec) : 'hidden')}
                    disabled={updatingId === rec.id}
                    className="btn-secondary btn-sm"
                  >
                    {rec.status === 'hidden' ? 'Unhide' : 'Hide'}
                  </button>
                </div>}
              </div>
            </div>
          ))}
          </>
        )}
      </div>
    </div>
  );
};
