import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { listRecommendations, generateRecommendations, updateRecommendation } from '../../api/recommendations';
import { useApiResource } from '../../hooks/useApiResource';
import { getErrorMessage } from '../../utils/errors';
import { ErrorState, InlineError, LoadingState } from '../../components/ApiStates';
import type { Recommendation } from '../../types';
import { Sparkles, ArrowRight } from 'lucide-react';

export const RecommendationsReview: React.FC = () => {
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

  const handleStatusUpdate = async (recId: string, status: string) => {
    setUpdatingId(recId);
    setActionError('');
    try {
      await updateRecommendation(recId, { status: status as Recommendation['status'] });
      refetch();
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
              <Sparkles className="w-5 h-5 text-brand-800" /> Screen 9: Contextual Improvement Recommendations
            </h1>
            <p className="text-sm text-ink-500 mt-1">
              Data-cited, department-specific recommendations matched from the InGage intervention library based on gaps and scores.
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={handleGenerate} disabled={generating} className="btn-secondary">
              <Sparkles className="w-3.5 h-3.5" />
              <span>{generating ? 'Generating...' : 'Generate Recommendations'}</span>
            </button>
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
            <p className="text-sm text-ink-500">No recommendations generated yet. Click 'Generate Recommendations'.</p>
            <button onClick={handleGenerate} disabled={generating} className="btn-primary btn-sm">
              {generating ? 'Generating...' : 'Generate Recommendations Now'}
            </button>
          </div>
        ) : (
          recs.map((rec) => (
            <div key={rec.id} className="glass-card-hover p-5 sm:p-6 space-y-4">
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
                        className="px-3 py-1 bg-line-200 hover:bg-line-300 text-ink-600 font-semibold text-xs rounded transition-colors"
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
                <span className="text-xs text-ink-500">Status: <strong className="text-brand-800 uppercase">{rec.status}</strong></span>
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => handleStatusUpdate(rec.id, 'accepted')}
                    disabled={updatingId === rec.id}
                    className="px-3 py-1 bg-success-solid hover:brightness-95 text-white font-semibold text-xs rounded transition-all disabled:opacity-60"
                  >
                    Accept for Report
                  </button>
                  <button
                    onClick={() => {
                      setEditingId(rec.id);
                      setEditValue(rec.edited_text || rec.recommendation_text);
                    }}
                    disabled={updatingId === rec.id}
                    className="px-3 py-1 bg-line-200 hover:bg-line-300 text-brand-800 font-semibold text-xs rounded transition-colors disabled:opacity-60"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleStatusUpdate(rec.id, 'hidden')}
                    disabled={updatingId === rec.id}
                    className="px-3 py-1 bg-line-200 hover:bg-line-300 text-ink-500 font-semibold text-xs rounded transition-colors disabled:opacity-60"
                  >
                    Hide
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
