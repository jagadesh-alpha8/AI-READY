import { test } from 'node:test';
import assert from 'node:assert/strict';

import { canDo, canSeePage, isStaff, roleLabel } from './access.ts';
import { institutionLevel, meetsLevel, nextTier, tierName } from './maturity.ts';
import { DASH, num, pct, rows, tone, valueText, initials, tidyText } from './format.ts';
import { errorMessage } from './errors.ts';
import { journeyStep } from './journey.ts';
import { gapClass, gapImpact } from './gapClass.ts';
import { cleanParams } from './params.ts';

test('access mirrors the existing frontend rules', () => {
  assert.equal(canDo('iqac_coordinator', 'sprint.manage'), true);
  assert.equal(canDo('iqac_coordinator', 'institution.create'), false);
  assert.equal(canDo('consultant', 'institution.create'), true);
  assert.equal(canDo('consultant', 'users.manage'), false);
  assert.equal(canSeePage('iqac_coordinator', 'benchmarkstudio'), false);
  assert.equal(canSeePage('super_admin', 'benchmarkstudio'), true);
  assert.equal(canSeePage(undefined, 'overview'), false);
  assert.equal(isStaff('consultant'), true);
  assert.equal(isStaff('iqac_coordinator'), false);
  assert.equal(roleLabel('iqac_coordinator'), 'IQAC Coordinator');
  assert.equal(roleLabel('lab_admin'), 'lab admin');
});

test('maturity tiers map onto backend levels without inventing a level', () => {
  assert.equal(tierName('L3'), 'Silver');
  assert.equal(tierName('L2'), 'Gold');
  assert.equal(tierName('L1'), 'Platinum');
  assert.equal(tierName(''), 'Unverified');
  assert.equal(meetsLevel('L1', 'L2'), true);
  assert.equal(meetsLevel('L3', 'L2'), false);
  assert.equal(meetsLevel('', 'L3'), false);
  assert.equal(nextTier('')?.name, 'Silver');
  assert.equal(nextTier('L3')?.name, 'Gold');
  assert.equal(nextTier('L1'), null);
});

test('institution level is the lowest scored level, and unscored stays unknown', () => {
  assert.equal(institutionLevel([]), null);
  assert.equal(institutionLevel([{ included: true, assessment: null }]), null);
  assert.equal(institutionLevel([
    { included: true, assessment: { current_level: 'L2' } },
    { included: true, assessment: { current_level: 'L3' } },
    { included: false, assessment: { current_level: '' } },
  ]), 'L3');
});

test('formatting never turns a missing value into a number', () => {
  assert.equal(num(null), DASH);
  assert.equal(num('61.75', 1), '61.8');
  assert.equal(pct(0.81), '81%');
  assert.equal(pct(81), '81%');
  assert.equal(pct(undefined), DASH);
  assert.equal(valueText(['a', 2]), 'a, 2');
  assert.equal(initials('Meera Shah'), 'MS');
  assert.equal(tone('blocking'), 'bad');
  assert.equal(tone('confirmed'), 'good');
  assert.equal(tone('something'), 'neutral');
  assert.deepEqual(rows({ results: [1, 2] }), [1, 2]);
  assert.deepEqual(rows(null), []);
});

test('errors read DRF shapes', () => {
  assert.equal(errorMessage({ response: { status: 400, data: { non_field_errors: ['Invalid login credentials'] } } }),
    'Invalid login credentials');
  assert.equal(errorMessage({ response: { status: 400, data: { email: ['Required.'] } } }), 'email: Required.');
  assert.match(errorMessage({ message: 'Network Error' }), /could not be reached/);
  assert.equal(errorMessage({ response: { status: 500, data: '<html>' } }), 'The server had a problem handling this request.');
});

test('journey, gap classes and params', () => {
  // Set up, Initial evidence, Assessment, Report & recommendations (flow agreed 12 Nov 2026).
  assert.equal(journeyStep('draft'), 0);
  assert.equal(journeyStep('reviewing'), 1);
  assert.equal(journeyStep('baseline_pending'), 2);
  assert.equal(journeyStep('report_ready'), 3);
  assert.equal(journeyStep(undefined), 0);
  assert.equal(gapClass('conflict'), 'Contradiction requiring resolution');
  assert.equal(gapClass('missing_document'), 'Evidence-only gap');
  assert.equal(gapImpact('blocking'), 'Blocks the next level');
  assert.deepEqual(cleanParams({ a: '', b: 0, c: undefined, d: 'x' }), { b: 0, d: 'x' });
});

test('extracted text keeps line breaks but drops blank-line runs', () => {
  assert.equal(tidyText('MISSION\n\nLine one\r\n\n\nLine two  \n'), 'MISSION\nLine one\nLine two');
  assert.equal(tidyText('One line'), 'One line');
  assert.equal(tidyText(null), '');
});

test('csv quotes commas, quotes and line breaks', async () => {
  const { toCsv } = await import('./csv.ts');
  const out = toCsv(['a', 'b'], [['x, y', 'say "hi"'], [1, null], ['two\nlines', undefined]]);
  assert.equal(out, '﻿a,b\r\n"x, y","say ""hi"""\r\n1,\r\n"two\nlines",\r\n');
});
