from copy import deepcopy
from django.test import TestCase
from django.utils import timezone

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from .capability.evaluation import evaluate
from .capability.storage import create_run, checkpoint, publish, candidate_requirements


class CapabilityStorageTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='College', student_count=1000)
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.other = Institution.objects.create(name='Other')
        self.other_sprint = Sprint.objects.create(institution=self.other)
        self.document, self.page = self.source(self.sprint)
        self.source(self.other_sprint, 'Foreign evidence must never enter a run.')

    def source(self, sprint, text='A readable institutional passage without staff approval.'):
        doc = Document.objects.create(sprint=sprint, document_type='naac_ssr')
        page = DocumentPage.objects.create(document=doc, page_number=1, text=text)
        return doc, page

    def make_run(self):
        return create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk,
                          population='All faculty and students', reference_period='2025-26')

    def test_tenant_current_versions_and_readable_unreviewed_pages(self):
        old, _ = self.source(self.sprint, 'Superseded evidence cannot count.')
        old.superseded_at = timezone.now()
        old.save()
        DocumentPage.objects.create(document=self.document, page_number=2, text='Unreadable', status='unreadable')
        run = self.make_run()
        self.assertEqual([s['id'] for s in run.inputs['sources']], [str(self.page.pk)])
        self.assertEqual(len(run.inputs['manifest']), 1)
        self.assertEqual(len(run.inputs['manifest'][0]['pages']), 2)
        with self.assertRaises(Sprint.DoesNotExist):
            create_run(institution_id=self.other.pk, sprint_id=self.sprint.pk,
                       population='All', reference_period='2026')
        with self.assertRaises(type(run).DoesNotExist):
            checkpoint(institution_id=self.other.pk, run_id=run.pk, state='running')

    def test_freeze_profile_pages_rubric_and_full_invalidation(self):
        run = self.make_run()
        before = deepcopy(run.inputs)
        self.page.text = 'Changed text'
        self.page.save()
        self.institution.student_count = 10
        self.institution.save()
        run.refresh_from_db()
        self.assertEqual(run.inputs, before)
        self.assertEqual(len(candidate_requirements(run)), 216)
        with self.assertRaises(ValueError):
            run.save()
        with self.assertRaises(ValueError):
            run.events.first().delete()

    def test_atomic_complete_and_terminal_failure_history(self):
        run = self.make_run()
        args = {'institution_id': self.institution.pk, 'run_id': run.pk}
        checkpoint(**args, state='running')
        evaluation = evaluate(run.inputs['sources'], service=None, population='All',
                              reference_period='2026', max_calls=0)
        inference = {'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []}
        incomplete = deepcopy(evaluation)
        incomplete['records'].pop()
        with self.assertRaises(ValueError):
            publish(**args, evaluation=incomplete, inference=inference)
        self.assertEqual(run.events.last().state, 'running')
        checkpoint(**args, state='partial', payload={'completed_indicators': 0})
        completed = publish(**args, evaluation=evaluation, inference=inference)
        self.assertEqual(len(completed.payload['result']['indicators']), 36)
        self.assertEqual(len(completed.payload['records']), 216)
        self.assertEqual(len(completed.payload['pathways']), 3)
        self.assertEqual(completed.payload['result']['upper'], 100)
        with self.assertRaises(ValueError):
            publish(**args, evaluation=evaluation, inference=inference)
        failed = self.make_run()
        event = checkpoint(institution_id=self.institution.pk, run_id=failed.pk,
                           state='failed', payload={'error': 'SECRET provider details'})
        self.assertNotIn('SECRET', str(event.payload))

    def test_forged_citations_and_unsupported_scope_cannot_score(self):
        run = self.make_run()
        args = {'institution_id': self.institution.pk, 'run_id': run.pk}
        checkpoint(**args, state='running')
        rows = [{'condition_id': cid, 'state': 'met', 'reason': 'Claim',
                 'scope_supported': True, 'period_supported': True,
                 'citations': [{'source_id': 'foreign-page', 'quote': self.page.text}]}
                for cid in candidate_requirements(run)]
        event = publish(**args, evaluation={'records': rows},
                        inference={'provider': 'mock', 'model': 'mock', 'settings': {}, 'calls': []})
        self.assertEqual(event.payload['result']['lower'], 0)
        self.assertTrue(all(r['state'] == 'unknown' for r in event.payload['records']))

    def test_supported_full_framework_publication_and_scope_failure(self):
        run = self.make_run()
        args = {'institution_id': self.institution.pk, 'run_id': run.pk}
        checkpoint(**args, state='running')
        rows = [{'condition_id': cid, 'state': 'met', 'reason': 'Scoped current evidence',
                 'scope_supported': True, 'period_supported': True,
                 'citations': [{'source_id': str(self.page.pk), 'quote': self.page.text}]}
                for cid in candidate_requirements(run)]
        event = publish(**args, evaluation={'records': rows},
                        inference={'provider': 'mock', 'model': 'mock', 'settings': {}, 'calls': []})
        self.assertEqual(event.payload['result']['exact_score'], 100)
        self.assertEqual(event.payload['result']['highest_demonstrated_tier'], 'Platinum')
        with self.assertRaises(ValueError):
            type(run).objects.filter(pk=run.pk).update(inputs={})
        with self.assertRaises(ValueError):
            run.events.all().delete()
        second = self.make_run()
        args['run_id'] = second.pk
        checkpoint(**args, state='running')
        for row in rows:
            row['scope_supported'] = False
        event = publish(**args, evaluation={'records': rows},
                        inference={'provider': 'mock', 'model': 'mock', 'settings': {}, 'calls': []})
        self.assertEqual(event.payload['result']['lower'], 0)
