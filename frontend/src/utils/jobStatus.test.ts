import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ExtractionJob } from '../types/extraction.ts';
import {
  attemptOutcome,
  attemptSource,
  jobActivity,
  jobBadge,
  nextRetry,
  partialSummary,
} from './jobStatus.ts';

const baseJob: ExtractionJob = {
  id: 'j1',
  sprint_id: 's1',
  document_id: 'd1',
  document_filename: 'doc.pdf',
  status: 'running',
  current_step: 'extracting_facts',
  current_step_label: 'Extracting facts',
  progress_percentage: 50,
  started_at: '2026-10-28T10:00:00Z',
  completed_at: null,
  error_message: '',
  retry_count: 0,
  ai_router: '',
  attempts: [],
  completeness: '',
  extraction_warnings: [],
  chunks_total: 10,
  chunks_completed: 4,
  created_at: '2026-10-28T10:00:00Z',
  updated_at: '2026-10-28T10:05:00Z',
  ai_input_tokens: 100,
  ai_output_tokens: 50,
  ai_cost_usd: null,
};

describe('jobStatus utility tests', () => {
  it('jobActivity shows phase_label when active, falls back to current_step_label', () => {
    const jobWithPhase = { ...baseJob, status: 'running' as const, phase_label: 'Reading pages 5 of 20 (2 by OCR)' };
    assert.equal(jobActivity(jobWithPhase), 'Reading pages 5 of 20 (2 by OCR)');

    const jobWithoutPhase = { ...baseJob, status: 'running' as const, phase_label: undefined };
    assert.equal(jobActivity(jobWithoutPhase), 'Extracting facts');

    const queuedJob = { ...baseJob, status: 'pending' as const, phase_label: undefined, current_step_label: '' };
    assert.equal(jobActivity(queuedJob), 'Queued');
  });

  it('jobBadge reflects completed/partial, cancelled/stopped, failed, or active phases', () => {
    assert.equal(jobBadge(undefined), 'not started');
    assert.equal(jobBadge({ ...baseJob, status: 'completed', completeness: 'complete' }), 'completed');
    assert.equal(jobBadge({ ...baseJob, status: 'completed', completeness: 'partial' }), 'partial');
    assert.equal(jobBadge({ ...baseJob, status: 'cancelled' }), 'stopped');
    assert.equal(jobBadge({ ...baseJob, status: 'failed' }), 'failed');

    assert.equal(jobBadge({ ...baseJob, status: 'running', phase: 'reading_pages' }), 'reading pages');
    assert.equal(jobBadge({ ...baseJob, status: 'running', phase: 'extracting_facts' }), 'extracting facts');
    assert.equal(jobBadge({ ...baseJob, status: 'pending', phase: 'queued' }), 'queued');
    assert.equal(jobBadge({ ...baseJob, status: 'retrying', phase: 'waiting_for_router' }), 'waiting for router');
  });

  it('nextRetry formats next retry timestamp when due in future', () => {
    const fixedNow = new Date('2026-10-28T10:00:00Z').getTime();
    const futureTime = new Date('2026-10-28T10:05:00Z').toISOString();
    const pastTime = new Date('2026-10-28T09:55:00Z').toISOString();

    assert.equal(nextRetry({ ...baseJob, status: 'running' }, fixedNow), '');
    assert.equal(nextRetry({ ...baseJob, status: 'retrying', next_retry_at: null }, fixedNow), '');
    assert.equal(nextRetry({ ...baseJob, status: 'retrying', next_retry_at: pastTime }, fixedNow), 'next attempt starting');
    assert.match(nextRetry({ ...baseJob, status: 'retrying', next_retry_at: futureTime }, fixedNow), /next attempt at /);
  });

  it('attemptSource distinguishes multi-router vs single provider mode', () => {
    assert.equal(attemptSource(baseJob, 'router-1'), 'router-1');
    assert.equal(attemptSource({ ...baseJob, processing_mode: 'multi_router' }, ''), 'router not assigned');
    assert.equal(attemptSource({ ...baseJob, processing_mode: 'single' }, ''), 'single provider');
  });

  it('attemptOutcome translates known outcome keys into human friendly strings', () => {
    assert.equal(attemptOutcome('out_of_credit'), 'out of credit');
    assert.equal(attemptOutcome('continued'), 'continued (large document)');
    assert.equal(attemptOutcome('recovered'), 'recovered after an interruption');
    assert.equal(attemptOutcome('rate_limited'), 'rate limited');
  });

  it('partialSummary describes missing chunks, unreadable pages, and extracted facts', () => {
    const job1 = { ...baseJob, chunks_total: 10, chunks_completed: 8, unreadable_pages: 2 };
    assert.equal(
      partialSummary(job1, 15),
      'Partially processed: 8 of 10 text chunks read · 2 pages could not be read · 15 facts extracted. Some content was not read.'
    );

    const job2 = { ...baseJob, chunks_total: 5, chunks_completed: 5, unreadable_pages: 1 };
    assert.equal(
      partialSummary(job2, 7),
      'Partially processed: 1 page could not be read · 7 facts extracted. Some content was not read.'
    );
  });
});

