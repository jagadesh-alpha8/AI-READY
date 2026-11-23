import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  achievedTier, capabilityTone, countedShare, creditLabel, fraction, heldLine, isActive, scoreLabel, stateCounts, stateLabel, tierLabel,
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
