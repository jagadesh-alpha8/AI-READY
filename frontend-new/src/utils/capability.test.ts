import { test } from 'node:test';
import assert from 'node:assert/strict';

import { achievedTier, capabilityTone, isActive, scoreLabel, stateCounts, stateLabel, tierLabel } from './capability.ts';

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
