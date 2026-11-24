"""Evidence map step 3 and an end-to-end map-mode run: the map's status endpoint, tagging after extraction, and a run
started and judged through the API on a tagged sprint. No model calls (a stand-in judge)."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.documents.models import Document
from apps.extraction.models import ExtractionJob
from apps.institutions.models import Institution
from apps.scoring import test_capability_api as api   # the module: importing the class would run its tests twice
from apps.sprints.models import Sprint

from . import spec, tagging
from .models import MapJob, MapPage
from .status import current_version
from .tasks import queue_after_extraction, tag_sprint

MAP_SETTINGS = dict(CAPABILITY_RETRIEVAL_MODE='map', CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000,
                    CAPABILITY_FOLLOW_UP_SEARCH=False, CAPABILITY_PROMPT_TOKEN_CEILING=None, EVIDENCE_MAP_AI_MODEL='')


def tag_every_page(sprint, model='tagger'):
    """Store a direct tag for C1.1 on every readable page of the sprint, as a finished pass would."""
    version = current_version()
    MapJob.objects.create(sprint=sprint, map_version=version, model=model, shape='one', status=MapJob.Status.COMPLETED,
                          pages_total=1, pages_to_tag=1, pages_tagged=1, spend_cap_usd=1, finished_at=timezone.now())
    for document in tagging.sprint_documents(sprint):
        for page in document['readable']:
            MapPage.objects.get_or_create(
                text_hash=spec.text_hash(page['text']), map_version=version, model=model,
                defaults={'status': MapPage.Status.TAGGED, 'page_type': 'report_narrative',
                          'tags': [{'indicator': 'AIQIF-C1.1', 'requirements': ['AIQIF-C1.1.F1'],
                                    'strength': 'direct', 'quote': page['text'][:40], 'quote_found': True,
                                    'reason': 'stand-in'}]})


@override_settings(**{**api.CapabilityAPITests._overridden_settings, **MAP_SETTINGS})
class MapRunTests(APITestCase):
    setUp = api.CapabilityAPITests.setUp
    response = api.CapabilityAPITests.response
    start = api.CapabilityAPITests.start
    execute = api.CapabilityAPITests.execute

    def test_a_tagged_sprint_runs_on_map_packets_end_to_end(self):
        tag_every_page(self.sprint)
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        inputs = execution.run.inputs
        policy = inputs['retrieval_policy']
        self.assertEqual((policy['mode'], policy['map_model']), ('map', 'tagger'))
        self.assertEqual(policy['map_coverage']['tagged'], 1)
        self.assertEqual(len(inputs['evidence_map']['pages']), 1)
        event = execution.run.events.get(state='completed')
        traces = {t['indicator']: t for t in event.payload['traces']}
        windows = traces['AIQIF-C1.1']['evidence_map']['windows']
        self.assertEqual(windows[0]['reasons'][0]['step'], 'direct')
        self.assertEqual(traces['AIQIF-C1.2']['evidence_map']['tagged_chars'], 0)   # other indicators: fill only

    def test_an_untagged_sprint_falls_back_to_keyword_mode_and_says_so(self):
        execution = self.execute(self.start())
        self.assertEqual(execution.status, 'completed')
        policy = execution.run.inputs['retrieval_policy']
        self.assertEqual(policy['mode'], 'bm25')
        self.assertEqual(policy['map_fallback']['reason'], 'no_map')
        self.assertNotIn('evidence_map', execution.run.inputs)

    def test_retagging_never_changes_a_started_run(self):
        tag_every_page(self.sprint)
        execution = self.start()
        frozen = execution.run.inputs['evidence_map']
        MapPage.objects.update(tags=[])
        execution = self.execute(execution)
        self.assertEqual(execution.status, 'completed')
        self.assertEqual(execution.run.inputs['evidence_map'], frozen)


@override_settings(SECURE_SSL_REDIRECT=False)
class StatusEndpointTests(APITestCase):
    setUp = api.CapabilityAPITests.setUp
    response = api.CapabilityAPITests.response

    def status_url(self, sprint=None):
        return f'/api/v1/sprints/{(sprint or self.sprint).pk}/evidence-map/status'

    def job(self, **fields):
        return MapJob.objects.create(sprint=self.sprint, map_version=current_version(), model='m', shape='one',
                                     spend_cap_usd=1, **{'pages_total': 100, 'pages_to_tag': 100, **fields})

    def test_no_map(self):
        response = self.client.get(self.status_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['warning'], response.data['job']), ('no_map', None))
        self.assertEqual(self.client.get(self.status_url(self.other_sprint)).status_code, 403)

    def test_a_finished_pass(self):
        self.job(status=MapJob.Status.COMPLETED, pages_tagged=97, pages_failed=3, finished_at=timezone.now())
        data = self.client.get(self.status_url()).data
        self.assertEqual((data['tagged_share'], data['warning']), (0.97, None))

    def test_a_pass_under_the_threshold_or_stopped_warns(self):
        self.job(status=MapJob.Status.COMPLETED, pages_tagged=90, pages_failed=10)
        self.assertEqual(self.client.get(self.status_url()).data['warning'], 'map_incomplete')
        self.job(status=MapJob.Status.STOPPED, pages_tagged=100)
        self.assertEqual(self.client.get(self.status_url()).data['warning'], 'map_incomplete')

    def test_a_running_pass_and_a_changed_document(self):
        job = self.job(status=MapJob.Status.RUNNING)
        self.assertEqual(self.client.get(self.status_url()).data['warning'], 'tagging_in_progress')
        MapJob.objects.filter(pk=job.pk).update(status=MapJob.Status.COMPLETED, pages_tagged=100)
        document = Document.objects.filter(sprint=self.sprint).first()
        ExtractionJob.objects.create(sprint=self.sprint, document=document, status=ExtractionJob.Status.COMPLETED,
                                     completed_at=timezone.now() + timedelta(seconds=5))
        data = self.client.get(self.status_url()).data
        self.assertEqual((data['warning'], data['documents_changed']), ('map_out_of_date', True))


class AfterExtractionTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        self.document = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')

    def test_off_by_default(self):
        with patch('apps.evidence_map.tasks.tag_sprint.delay') as delay, self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(queue_after_extraction(self.sprint))
        delay.assert_not_called()

    @override_settings(EVIDENCE_MAP_AUTO_TAG=True)
    def test_queued_once_extraction_is_idle(self):
        with patch('apps.evidence_map.tasks.tag_sprint.delay') as delay, self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(queue_after_extraction(self.sprint))
        delay.assert_called_once_with(str(self.sprint.pk))

    @override_settings(EVIDENCE_MAP_AUTO_TAG=True)
    def test_not_while_extraction_or_tagging_is_running(self):
        job = ExtractionJob.objects.create(sprint=self.sprint, document=self.document,
                                           status=ExtractionJob.Status.RUNNING)
        self.assertFalse(queue_after_extraction(self.sprint))
        ExtractionJob.objects.filter(pk=job.pk).update(status=ExtractionJob.Status.COMPLETED)
        MapJob.objects.create(sprint=self.sprint, map_version='v', model='m', shape='one', spend_cap_usd=1)
        self.assertFalse(queue_after_extraction(self.sprint))
        with patch('apps.evidence_map.tagging.run') as run:
            self.assertIsNone(tag_sprint(str(self.sprint.pk)))
        run.assert_not_called()

    @override_settings(EVIDENCE_MAP_AUTO_TAG=True, EVIDENCE_MAP_STALE_SECONDS=60)
    def test_a_dead_pass_no_longer_blocks(self):
        job = MapJob.objects.create(sprint=self.sprint, map_version='v', model='m', shape='one', spend_cap_usd=1)
        MapJob.objects.filter(pk=job.pk).update(started_at=timezone.now() - timedelta(hours=1))
        with patch('apps.evidence_map.tasks.tag_sprint.delay'), self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(queue_after_extraction(self.sprint))

    @override_settings(EVIDENCE_MAP_AUTO_TAG=True)
    def test_a_failure_never_reaches_extraction(self):
        with patch('apps.evidence_map.tasks.running_job', side_effect=RuntimeError('database')):
            self.assertFalse(queue_after_extraction(self.sprint))
