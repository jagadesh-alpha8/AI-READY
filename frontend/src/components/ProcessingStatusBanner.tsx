import React from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';

import { getProcessingSummary } from '../api/extraction';
import { useApiResource } from '../hooks/useApiResource';
import type { ProcessingSummary } from '../types';
import { isRealSprintId } from '../utils/selectedSprint';

/**
 * Says plainly when a sprint's included documents are not all fully processed (failed, still processing,
 * not processed, or partially extracted), so nobody reads facts, the CRI, the baseline or a report as
 * complete when it is not (backend apps/extraction/services/completeness.py). Renders nothing when complete.
 */
export const ProcessingStatusBanner: React.FC<{
  sprintId: string;
  /** What the incomplete processing means on this page, e.g. "This CRI may miss facts from them." */
  consequence?: string;
  /** Pass the summary when the page already has it (e.g. the baseline response). */
  summary?: ProcessingSummary | null;
}> = ({ sprintId, consequence, summary }) => {
  const { data } = useApiResource<ProcessingSummary>(
    () => getProcessingSummary(sprintId), [sprintId], !summary && isRealSprintId(sprintId),
  );
  const s = summary || data;
  if (!s || s.complete) return null;
  return (
    <div className="rounded-lg border border-warning-line bg-warning-bg p-3 text-sm text-ink-700 flex items-start gap-2">
      <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
      <div className="space-y-1 min-w-0">
        <p>
          <strong className="text-warning">Document processing is incomplete. </strong>
          {s.description} {consequence}
        </p>
        <ul className="text-xs text-ink-600 list-disc pl-4">
          {s.incomplete.slice(0, 6).map((d) => (
            <li key={d.document_id}>{d.filename}: {d.label}</li>
          ))}
          {s.incomplete.length > 6 && <li>and {s.incomplete.length - 6} more</li>}
        </ul>
        <Link to={`/sprint/${sprintId}/monitor`} className="text-xs font-semibold text-brand-800 hover:underline">
          Open the AI Processing Monitor to retry them
        </Link>
      </div>
    </div>
  );
};
