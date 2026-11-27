import { test } from 'node:test';
import assert from 'node:assert/strict';

import { PAGE_ROLES, type PageKey } from './access.ts';
import { JOURNEY, journeyOf } from './journeySteps.ts';
import { countsInWords } from './practices.ts';
import { answerState, littleAfter } from './answers.ts';
import { SECTIONS, sectionOf, tabOf, visibleTabs } from '../workspace/sections.ts';

test('every page belongs to one section of the merged website design', () => {
  for (const page of Object.keys(PAGE_ROLES) as PageKey[]) {
    const holders = SECTIONS.filter((s) => s.tabs.some((t) => t.page === page));
    assert.equal(holders.length, 1, page);
  }
  assert.deepEqual(SECTIONS.filter((s) => !s.staff).map((s) => s.label),
    ['Overview', 'Institution', 'Documents', 'Assessment', 'Results', 'Plan', 'Help']);
  assert.deepEqual(SECTIONS.filter((s) => s.staff).map((s) => s.label), ['Benchmarks', 'Manage']);
});

test('a college sees no staff tabs, no hidden tabs, and Results has no Summary', () => {
  for (const s of SECTIONS) for (const t of visibleTabs(s, false)) assert.ok(!t.staff && !t.hidden, `${s.key}: ${t.page}`);
  assert.deepEqual(visibleTabs(sectionOf('areas'), false).map((t) => t.label), ['Readiness areas', 'Reports']);
  assert.deepEqual(visibleTabs(sectionOf('questionnaire'), false).map((t) => t.label), ['Follow-up questions', 'Your answers']);
  assert.deepEqual(visibleTabs(sectionOf('actions'), false).map((t) => t.label), ['Steps', 'Choose a pace', 'Check your own plan']);
  assert.ok(visibleTabs(sectionOf('questionnaire'), true).some((t) => t.page === 'assessment'));
  assert.equal(tabOf('plancompare')?.beta, true);
  assert.equal(sectionOf('copilot').key, 'documents');
});

test('the progress bar follows the assessment', () => {
  const sprint = { id: 's' };
  const at = (run: { shown: boolean; final: boolean; making: boolean }, closed = false) => JOURNEY[journeyOf(sprint, run, closed)]?.label ?? 'done';
  assert.equal(journeyOf(null, { shown: false, final: false, making: false }, false), 0);
  assert.equal(at({ shown: false, final: false, making: false }), 'Documents');
  assert.equal(at({ shown: false, final: false, making: true }), 'Stage 1 result');
  assert.equal(at({ shown: true, final: false, making: false }), 'Follow-up questions');
  assert.equal(at({ shown: true, final: false, making: false }, true), 'Final result');
  assert.equal(at({ shown: true, final: true, making: false }), 'done');
});

test('a topic is counted in words, never as dots', () => {
  const p = (status: 'shown' | 'partly' | 'missing') => ({ status });
  assert.equal(countsInWords([p('shown'), p('partly'), p('partly'), p('missing')]), '1 in place, 2 partly, 1 not found');
  assert.equal(countsInWords([p('missing'), p('missing')]), '2 not found');
});

test('the follow-up list marks where answers stop adding much', () => {
  const qs = (...pts: number[]) => pts.map((points_at_stake) => ({ points_at_stake }));
  assert.equal(littleAfter(qs(5, 3, 1, 0.5, 0.3, 0.2)), 3);   // 9 of 10 points by the third question
  assert.equal(littleAfter(qs(1, 1)), -1);                     // nothing comes after the last question
  assert.equal(littleAfter(qs(0, 0)), -1);
  assert.equal(answerState({ kind: 'answer', choice: 'not_yet', status: 'checked', supported: null }).label, 'Not yet in place');
  assert.equal(answerState({ kind: 'answer', choice: 'yes', status: 'pending', supported: null }).label, 'Being checked against your documents');
});
