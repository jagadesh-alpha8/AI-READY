import React from 'react';
import { Link } from 'react-router-dom';
import { Info } from 'lucide-react';

import { useAccess } from '../../utils/access';

/**
 * The sprint CRI and a Benchmark Assessment are two different scorecards. This note says so on both
 * pages, with a link to the other one. Neither score changes the other (the backend keeps them apart).
 */
export const ScorecardsNote: React.FC<{ here: 'cri' | 'assessment'; sprintId?: string }> = ({ here, sprintId }) => {
  const { canSee } = useAccess();
  return (
    <div className="rounded-lg border border-info-line bg-info-bg p-3 text-xs text-ink-700 flex items-start gap-2">
      <Info className="w-4 h-4 text-info shrink-0 mt-0.5" />
      <div className="space-y-1">
        {here === 'cri' ? (
          <p>
            <strong>This is the sprint CRI</strong>: one weighted score across the 9 AI-QIF criteria, calculated from
            this sprint's confirmed facts and open gaps, with its own baseline approval, report and Transformation
            Plan. A <strong>Benchmark Assessment</strong> is a separate scorecard: a college's evidence checked
            benchmark by benchmark against a published benchmark release, with four scores per benchmark and its own
            improvement plan. Neither one changes the other.
          </p>
        ) : (
          <p>
            <strong>This is a Benchmark Assessment</strong>: a college's evidence checked benchmark by benchmark
            against one published benchmark release (shown on each assessment), with four scores per benchmark and an
            improvement plan once it is finalized. It is separate from the <strong>sprint CRI</strong>, the weighted
            AI-QIF score calculated from a discovery sprint's facts and gaps. Neither one changes the other.
          </p>
        )}
        <p>
          {here === 'cri' ? (
            canSee('benchmark-assessment') && (
              <>When a benchmark release has been published, assess the college against it in{' '}
                <Link className="font-semibold text-brand-800 hover:underline" to="/benchmark-assessment">Benchmark Assessment</Link>.</>
            )
          ) : (
            sprintId && canSee('sprint-score') && (
              <>The sprint CRI is on{' '}
                <Link className="font-semibold text-brand-800 hover:underline" to={`/sprint/${sprintId}/score`}>Live CRI</Link>.</>
            )
          )}
        </p>
      </div>
    </div>
  );
};
