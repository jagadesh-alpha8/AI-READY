"""The runs' display copies (issue 60): the run list and run detail never read a run's inputs or its events whole,
say the same thing the full response does, and carry a version marker that changes whenever the response would."""
import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps as django_apps
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from .capability import run_view
from .capability.report_views import ReportIntegrityError
from .models import CapabilityExplanation, CapabilityRun, CapabilityRunEvent, CapabilityRunView
from . import test_capability_api as api   # the module, not the class: importing it would run its tests twice

LIGHT_ONLY_DROPS = {'reviewed_evidence', 'review_changes_since_assessment', 'scope'}
PLAN_DROPS = {'reviewed_evidence', 'scope'}


def _without_version(data):
    return {k: v for k, v in data.items() if k != 'version'}


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_JUDGMENT='conditions',
    CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False,
    AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class RunViewTests(APITestCase):
    setUp = api.CapabilityAPITests.setUp
    response = api.CapabilityAPITests.response
    start = api.CapabilityAPITests.start
    execute = api.CapabilityAPITests.execute

    def completed(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        return execution

    def detail(self, execution, query='', **headers):
        return self.client.get(f'{self.url}/{execution.run_id}{query}', **headers)

    def test_copy_is_written_with_the_run_and_its_completed_event(self):
        execution = self.completed()
        view = CapabilityRunView.objects.get(run_id=execution.run_id)
        event = execution.run.events.get(state='completed')
        self.assertEqual(view.event_id, event.pk)
        self.assertEqual(view.assessment, run_view.light(event.payload))
        self.assertNotIn('traces', view.assessment)
        self.assertTrue(view.verified)
        self.assertEqual(view.indicators_done, 36)
        self.assertEqual(view.diagnostics_key, run_view.diagnostics_key())
        self.assertEqual(view.stage, 'provisional')

    def test_list_reads_no_inputs_no_events_and_no_review_queue(self):
        self.completed()
        self.start('request-2')   # a queued run too
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        sql = ' '.join(q['sql'] for q in queries.captured_queries)
        self.assertNotIn('"inputs"', sql)
        self.assertNotIn('scoring_capabilityrunevent', sql)
        self.assertNotIn('extraction_documentpage', sql)   # the review queue re-read every page
        self.assertNotIn('review_questions_awaiting', response.data)
        rows = {r['status']: r for r in response.data['results']}
        self.assertEqual(rows['completed']['completed_indicators'], 36)
        self.assertEqual(rows['completed']['stage'], 'provisional')
        self.assertTrue(rows['completed']['assessment_protocol_current'])
        self.assertEqual(rows['completed']['reference_period'], '2025-26')
        self.assertNotIn('scope', rows['completed'])

    def test_light_detail_says_what_the_full_detail_says(self):
        execution = self.completed()
        CapabilityExplanation.objects.create(run=execution.run, event_id=execution.run.events.get(state='completed').pk,
            version='explanations-0.3', payload={'version': 'explanations-0.3', 'requirements': {
                'AIQIF-C1.1.F1': {'found': 'A policy.', 'text': 'Shown.', 'looked': '', 'next_step': ''}},
                'indicators': {}, 'areas': {}})
        light, full = self.detail(execution), self.detail(execution, '?full=1')
        self.assertEqual((light.status_code, full.status_code), (200, 200))
        light, full = _without_version(light.data), _without_version(full.data)
        self.assertEqual(set(full) - set(light), LIGHT_ONLY_DROPS)
        for key in set(light) - {'deterministic_plan'}:
            self.assertEqual(json.dumps(light[key], sort_keys=True, default=str),
                             json.dumps(full[key], sort_keys=True, default=str), key)
        plan_full = {k: v for k, v in full['deterministic_plan'].items() if k not in PLAN_DROPS}
        self.assertEqual(json.dumps(light['deterministic_plan'], sort_keys=True, default=str),
                         json.dumps(plan_full, sort_keys=True, default=str))
        records = {r['condition_id']: r for r in light['assessment']['records']}
        self.assertEqual(records['AIQIF-C1.1.F1']['explanation']['found'], 'A policy.')

    def test_traces_and_full(self):
        execution = self.completed()
        self.assertNotIn('traces', self.detail(execution).data['assessment'])
        self.assertNotIn('traces', self.detail(execution, '?full=1').data['assessment'])
        traced = self.detail(execution, '?traces=1').data
        self.assertEqual(len(traced['assessment']['traces']), 36)
        self.assertIn('reviewed_evidence', traced)

    def test_in_progress_and_failed_runs(self):
        with override_settings(CAPABILITY_MAX_HTTP_CALLS=1):
            execution = self.execute(self.start())
        self.assertEqual(execution.status, 'failed')
        light, full = self.detail(execution).data, self.detail(execution, '?full=1').data
        self.assertIsNone(light['assessment'])
        self.assertEqual(len(light['partial_decisions']), 6)
        self.assertEqual(light['partial_decisions'], full['partial_decisions'])
        self.assertEqual(light['error']['error_code'], 'budget_exhausted')
        self.assertIsNone(light['deterministic_plan'])

    def test_version_marker_and_conditional_requests(self):
        execution = self.completed()
        first = self.detail(execution)
        version = first.data['version']
        self.assertEqual(first['ETag'], f'"{version}"')
        self.assertIn('no-cache', first['Cache-Control'])
        self.assertEqual(self.detail(execution).data['version'], version)
        for tag in (f'"{version}"', f'W/"{version}"', f'"other", W/"{version}"'):
            again = self.detail(execution, HTTP_IF_NONE_MATCH=tag)
            self.assertEqual(again.status_code, 304, tag)
            self.assertEqual(again['ETag'], f'"{version}"')
        self.assertEqual(self.detail(execution, HTTP_IF_NONE_MATCH='"stale"').status_code, 200)
        # Each mode has its own marker, so a light copy is never mistaken for a full one; the full detail is never
        # answered 304 (its review flag follows the sprint's current facts).
        full = self.detail(execution, '?full=1')
        self.assertNotEqual(full.data['version'], version)
        self.assertNotIn('ETag', full)
        self.assertEqual(self.detail(execution, '?full=1', HTTP_IF_NONE_MATCH=f'"{full.data["version"]}"').status_code, 200)
        self.assertNotEqual(self.detail(execution, '?traces=1').data['version'], version)

    def test_marker_changes_when_the_response_would(self):
        execution = self.completed()
        version = self.detail(execution).data['version']
        # Explanations written after completion.
        CapabilityExplanation.objects.create(run=execution.run, event_id=execution.run.events.get(state='completed').pk,
            version='explanations-0.3', payload={'version': 'explanations-0.3', 'requirements': {},
                                                 'indicators': {}, 'areas': {}})
        after_explanations = self.detail(execution).data['version']
        self.assertNotEqual(after_explanations, version)
        self.assertEqual(self.detail(execution, HTTP_IF_NONE_MATCH=f'"{version}"').status_code, 200)
        # A final result published from this run closes its follow-up stage.
        inputs = {**execution.run.inputs, 'second_layer': {'provisional_run_id': str(execution.run_id)}}
        CapabilityRun.objects.create(sprint=self.sprint, inputs=inputs, inputs_hash='x' * 64)
        self.assertNotEqual(self.detail(execution).data['version'], after_explanations)
        # The execution ledger (a heartbeat or reservation) and the deployed code.
        before = self.detail(execution).data['version']
        execution.requests_reserved += 1
        execution.save(update_fields=['requests_reserved'])
        self.assertNotEqual(self.detail(execution).data['version'], before)
        before = self.detail(execution).data['version']
        with patch.object(run_view, 'code_fingerprint', return_value='another-release'):
            self.assertNotEqual(self.detail(execution).data['version'], before)

    def test_missing_or_unfinished_copy_is_rebuilt_on_read(self):
        execution = self.completed()
        expected = _without_version(self.detail(execution).data)
        CapabilityRunView.objects.filter(run_id=execution.run_id).delete()
        self.assertEqual(self.client.get(self.url).status_code, 200)   # list fields only
        view = CapabilityRunView.objects.get(run_id=execution.run_id)
        self.assertIsNone(view.event_id)
        self.assertEqual(_without_version(self.detail(execution).data), expected)
        view.refresh_from_db()
        self.assertTrue(view.verified)
        # A copy made by the migration's SQL has no digest or diagnostics yet.
        CapabilityRunView.objects.filter(run_id=execution.run_id).update(assessment_hash='', diagnostics=None,
                                                                         diagnostics_key='', verified=False)
        self.assertEqual(_without_version(self.detail(execution).data), expected)
        # Diagnostics written by other code are rebuilt.
        CapabilityRunView.objects.filter(run_id=execution.run_id).update(diagnostics={'old': True}, diagnostics_key='old')
        self.assertEqual(_without_version(self.detail(execution).data), expected)

    def test_a_failing_copy_never_stops_a_run(self):
        # A real database error in each write (run creation, every indicator checkpoint, publishing): on PostgreSQL
        # it would abort the run's own transaction without the savepoint.
        def broken(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute('SELECT * FROM no_such_table_for_this_test')
        with patch.object(run_view, '_store_list_fields', side_effect=broken), \
                patch.object(run_view, '_count_indicator', side_effect=broken), \
                patch.object(run_view, '_completed_fields', side_effect=broken):
            execution = self.completed()
        self.assertEqual(execution.run.events.filter(state='partial', payload__kind='indicator').count(), 36)
        self.assertTrue(execution.run.events.filter(state='completed').exists())
        # The start answer built the list fields on read; the completed copy was never stored.
        self.assertIsNone(CapabilityRunView.objects.get(run_id=execution.run_id).event_id)
        row = self.client.get(self.url).data['results'][0]
        self.assertEqual((row['status'], row['completed_indicators']), ('completed', 36))
        detail = self.detail(execution)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data['assessment']['records']), 216)

    def test_a_failed_checkpoint_count_is_corrected_at_completion(self):
        with patch.object(run_view, '_count_indicator', side_effect=RuntimeError('boom')):
            execution = self.completed()
        self.assertEqual(CapabilityRunView.objects.get(run_id=execution.run_id).indicators_done, 36)

    def test_unverified_copy_takes_the_full_path(self):
        # A copy whose integrity check failed is never served: the earlier, checked path answers instead.
        execution = self.completed()
        view = CapabilityRunView.objects.get(run_id=execution.run_id)
        view.verified = False
        with patch.object(run_view, 'ensure', return_value=view):
            data = self.detail(execution).data
        self.assertIn('reviewed_evidence', data)

    def test_migration_backfill_matches_the_copy(self):
        execution = self.completed()
        expected = CapabilityRunView.objects.filter(run_id=execution.run_id).values(
            'stage', 'provisional_run_id', 'refines_run_id', 'rubric_version', 'engine_version', 'prompt_version',
            'retrieval_version', 'reference_period', 'indicators_done', 'event_id', 'assessment').get()
        CapabilityRunView.objects.all().delete()
        migration = importlib.import_module('apps.scoring.migrations.0020_run_view')
        migration.backfill(django_apps, SimpleNamespace(connection=connection))   # reads only .connection
        got = CapabilityRunView.objects.filter(run_id=execution.run_id).values(*expected).get()
        self.assertEqual(json.dumps(got, sort_keys=True, default=str), json.dumps(expected, sort_keys=True, default=str))
        # Then the first read completes it.
        self.assertTrue(run_view.ensure(execution.run_id).verified)

    def test_review_status_is_its_own_call(self):
        response = self.client.get(f'{self.url}/review-status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'review_questions_awaiting': 0})
        foreign = f'/api/v1/sprints/{self.other_sprint.pk}/capability-runs/review-status'
        self.assertEqual(self.client.get(foreign).status_code, 403)

    def test_counts_indicator_checkpoints(self):
        execution = self.start()
        CapabilityRunEvent.objects.create(run=execution.run, state='running')
        CapabilityRunEvent.objects.create(run=execution.run, state='partial', payload={'kind': 'request_reserved'})
        CapabilityRunEvent.objects.create(run=execution.run, state='partial',
                                          payload={'kind': 'indicator', 'records': [], 'trace': {}})
        row = next(r for r in self.client.get(self.url).data['results'] if r['id'] == str(execution.run_id))
        self.assertEqual(row['completed_indicators'], 1)

    def test_report_pdf_is_kept_per_version(self):
        execution = self.completed()
        url = f'{self.url}/{execution.run_id}/report'
        with patch('apps.scoring.capability.report_views.html_to_pdf', return_value=b'%PDF-1.7 test') as render:
            first = self.client.get(url, {'file': 'pdf', 'audience': 'summary'})
            second = self.client.get(url, {'file': 'pdf', 'audience': 'summary'})
            self.assertEqual((first.status_code, second.status_code), (200, 200))
            self.assertEqual((first['X-Report-Cache'], second['X-Report-Cache']), ('miss', 'hit'))
            self.assertEqual(second.content, first.content)
            self.assertEqual(second['Content-Type'], 'application/pdf')
            self.assertEqual(render.call_count, 1)
            # Another report, or the same one once its explanations change, is made afresh.
            self.assertEqual(self.client.get(url, {'file': 'pdf', 'audience': 'detailed'})['X-Report-Cache'], 'miss')
            CapabilityExplanation.objects.create(run=execution.run, event_id=execution.run.events.get(state='completed').pk,
                version='explanations-0.3', payload={'version': 'explanations-0.3', 'requirements': {},
                                                     'indicators': {}, 'areas': {}})
            self.assertEqual(self.client.get(url, {'file': 'pdf', 'audience': 'summary'})['X-Report-Cache'], 'miss')
            self.assertEqual(render.call_count, 3)
        # HTML and JSON are not kept.
        self.assertNotIn('X-Report-Cache', self.client.get(url, {'file': 'html', 'audience': 'summary'}))
        # The integrity check still runs on a kept PDF.
        with patch('apps.scoring.capability.report_views.validate_report_identity',
                   side_effect=ReportIntegrityError()):
            self.assertEqual(self.client.get(url, {'file': 'pdf', 'audience': 'summary'}).status_code, 409)
