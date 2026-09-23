import React from 'react';
import { FlaskConical } from 'lucide-react';

/**
 * The banner every ported module carries.
 *
 * These screens render illustrative data held in the browser — no API call,
 * no database, nothing persisted. That has to be unmissable. This platform's
 * whole posture is that a number on screen is traceable to a document a human
 * can open; a screen full of convincing figures that came from a seed file
 * would quietly break that promise, and a screenshot of one could easily be
 * mistaken for a real institution's record.
 *
 * Deliberately placed first on every page, so it cannot be cropped out of a
 * screenshot of the top of the screen.
 */
export const DemoDataNotice: React.FC<{
  /** What, specifically, is not real here. One sentence. */
  detail?: string;
}> = ({ detail }) => (
  <div className="rounded-lg border border-info-line bg-info-bg p-3.5 flex items-start gap-3">
    <FlaskConical className="w-4 h-4 text-info shrink-0 mt-0.5" />
    <p className="text-sm text-ink-600 min-w-0">
      <strong className="text-info">Demo data. </strong>
      This screen is the UI from the InGage prototype, rendered with its sample content.
      Nothing here is saved, fetched, or connected to a real institution — reloading resets it.
      {detail ? ` ${detail}` : ''}
    </p>
  </div>
);
