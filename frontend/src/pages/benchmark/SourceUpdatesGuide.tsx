import React from 'react';

/**
 * The human steps from a source change to colleges seeing a changed benchmark. Shown in the
 * Watcher and Candidates tabs so it is clear that no step updates a benchmark or release by itself.
 */
const STEPS: { title: string; where: string; detail: string }[] = [
  { title: 'Change found', where: 'Watcher', detail: 'The watcher (daily, or "Check now" by hand) lists what changed on a watched official page.' },
  { title: 'Decide on the change', where: 'Watcher > Changes', detail: 'Accept, reject or ignore it with a note. Accepting only records the decision; it changes no benchmark or release.' },
  { title: 'Create a candidate', where: 'Watcher > Changes', detail: '"Create a benchmark candidate" proposes the update (or one is created for an important change).' },
  { title: 'Expert review', where: 'Candidates', detail: 'Each required expert role reviews it (a different person for each). All approve = approved.' },
  { title: 'Open a benchmark draft', where: 'Candidates', detail: '"Open a new draft" reopens the active benchmark as its next draft version.' },
  { title: 'Edit and confirm', where: 'Levels', detail: 'Edit levels, evidence and applicability rules; an InGage reviewer confirms the new content.' },
  { title: 'Release', where: 'Releases', detail: 'Add it to the next release, submit, approve (a different person) and publish. Only then do colleges see it.' },
];

export const SourceUpdatesGuide: React.FC<{ current?: 'watcher' | 'candidates' }> = ({ current }) => (
  <details className="glass-card p-3 text-xs" open={false}>
    <summary className="cursor-pointer font-bold text-ink-900">How a source change reaches a benchmark (all steps are done by people)</summary>
    <ol className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
      {STEPS.map((s, i) => {
        const here = (current === 'watcher' && s.where.startsWith('Watcher')) || (current === 'candidates' && s.where === 'Candidates');
        return (
          <li key={s.title} className={`rounded-lg border p-2 ${here ? 'border-brand-500 bg-brand-50' : 'border-line-200 bg-surface'}`}>
            <p className="font-bold text-ink-900">{i + 1}. {s.title} <span className="font-normal text-ink-500">· {s.where}</span></p>
            <p className="text-ink-700 mt-0.5">{s.detail}</p>
          </li>
        );
      })}
    </ol>
  </details>
);
