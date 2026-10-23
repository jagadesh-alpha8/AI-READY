/**
 * The AI Processing Monitor's "Most recent processing activity" (`npm test`): which jobs it groups, the documents
 * it lists with their outcomes, and how its duration is measured (utils/extractionTiming.ts).
 */
import assert from 'node:assert/strict';
import { after, describe, it } from 'node:test';

import { bundleComponent } from '../testing/bundle.ts';

const { mod, cleanup } = await bundleComponent(new URL('./extractionTiming.ts', import.meta.url));
after(cleanup);
const { latestRunTiming, formatDuration } = mod;

const T0 = Date.parse('2026-10-20T09:00:00Z');
const at = (minutes: number, seconds = 0) => new Date(T0 + (minutes * 60 + seconds) * 1000).toISOString();

const job = (id: string, filename: string, status: string, start: string | null, end: string | null,
  completeness = '') => ({
  id, document_id: `doc-${id}`, document_filename: filename, status, completeness,
  started_at: start, completed_at: end, updated_at: end || start || at(0), created_at: at(0),
});

describe('most recent processing activity', () => {
  // The sprint's first processing (117 documents, long finished), then two documents re-processed a day later.
  const first = Array.from({ length: 117 }, (_, i) => job(`old${i}`, `file${i}.pdf`, 'completed', at(0, i), at(1, i), 'complete'));
  const jobs = [
    ...first,
    job('a', 'aqar-2023.pdf', 'completed', at(24 * 60), at(24 * 60 + 6), 'partial'),
    job('b', 'ssr.pdf', 'failed', at(24 * 60 + 2), at(24 * 60 + 9, 13)),
  ];
  const run = latestRunTiming(jobs, T0 + 25 * 3600 * 1000);

  it('counts only the latest group of jobs, not the sprint total', () => {
    assert.equal(run.active, false);
    assert.equal(run.total, 2);
    assert.equal(run.completed + run.failed + run.stopped, 2);
  });

  it('lists the documents in the activity with their outcomes', () => {
    assert.deepEqual(run.jobs.map((j: { filename: string; outcome: string }) => [j.filename, j.outcome]), [
      ['aqar-2023.pdf', 'partially processed'],
      ['ssr.pdf', 'failed'],
    ]);
  });

  it('measures from the first start to the last finish', () => {
    assert.equal(formatDuration(run.elapsedMs), '9m 13s');
    assert.equal(run.startedAt, Date.parse(at(24 * 60)));
    assert.equal(run.finishedAt, Date.parse(at(24 * 60 + 9, 13)));
  });

  it('jobs more than 5 minutes apart are separate activities', () => {
    const split = latestRunTiming([
      job('x', 'x.pdf', 'completed', at(0), at(1), 'complete'),
      job('y', 'y.pdf', 'completed', at(7), at(8), 'complete'),
    ], T0 + 3600 * 1000);
    assert.deepEqual(split.jobs.map((j: { filename: string }) => j.filename), ['y.pdf']);
  });
});
