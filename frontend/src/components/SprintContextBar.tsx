import React from 'react';
import { Link } from 'react-router-dom';
import { Layers } from 'lucide-react';

import { useSelectedSprint } from '../context/SelectedSprintContext';
import type { Sprint } from '../types';

const sprintLabel = (s: Sprint) =>
  `${s.institution_name || s.name || 'Institution'} · ${s.sprint_code} (${s.status.replace(/_/g, ' ')})`;

/**
 * The selected sprint, at the top of the dashboard and every sprint page: its code, name and institution,
 * and the one place to switch it (context/SelectedSprintContext.tsx). With nothing selected it says so --
 * it never implies a sprint is active.
 */
export const SprintContextBar: React.FC = () => {
  const { sprint, sprints, status, sprintId, loadError, selectSprint, refreshSprints } = useSelectedSprint();
  const options = sprints || [];

  const picker = options.length > 0 && (
    <label className="flex items-center gap-2 text-xs font-semibold text-ink-700 shrink-0">
      <span>{status === 'ok' ? 'Switch sprint' : 'Choose a sprint'}</span>
      <select
        className="input py-1.5 text-xs max-w-[22rem]"
        aria-label="Selected sprint"
        value={status === 'ok' ? sprintId : ''}
        onChange={(e) => { if (e.target.value) selectSprint(e.target.value); }}
      >
        {status !== 'ok' && <option value="">Choose a sprint…</option>}
        {options.map((s) => <option key={s.id} value={s.id}>{sprintLabel(s)}</option>)}
      </select>
    </label>
  );

  let body: React.ReactNode;
  if (loadError && sprints === null) {
    body = (
      <p className="text-sm text-danger">
        Could not load your sprints.{' '}
        <button type="button" className="font-semibold underline" onClick={refreshSprints}>Retry</button>
      </p>
    );
  } else if (status === 'loading' || sprints === null) {
    body = <p className="text-sm text-ink-500">Loading sprints…</p>;
  } else if (status === 'ok' && sprint) {
    body = (
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wide text-ink-500">Selected sprint</p>
        <p className="text-sm font-bold text-ink-900 truncate">
          <span className="font-mono text-brand-800">{sprint.sprint_code}</span>
          {sprint.name && sprint.name !== sprint.institution_name ? ` · ${sprint.name}` : ''}
        </p>
        <p className="text-xs text-ink-600 truncate">
          {sprint.institution_name || 'Institution not recorded'}
          {sprint.academic_year ? ` · ${sprint.academic_year}` : ''} · {sprint.status.replace(/_/g, ' ')}
        </p>
      </div>
    );
  } else if (status === 'not_found') {
    body = (
      <p className="text-sm text-warning">
        This sprint is not one of yours, or it no longer exists. Choose another sprint.
      </p>
    );
  } else if (options.length === 0) {
    body = <p className="text-sm text-ink-600">No sprints yet. <Link to="/dashboard" className="font-semibold text-brand-800 hover:underline">Go to the dashboard</Link> to start one.</p>;
  } else {
    body = <p className="text-sm font-semibold text-ink-700">No sprint selected. Choose one to see its data.</p>;
  }

  return (
    <div
      className={`glass-card px-4 py-3 mb-5 flex flex-col sm:flex-row sm:items-center gap-3 justify-between border-l-4 ${
        status === 'ok' ? 'border-l-brand-500' : 'border-l-warning'}`}
      role="region"
      aria-label="Selected sprint"
    >
      <div className="flex items-center gap-3 min-w-0">
        <Layers className="w-5 h-5 text-brand-800 shrink-0" aria-hidden="true" />
        {body}
      </div>
      {picker}
    </div>
  );
};

/** For a page that needs a sprint when none is selected: the header above has the picker. */
export const SelectSprintPrompt: React.FC = () => (
  <div className="panel-muted text-center py-10">
    <p className="text-sm font-semibold text-ink-800">Choose a sprint to see this page.</p>
    <p className="text-xs text-ink-500 mt-1">Use the sprint picker at the top of the page. Your choice stays selected until you change it.</p>
  </div>
);
