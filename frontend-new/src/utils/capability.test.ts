import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  achievedTier, bandTier, capabilityTone, countedShare, creditLabel, fraction, heldLine, isActive, scoreLabel, stageLabel, stateCounts,
  stateLabel, tierLabel, tierShown,
} from './capability.ts';

const tier = (name: string, eligibility: string) => ({ name, eligibility, threshold: null, pillar_floor: null, gates: {} });

test('score shows bounds until every condition is decided', () => {
  assert.equal(scoreLabel({ exact_score: null, lower: 12.345, upper: 61 }), '12.3–61.0 / 100');
  assert.equal(scoreLabel({ exact_score: 58.04, lower: 58, upper: 58 }), '58.0 / 100');
});

test('achieved tier is the highest demonstrated one, never inferred', () => {
  assert.equal(achievedTier({ tiers: [tier('Silver', 'demonstrated'), tier('Gold', 'unresolved'), tier('Platinum', 'requirements_unmet')] }), 'Silver');
  assert.equal(achievedTier({ tiers: [tier('Silver', 'unresolved')] }), null);
  assert.equal(achievedTier({ badge_policy: 'not_calibrated', tiers: [tier('Silver', 'demonstrated')] }), null);
});

test('labels, tones, counts and job state', () => {
  assert.equal(stateLabel('unknown'), 'Evidence needed');
  assert.equal(tierLabel('requirements_unmet'), 'Requirements unmet');
  assert.equal(capabilityTone('met'), 'good');
  assert.equal(capabilityTone('unknown'), 'warn');
  assert.equal(capabilityTone('conflicting'), 'bad');
  assert.deepEqual(stateCounts({ indicators: [{ conditions: [{ state: 'met' }, { state: 'unknown' }, { state: 'unknown' }] }] } as never),
    { met: 1, not_met: 0, unknown: 2, conflicting: 0 });
  assert.equal(isActive({ status: 'running' }), true);
  assert.equal(isActive({ status: 'completed' }), false);
  assert.equal(isActive(null), false);
});

const rec = (credit: number, extra: Record<string, unknown> = {}) =>
  ({ condition_id: 'X.1.F1', state: 'met' as const, reason: '', citations: [], credit, ...extra });

test('fractions arrive as "1/4", "0.25" or numbers', () => {
  assert.equal(fraction('1/4'), 0.25);
  assert.equal(fraction('0.25'), 0.25);
  assert.equal(fraction(0.5), 0.5);
  assert.equal(fraction(null), 0);
  assert.equal(fraction('x'), 0);
});

test('held credit follows reserve.record_factor', () => {
  assert.equal(countedShare(rec(1)), 1);                                                     // no reserve: counts in full
  assert.equal(countedShare(rec(1, { depth_share: '1/4' })), 0.75);                          // provisional: evidenced
  assert.equal(countedShare(rec(1, { depth_share: '1/4', depth_level: 'substantiated' })), 0.875);
  assert.equal(countedShare(rec(1, { depth_share: '1/4', depth_level: 'strong' })), 1);
  assert.equal(countedShare(rec(0.25, { depth_share: '1/4', depth_min_credit: '1/2' })), 1); // related only: not held (v2)
  assert.equal(countedShare(rec(0.5, { depth_share: '1/4', depth_min_credit: '1/2' })), 0.75);
  assert.equal(countedShare(rec(0.25, { depth_share: '1/4' })), 0.75);                       // v1 record: no minimum
  assert.equal(countedShare(rec(0, { depth_share: '1/4' })), 1);
  // depth-reserve-v4: the held share rises from nothing at the line, so more credit never counts for less
  const v4 = { depth_share: '1/4', depth_min_credit: '5/8', depth_ramp: true };
  assert.equal(countedShare(rec(0.625, v4)), 1);
  assert.equal(countedShare(rec(1, v4)), 0.75);
  assert.ok(Math.abs(countedShare(rec(0.75, v4)) - (1 - 0.25 / 3)) < 1e-9);
  assert.ok(0.625 * countedShare(rec(0.625, v4)) > 0.583 * countedShare(rec(0.583, v4)));
  assert.equal(countedShare(rec(0.75, { ...v4, depth_exempt: 'established in follow-up' })), 1);
});

test('credit label says what is counted while credit is held', () => {
  assert.equal(creditLabel(rec(1)), 'credit 100%');
  assert.equal(creditLabel(rec(1, { depth_share: '1/4' })), 'credit 100% (75% counted until follow-up answers show depth)');
  assert.equal(creditLabel(rec(1, { depth_share: '1/4', depth_level: 'strong' })), 'credit 100%');
});

test('held line beside the headline score', () => {
  const held = { share: 0.25, evidence_score: 26.14, held_points: 5.16, earned_back_points: 0, still_held_points: 5.16 };
  assert.equal(heldLine(null), null);
  assert.equal(heldLine({ ...held, held_points: 0, still_held_points: 0 }), null);
  assert.equal(heldLine(held), '5.16 points held until you answer the follow-up questions');
  assert.equal(heldLine({ ...held, earned_back_points: 2, still_held_points: 3.16 }),
    '3.16 points held until you answer the follow-up questions · 2 points earned back by your follow-up answers');
});

test('Stage 1 and final labels; the tier only on the final score (23 Nov)', () => {
  assert.equal(stageLabel('provisional'), 'Stage 1 result: Document Review');
  assert.equal(stageLabel(null), 'Stage 1 result: Document Review');
  assert.equal(stageLabel('final'), 'Final AI-READY Score');
  assert.equal(tierShown('provisional'), false);
  assert.equal(tierShown(undefined), false);
  assert.equal(tierShown('final'), true);
});

test("a part-credit run's level is its score band, whatever the rubric's badge policy says", () => {
  // Five levels, one star for every 20 points (23 Nov); every score has a level.
  assert.deepEqual(bandTier(25.36), { current: 'Getting there', next: 'Prepared', pointsToNext: 14.64 });
  assert.deepEqual(bandTier(14.06), { current: 'Starting out', next: 'Getting there', pointsToNext: 5.94 });
  assert.deepEqual(bandTier(72), { current: 'Advanced', next: 'Leading', pointsToNext: 8 });
  assert.equal(bandTier(95).next, null);
  assert.equal(achievedTier({ tiers: [], badge_policy: 'not_calibrated', score: 61 }), 'Advanced');
  assert.equal(achievedTier({ tiers: [], badge_policy: 'not_calibrated', score: 0 }), 'Starting out');
  assert.equal(achievedTier({ tiers: [tier('Silver', 'demonstrated')], badge_policy: 'not_calibrated' }), null);
});

test('the screens show the published run, never just the newest one', async () => {
  const { shownRun } = await import('./capability.ts');
  const job = (id: string, status = 'completed', stage: 'provisional' | 'final' = 'provisional', provisional_run_id: string | null = null) =>
    ({ id, status, stage, provisional_run_id, created_at: '', stalled: false }) as never;
  const list = [job('new'), job('final', 'completed', 'final', 'stage1'), job('stage1'), job('failed', 'failed')];
  const pub = (run_id: string, stage: 'provisional' | 'final' = 'provisional', provisional_run_id: string | null = null) =>
    ({ run_id, stage, provisional_run_id, published_at: '', published_by: null, note: '' });

  // Published final: its Stage 1 run carries the questions; a newer completed run waits for staff.
  const final = shownRun(list, pub('final', 'final', 'stage1'), false);
  assert.deepEqual([final.id, final.stage, final.provisionalId, final.published, final.preview], ['final', 'final', 'stage1', true, false]);
  assert.equal(final.newer && (final.newer as { id: string }).id, 'new');
  // Published newest: nothing newer.
  assert.equal(shownRun(list, pub('new'), false).newer, null);
  // A published run beyond the list's first page is older than the newest on it.
  assert.equal((shownRun(list, pub('old'), true).newer as { id: string }).id, 'new');
  // Nothing published: staff preview the newest completed run; a college sees nothing, "being prepared".
  const preview = shownRun(list, null, true);
  assert.deepEqual([preview.id, preview.preview, preview.published], ['new', true, false]);
  const college = shownRun(list, null, false);
  assert.deepEqual([college.id, college.preparing, college.provisionalId], ['', true, '']);
  // No completed run at all: nothing to prepare.
  assert.equal(shownRun([job('x', 'running'), job('y', 'failed')], null, false).preparing, false);
});
