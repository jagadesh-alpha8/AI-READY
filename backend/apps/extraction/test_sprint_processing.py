"""Every document of a sprint is processed in that sprint: reused files across sprints, replaced versions,
and reviews / scores that never carry from one sprint to another. (Renamed files, same-sprint retries and
partial re-runs are covered in tests.py.)"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status

from apps.accounts.models import User
from apps.documents.models import Document
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.scoring.services import run_scoring_engine
from apps.sprints.models import Sprint

from .models import ExtractionJob
from .tests import ExtractionJobTestBase, _valid_fact, make_pdf


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True,
                   FACT_AUTO_CONFIRM_MIN_CONFIDENCE=None)  # only a person's review counts here
class SprintScopedProcessingTests(ExtractionJobTestBase):
    def setUp(self):
        super().setUp()
        self.admin = self._make_user('admin@test.edu', User.Role.INSTITUTION_ADMIN, self.institution)
        self.fact_openai_mock.return_value.extract_structured_data.return_value = {'facts': [_valid_fact()]}

    def _bytes(self, document):
        document.file.open('rb')
        try:
            return document.file.read()
        finally:
            document.file.close()

    def _upload(self, sprint, name, content):
        return self.client.post(f'/api/v1/sprints/{sprint.id}/upload-file/',
                                {'file': SimpleUploadedFile(name, content, content_type='application/pdf'),
                                 'document_type': 'naac_ssr'}, format='multipart')

    def _summary(self, sprint):
        return self.client.get(f'/api/v1/sprints/{sprint.id}/processing-summary').data

    def test_a_reused_document_is_reviewed_and_scored_separately_in_each_sprint(self):
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        first = self.sprint.facts.get(field_key='total_faculty')
        self._auth(self.admin)
        self.assertEqual(self.client.post(f'/api/v1/facts/{first.id}/confirm', {}).status_code, 200)

        # Sprint 2 holds the same file (renamed) and processes it in its own context.
        sprint2 = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self._auth(self.iqac)
        upload = self._upload(sprint2, 'SSR-copy-for-sprint-2.pdf', self._bytes(self.document))
        self.assertEqual(upload.status_code, status.HTTP_201_CREATED, upload.data)
        self.client.post(f'/api/v1/sprints/{sprint2.id}/extraction-jobs/')
        second = sprint2.facts.get(field_key='total_faculty')

        self.assertNotEqual(first.id, second.id)
        first.refresh_from_db()
        self.assertEqual((first.status, second.status), (ExtractedFact.Status.CONFIRMED, ExtractedFact.Status.EXTRACTED))
        self.assertIsNone(second.reviewed_by)  # the sprint 1 confirmation is not carried forward
        # Each sprint has its own gaps: sprint 1's review closed its own; sprint 2 still has to review.
        self.assertFalse(GapItem.objects.filter(sprint=self.sprint, source_fact=first,
                                                status__in=GapItem.ACTIVE_STATUSES).exists())
        self.assertTrue(GapItem.objects.filter(sprint=sprint2, source_fact=second,
                                               status__in=GapItem.ACTIVE_STATUSES).exists())
        # ...and its own CRI: only its own confirmed facts count.
        self.assertGreater(run_scoring_engine(self.sprint).overall_cri, 0)
        self.assertEqual(run_scoring_engine(sprint2).overall_cri, 0)

    def test_a_sprint_with_reused_and_new_documents_processes_all_of_them(self):
        """Sprint 1: one document. Sprint 2: that document again plus a new one -- both processed in sprint 2."""
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        sprint2 = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self._upload(sprint2, 'doc.pdf', self._bytes(self.document))
        self._upload(sprint2, 'new-aqar.pdf', make_pdf('new-aqar.pdf', ('A new annual quality assurance report page for the extraction pipeline tests.',)).read())
        self.assertEqual(self._summary(sprint2)['counts']['not_processed'], 2)

        jobs = self.client.post(f'/api/v1/sprints/{sprint2.id}/extraction-jobs/').data
        self.assertEqual(len(jobs), 2)
        summary = self._summary(sprint2)
        self.assertEqual((summary['complete'], summary['counts']['total'], summary['counts']['complete']), (True, 2, 2),
                         summary['documents'])
        self.assertEqual(ExtractionJob.objects.filter(sprint=sprint2).count(), 2)
        self.assertEqual(ExtractionJob.objects.filter(sprint=self.sprint).count(), 1)  # sprint 1 untouched

    def test_a_replaced_version_is_kept_but_not_processed_or_counted_again(self):
        self._auth(self.iqac)
        v1 = self._upload(self.sprint, 'report.pdf', make_pdf('report.pdf', ('Version one of the institutional report for the extraction pipeline tests.',)).read())
        v2 = self._upload(self.sprint, 'report.pdf', make_pdf('report.pdf', ('Version two of the institutional report, with new figures for the tests.',)).read())
        old, new = Document.objects.get(id=v1.data['id']), Document.objects.get(id=v2.data['id'])
        self.assertEqual((new.previous_version_id, new.version_number), (old.id, 2))

        jobs = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/').data
        self.assertEqual(sorted(str(j['document_id']) for j in jobs), sorted([str(self.document.id), str(new.id)]))
        self.assertFalse(ExtractionJob.objects.filter(document=old).exists())
        summary = self._summary(self.sprint)
        self.assertEqual(summary['counts']['total'], 2)  # doc.pdf + report.pdf v2; v1 is history
        self.assertNotIn(str(old.id), [d['document_id'] for d in summary['documents']])
        self.assertTrue(Document.objects.filter(pk=old.pk).exists())

        # An old version can still be processed when someone asks for it explicitly.
        explicit = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/', {'document_id': str(old.id)})
        self.assertEqual((explicit.status_code, len(explicit.data)), (status.HTTP_201_CREATED, 1))

    def test_the_summary_names_what_still_needs_processing_and_a_retry_fixes_only_that(self):
        self._auth(self.iqac)
        extra = self._upload(self.sprint, 'aqar.pdf', make_pdf('aqar.pdf', ('Annual quality assurance report text used by the extraction pipeline tests.',)).read())
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/', {'document_id': str(self.document.id)})
        job = ExtractionJob.objects.get(document=self.document)
        job.status = ExtractionJob.Status.FAILED
        job.error_message = 'Could not reach the AI service.'
        job.save(update_fields=['status', 'error_message', 'updated_at'])

        summary = self._summary(self.sprint)
        states = {d['filename']: (d['state'], d['error']) for d in summary['documents']}
        self.assertEqual(states, {'doc.pdf': ('failed', 'Could not reach the AI service.'),
                                  'aqar.pdf': ('not_processed', '')})
        self.assertFalse(summary['complete'])
        self.assertIn('2 of 2 included document(s) are not fully processed', summary['description'])

        retried = self.client.post(f'/api/v1/extraction-jobs/sprints/{self.sprint.id}/process-incomplete').data
        self.assertEqual(len(retried), 2)
        self.assertIn(str(job.id), [j['id'] for j in retried])  # the failed attempt is reused, not duplicated
        self.assertEqual(ExtractionJob.objects.filter(sprint=self.sprint).count(), 2)
        self.assertTrue(self._summary(self.sprint)['complete'], self._summary(self.sprint)['documents'])
        facts_before = self.sprint.facts.count()
        self.assertEqual(self.client.post(f'/api/v1/extraction-jobs/sprints/{self.sprint.id}/process-incomplete').data, [])
        self.assertEqual(self.sprint.facts.count(), facts_before)
        self.assertTrue(Document.objects.filter(id=extra.data['id']).exists())
