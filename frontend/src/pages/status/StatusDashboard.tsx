import React from 'react';
import { Link } from 'react-router-dom';

const workflow = [
  ['Sprint setup', 'Choose the institution and create a workspace.'],
  ['Upload & Processing', 'Upload files or import from Drive; inspect processing failures and the document inventory. OCR support exists in code; successful extraction must be checked for each import.'],
  ['Evidence & Review', 'Review exceptions, conflicts, missing records and accreditation evidence in one workspace. Reviewed decisions are not yet integrated into capability snapshots.'],
  ['Assessment', 'Explicitly start an experimental capability assessment. The default overview preserves source-specific scope; optional refinement creates a new version.'],
  ['Recommendations & Action Plan', 'Inspect evidence gaps, documented shortfalls and explicitly requested advice. Optional institutional plan evaluation compares conditional scenarios without changing actual standing.'],
  ['Reports', 'Export the saved leadership report or full supporting evidence. Exporting causes no model calls and requires no consultant sign-off.'],
];
const remaining = [
  ['Reviewed evidence integration', 'Freeze accepted facts, conflict resolutions and declarations with their source history.'],
  ['Small review-question queue', 'Group material questions and persist an initial limit of 25, with deferred issues retained.'],
  ['Institution-specific initiatives', 'Link related actions, documented assets, dependencies and practical benefits across assessment areas.'],
  ['One-action assessment workflow', 'Coordinate review, assessment and advice generation with explicit limits and failure states.'],
  ['Methodology validation', 'Evaluate the proposed rubric, aggregation and tier rules on reviewed examples before activating a new method.'],
  ['Deployment and institutional baseline', 'Confirm deployed API/worker versions, migrations, configured limits and a reconciled full-folder import. Reassess that same corpus before claiming an institutional result.'],
];
export const StatusDashboard: React.FC = () => <div className="space-y-6 max-w-5xl mx-auto">
  <Link className="btn-secondary" to="/dashboard">Back to the platform</Link>
  <header className="glass-card p-6 space-y-3"><p className="eyebrow">Implementation status · 2 November 2026</p>
    <h1 className="text-2xl font-bold">Assessment workflow and remaining work</h1>
    <p>This is a maintained source-code snapshot. It does not confirm which changes are deployed, whether an import completed, or the quality of a real institution’s assessment.</p>
  </header>
  <section className="glass-card p-6 space-y-4"><h2 className="text-xl font-bold">Current workflow</h2>
    {workflow.map(([title, description]) => <article key={title}><h3 className="font-semibold">{title}</h3><p>{description}</p></article>)}
  </section>
  <section className="glass-card p-6 space-y-4"><h2 className="text-xl font-bold">Open implementation and validation work</h2>
    {remaining.map(([title, description]) => <article key={title}><h3 className="font-semibold">{title}</h3><p>{description}</p></article>)}
  </section>
  <p className="panel-muted">Automated checks cover backend and frontend behavior. They do not establish production readiness, extraction completeness or the validity of the experimental score. Plan interpretation is model-assisted, remains fallible and is disabled until configured for validation.</p>
</div>;
