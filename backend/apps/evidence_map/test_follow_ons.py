"""The follow-ons to tagging and assessment (EVIDENCE_MAP_AUTO_CHECK, EVIDENCE_MAP_AUTO_LEARN). No model calls."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from . import spec, tasks
from .models import MapJob


class FollowOnTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))

    def job(self, status=MapJob.Status.COMPLETED, version='v1'):
        return MapJob.objects.create(sprint=self.sprint, map_version=version, model='m', shape='areas',
                                     spend_cap_usd=1, status=status)

    def tag(self, job):
        with patch('apps.evidence_map.tagging.start_job', return_value=job), \
                patch('apps.evidence_map.tagging.run', return_value=job), \
                patch('apps.evidence_map.requirement_check.run') as check:
            tasks.tag_sprint(str(self.sprint.pk))
        return check

    def test_the_check_follows_a_completed_pass_only_when_switched_on(self):
        self.assertFalse(self.tag(self.job()).called)
        with override_settings(EVIDENCE_MAP_AUTO_CHECK=True, EVIDENCE_MAP_CHECK_MAX_COST_USD=0.25):
            check = self.tag(self.job())
            self.assertEqual(check.call_args.kwargs['map_version'], 'v1')
            self.assertEqual(check.call_args.kwargs['max_cost_usd'], 0.25)
            MapJob.objects.all().delete()
            self.assertFalse(self.tag(self.job(status=MapJob.Status.STOPPED)).called)

    def test_a_failing_check_never_raises(self):
        with patch('apps.evidence_map.requirement_check.run', side_effect=RuntimeError('x')):
            self.assertIsNone(tasks.check_after_tagging(self.sprint, self.job()))

    def test_learning_is_queued_only_when_switched_on(self):
        run = SimpleNamespace(pk='r1', sprint_id=self.sprint.pk, inputs={})
        self.assertFalse(tasks.queue_learning(run))
        with override_settings(EVIDENCE_MAP_AUTO_LEARN=True), patch.object(tasks.learn_from_run, 'delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(tasks.queue_learning(run))
            delay.assert_called_once_with('r1')

    def test_learning_goes_to_the_runs_own_map_else_the_configured_one(self):
        own = SimpleNamespace(sprint_id=self.sprint.pk,
                              inputs={'retrieval_policy': {'mode': 'map', 'map_version': 'vx', 'map_model': 'mx'}})
        self.assertEqual(tasks.learning_target(own), ('vx', 'mx'))
        keyword = SimpleNamespace(sprint_id=self.sprint.pk, inputs={'retrieval_policy': {'mode': 'bm25'}})
        self.assertEqual(tasks.learning_target(keyword), (None, None))
        with override_settings(EVIDENCE_MAP_SHAPE='areas'):
            version = spec.map_version('areas', *spec.rubric_sources())
            self.job(version=version)
            self.assertEqual(tasks.learning_target(keyword), (version, 'm'))
