import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ClipboardList } from 'lucide-react';

import { listCycles } from '../../api/assessments';
import type { Cycle } from '../../api/assessments';
import { ErrorState, LoadingState } from '../../components/ApiStates';
import { useAuth } from '../../context/AuthContext';
import { useApiResource } from '../../hooks/useApiResource';
import { useAccess } from '../../utils/access';
import { ScorecardView } from '../assessments/BenchmarkAssessments';

const STAFF = ['super_admin', 'consultant'];

/**
 * The college's Benchmark Assessment, apart from the sprint CRI: an assessment cycle belongs to the college
 * (not to a sprint) and is scored against one published benchmark release. Its scores are the ones the
 * Benchmark Assessment page shows (Compliance, Maturity, Evidence confidence, Outcome per benchmark, and a
 * Composite only with approved weights) -- this section reuses that scorecard rather than restating it.
 */
export const BenchmarkAssessmentSection: React.FC<{ institutionId: string | null; institutionName: string }> = (
  { institutionId, institutionName },
) => {
  const { user } = useAuth();
  const { canSee } = useAccess();
  const cycles = useApiResource<Cycle[]>(() => listCycles(institutionId!), [institutionId], !!institutionId);
  const [picked, setPicked] = useState('');
  const staff = !!user && STAFF.includes(user.role);
  const list = cycles.data || [];
  const cycle = list.find((c) => c.id === picked) || list[0] || null;
  const link = canSee('benchmark-assessment') && (
    <Link to="/benchmark-assessment" className="font-semibold text-brand-800 hover:underline">Benchmark Assessment</Link>
  );

  return (
    <section className="glass-card p-5 sm:p-6 space-y-3" aria-labelledby="benchmark-assessment-heading">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="benchmark-assessment-heading" className="text-base font-bold text-ink-900 flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-brand-800" /> Benchmark Assessment (separate from the sprint CRI)
          </h2>
          <p className="text-xs text-ink-500 mt-0.5">
            {institutionName || 'This college'}'s evidence checked benchmark by benchmark against a published benchmark
            release. It belongs to the college, not to this sprint, and neither score changes the other.
          </p>
        </div>
        {list.length > 1 && (
          <select className="input text-xs w-auto" value={cycle?.id || ''} onChange={(e) => setPicked(e.target.value)}
            aria-label="Assessment cycle">
            {list.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.release_label} · {c.status_label}</option>)}
          </select>
        )}
      </div>

      {!institutionId ? <p className="text-xs text-ink-500">Choose a sprint to see its college's assessments.</p>
        : cycles.loading ? <LoadingState message="Loading assessments…" />
          : cycles.error ? <ErrorState message={cycles.error} onRetry={cycles.refetch} />
            : !cycle ? (
              <div className="panel-muted text-sm text-ink-600">
                No Benchmark Assessment has been started for this college yet, so there are no assessment scores.{' '}
                {staff ? <>Start one in {link || 'Benchmark Assessment'} (it needs a published benchmark release).</>
                  : <>InGage starts assessments{link ? <>; they appear in {link}</> : ''}.</>}
              </div>
            ) : (
              <div className="space-y-2 text-xs">
                <p className="text-ink-700">
                  <strong>{cycle.name}</strong> · {cycle.status_label} · release <strong className="font-mono">{cycle.release_label}</strong>
                  {' '}· opens {cycle.opens_on}{cycle.closes_on ? ` · closes ${cycle.closes_on}` : ''}
                </p>
                {cycle.status === 'finalized' || staff ? (
                  <ScorecardView cycleId={cycle.id} />
                ) : (
                  <p className="panel-muted text-ink-600">
                    The scorecard is shared once InGage finalizes this assessment (it is {cycle.status_label.toLowerCase()} now).
                  </p>
                )}
                {link && <p className="text-ink-500">Evidence, scoring and the improvement plan are in {link}.</p>}
              </div>
            )}
    </section>
  );
};
