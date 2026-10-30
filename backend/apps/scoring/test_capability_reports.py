import json
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import override_settings
from rest_framework.test import APITestCase

from . import test_recommendations as fixtures
from .capability.validation import compare_export
from .models import CapabilityRun, CapabilityRunEvent, RecommendationSnapshot, RecommendationActionState


@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_RECOMMENDATIONS_ENABLED=True,
                  CAPABILITY_ASSESSMENT_ENABLED=True)
class CapabilityReportTests(APITestCase):
    rows = fixtures.RecommendationTests.rows
    response = fixtures.RecommendationTests.response

    def prepare_run(self):
        fixtures.RecommendationTests.prepare_run(self)
        from .models import CapabilityExecution
        CapabilityExecution.objects.create(run=self.run, sprint=self.sprint, status='completed',
            idempotency_key=str(self.run.pk), request_hash=self.run.inputs_hash)

    def setUp(self):
        fixtures.RecommendationTests.setUp(self)
        self.report_url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}/report'

    def test_report_without_baseline_approval_is_pinned_and_inference_free(self):
        before = (CapabilityRun.objects.count(), CapabilityRunEvent.objects.count(), RecommendationSnapshot.objects.count())
        with patch('apps.scoring.tasks.get_ai_service') as factory:
            response = self.client.get(self.report_url, {'file': 'json'})
            html = self.client.get(self.report_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.status_code, 200)
        self.assertFalse(factory.called)
        data = json.loads(response.content)
        self.assertEqual(len(data['assessment']['result']['indicators']), 36)
        self.assertEqual(len(data['assessment']['records']), 216)
        self.assertEqual(data['inputs_hash'], self.run.inputs_hash)
        self.assertEqual(data['reference_period'], '2025-26')
        self.assertEqual(len(data['assessment']['pathways']), 3)
        self.assertIn('private, no-store', html['Cache-Control'])
        self.assertIn("default-src 'none'", html['Content-Security-Policy'])
        self.assertEqual(before, (CapabilityRun.objects.count(), CapabilityRunEvent.objects.count(), RecommendationSnapshot.objects.count()))
        for i in self.run.inputs['rubric']['indicators']:
            self.assertContains(html, i['code'])
        # New mutable institution changes never rewrite the frozen report.
        self.institution.name = 'Changed after assessment'; self.institution.save()
        self.assertEqual(json.loads(self.client.get(self.report_url, {'file': 'json'}).content)['profile']['name'], 'College')

    def test_native_pdf_contains_frozen_assessment_and_never_calls_a_model(self):
        import pymupdf
        before = CapabilityRunEvent.objects.count()
        with patch('apps.scoring.tasks.get_ai_service') as factory:
            response = self.client.get(self.report_url, {'file': 'pdf'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-'))
        document = pymupdf.open(stream=response.content, filetype='pdf')
        text = ''.join(page.get_text() for page in document)
        self.assertIn(str(self.run.pk), text)
        self.assertIn(self.run.inputs_hash, text.replace('\n', ''))
        self.assertIn('Understanding this result', text)
        for indicator in self.run.inputs['rubric']['indicators']:
            for condition in indicator['conditions']:
                self.assertIn(condition['id'], text)
        self.assertFalse(factory.called)
        self.assertEqual(CapabilityRunEvent.objects.count(), before)

    def test_report_cross_tenant_and_noncompleted_access(self):
        self.user.institution = self.other; self.user.save()
        self.assertEqual(self.client.get(self.report_url).status_code, 403)
        self.user.institution = self.institution; self.user.save()
        from .capability.storage import create_run
        pending = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk, population='All', reference_period='2025-26')
        from .models import CapabilityExecution
        CapabilityExecution.objects.create(run=pending, sprint=self.sprint, idempotency_key='pending', request_hash=pending.inputs_hash)
        self.assertEqual(self.client.get(self.report_url.replace(str(self.run.pk), str(pending.pk))).status_code, 409)
        self.assertEqual(self.client.get(self.report_url, {'file': 'docx'}).status_code, 400)
        self.assertEqual(self.client.get(self.report_url, {'recommendation_id': 'invalid'}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.report_url).status_code, 401)

    def test_recommendation_version_and_workflow_are_separate_and_tenant_checked(self):
        ex = fixtures.RecommendationTests.start(self)
        aid = ex.snapshot.inputs['actions'][0]['id']
        RecommendationActionState.objects.create(snapshot=ex.snapshot, condition_id=aid, status='completed', owner='Coordinator')
        data = json.loads(self.client.get(self.report_url, {'file': 'json', 'recommendation_id': str(ex.snapshot_id)}).content)
        self.assertIsNone(data['recommendation']['tailoring'])
        self.assertEqual(data['recommendation']['workflow_at_export'][0]['status'], 'completed')
        self.assertEqual(data['assessment']['result'], self.run.events.filter(state='completed').last().payload['result'])
        html = self.client.get(self.report_url, {'recommendation_id': str(ex.snapshot_id)})
        self.assertEqual(html.status_code, 200)
        # Same institution, different assessment still cannot mix recommendation versions.
        first_url = self.report_url
        self.prepare_run()
        self.report_url = first_url.replace(str(data['run_id']), str(self.run.pk))
        self.assertEqual(self.client.get(self.report_url, {'recommendation_id': str(ex.snapshot_id)}).status_code, 404)

    def test_offline_validation_separates_replay_accuracy_and_agreement(self):
        data = json.loads(self.client.get(self.report_url, {'file': 'json'}).content)
        rubric = self.run.inputs['rubric']
        report = compare_export(data, rubric=rubric)
        self.assertTrue(report['numerical_replay_matches'])
        self.assertIsNone(report['accuracy'])
        self.assertIsNone(report['cold_run_agreement'])
        gold = {'inputs_hash': data['inputs_hash'], 'rubric_hash': data['assessment']['result']['rubric_hash'],
                'records': [dict(data['assessment']['records'][0], state='unknown')]}
        report = compare_export(data, rubric=rubric, gold=gold, repeat=data)
        self.assertEqual(report['accuracy']['labelled_conditions'], 1)
        self.assertEqual(report['accuracy']['exact_state_accuracy'], 0)
        self.assertEqual(report['cold_run_agreement'], 1)
        gold['inputs_hash'] = 'other'
        with self.assertRaises(ValueError):
            compare_export(data, rubric=rubric, gold=gold)
        other = deepcopy(data); other['assessment']['records'].pop()
        with self.assertRaises(ValueError):
            compare_export(other, rubric=rubric)
        other = deepcopy(data); other['inputs_hash'] = 'changed'
        with self.assertRaises(ValueError):
            compare_export(data, rubric=rubric, repeat=other)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'assessment.json'; path.write_text(json.dumps(data))
            output = StringIO(); call_command('validate_capability', str(path), stdout=output)
            self.assertTrue(json.loads(output.getvalue())['numerical_replay_matches'])
            data['assessment']['result']['lower'] = 99; path.write_text(json.dumps(data))
            with self.assertRaises(CommandError):
                call_command('validate_capability', str(path), stdout=StringIO())

    def test_report_escapes_untrusted_source_and_profile_html(self):
        self.institution.name = '<script>profile_attack()</script>'
        self.institution.save()
        self.page.text = '<script>source_attack()</script> scoped evidence across the institution in 2025-26'
        self.page.save()
        self.prepare_run()
        url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}/report'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>')
        self.assertContains(response, '&lt;script&gt;profile_attack()&lt;/script&gt;')
        self.assertContains(response, '&lt;script&gt;source_attack()&lt;/script&gt;')
        self.assertContains(response, 'AIQIF-NEXT-0.1')

    def test_capability_onboarding_does_not_require_legacy_approval_or_fact_review(self):
        response = self.client.get('/api/v1/auth/guide-status', {'sprint_id': str(self.sprint.pk), 'workflow': 'capability'})
        self.assertEqual(response.status_code, 200)
        steps = {s['id']: s for s in response.data['steps']}
        self.assertNotIn('baseline_approval', steps)
        self.assertNotIn('facts_review', steps)
        self.assertEqual(steps['live_cri']['status'], 'completed')
        self.assertIsNone(steps['reports']['block_reason'])
        self.assertIn('without model calls', steps['reports']['purpose'])
        # Existing clients can still explicitly use the original guide semantics.
        legacy = self.client.get('/api/v1/auth/guide-status', {'sprint_id': str(self.sprint.pk)})
        self.assertIn('baseline_approval', {s['id'] for s in legacy.data['steps']})
