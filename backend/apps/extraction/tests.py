import io
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
from fpdf import FPDF
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
import anthropic as anthropic_sdk
from PIL import Image

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.facts.models import ExtractedFact
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .exceptions import AIResponseError, PermanentExtractionError, RecoverableExtractionError
from .models import ExtractionJob
from .services.ai_service import detect_provider, get_ai_service
from .services.anthropic_client import AnthropicExtractionService, AnthropicResponseError
from .services.conflict_checker import ConflictValidationError, OpenAIConflictChecker
from .services.gap_detector import RuleBasedGapDetector
from .services.openai_classifier import (
    CLASSIFICATION_SCHEMA, ClassificationValidationError, OpenAIDocumentClassifier,
)
from .services.openai_client import OpenAIExtractionService, OpenAIResponseError
from .services.openai_fact_extractor import OpenAIFactExtractor
from .services.pdf_reader import PDFPageReader
from .tasks import _handle_recoverable

PASSWORD = 'Str0ng!DevPassw0rd'

#: A classification result the real OpenAIDocumentClassifier would accept --
#: used to fake a plausible AI response wherever a test just needs the
#: pipeline to get past the (now real, OpenAI-backed) classification step
#: without asserting anything about classification itself.
FAKE_CLASSIFICATION_RESULT = {
    'document_type': 'naac_ssr',
    'document_title': 'Self Study Report',
    'reporting_year': None,
    'institution_name': None,
    'confidence': 0.9,
    'reasoning': 'Test fixture classification result.',
}


def make_pdf_bytes(page_texts=('Sample document text for extraction pipeline tests.',)):
    """A real, pdfplumber-readable PDF -- one page per string in
    `page_texts`; an empty string produces a page with no text drawn on it
    (simulating a blank/scanned page)."""
    pdf = FPDF()
    for text in page_texts:
        pdf.add_page()
        if text:
            pdf.set_font('Helvetica', size=12)
            pdf.cell(0, 10, text)
    return bytes(pdf.output())


def make_scanned_pdf_bytes():
    """A PDF page with an embedded image and no real text layer -- what an
    actual scan looks like to a text extractor."""
    image = Image.new('RGB', (40, 40), color='white')
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    pdf = FPDF()
    pdf.add_page()
    pdf.image(buf, x=10, y=10, w=20)
    return bytes(pdf.output())


def make_pdf(name='doc.pdf', page_texts=('Sample document text for extraction pipeline tests.',)):
    return SimpleUploadedFile(name, make_pdf_bytes(page_texts), content_type='application/pdf')


class ExtractionJobTestBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')

        self.iqac = self._make_user('iqac@test.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.outsider = self._make_user('outsider@test.edu', User.Role.HOD, self.other_institution)

        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)

        # ExtractionPipeline's default classifier and fact extractor are both
        # real (OpenAI-backed) as of this task -- these tests exercise the
        # pipeline's orchestration, not classification/extraction themselves,
        # so both underlying OpenAI calls are mocked here once for every test
        # in this file that runs the real pipeline. Tests about classification/
        # extraction behavior itself live in OpenAIDocumentClassifierTests and
        # OpenAIFactExtractorTests, further down, with their own mocks.
        classifier_patcher = patch('apps.extraction.services.openai_classifier.get_ai_service')
        mock_classifier_openai_cls = classifier_patcher.start()
        mock_classifier_openai_cls.return_value.extract_structured_data.return_value = dict(FAKE_CLASSIFICATION_RESULT)
        self.addCleanup(classifier_patcher.stop)

        # Defaults to "the AI found nothing" -- individual tests that care
        # about persisted fact content override
        # self.fact_openai_mock.return_value.extract_structured_data.return_value.
        fact_patcher = patch('apps.extraction.services.openai_fact_extractor.get_ai_service')
        self.fact_openai_mock = fact_patcher.start()
        self.fact_openai_mock.return_value.extract_structured_data.return_value = {'facts': []}
        self.addCleanup(fact_patcher.stop)

        self._auth(self.iqac)
        upload = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file/',
            {'file': make_pdf(), 'document_type': 'naac_ssr'}, format='multipart',
        )
        self.document = Document.objects.get(id=upload.data['id'])
        self.sprint.refresh_from_db()  # now 'collecting'
        self.client.credentials()  # tests authenticate explicitly as whichever persona they need

    @staticmethod
    def _make_user(email, role, institution):
        return User.objects.create_user(
            email=email, username=email.split('@')[0], password=PASSWORD,
            first_name='Test', last_name=role, role=role, institution=institution,
        )

    def _auth(self, user):
        login = self.client.post('/api/v1/auth/login/', {'email': user.email, 'password': PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access_token"]}')


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class JobCreationTests(ExtractionJobTestBase):
    def test_post_creates_job_for_eligible_document(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(str(response.data[0]['document_id']), str(self.document.id))
        self.assertEqual(str(response.data[0]['sprint_id']), str(self.sprint.id))

    def test_post_without_trailing_slash_matches_frontend_client(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_post_does_not_duplicate_jobs_for_already_processed_documents(self):
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, [])
        self.assertEqual(ExtractionJob.objects.filter(document=self.document).count(), 1)

    def test_post_with_explicit_document_id_targets_only_that_document(self):
        self._auth(self.iqac)
        response = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/', {'document_id': str(self.document.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data), 1)

    def test_post_with_document_id_not_in_sprint_is_not_found(self):
        self._auth(self.iqac)
        other_sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        response = self.client.post(
            f'/api/v1/sprints/{other_sprint.id}/extraction-jobs/', {'document_id': str(self.document.id)},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_job_listing_scoped_to_sprint(self):
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # -- unauthorized access -------------------------------------------------

    def test_unauthenticated_create_rejected(self):
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_from_outside_institution_rejected(self):
        self._auth(self.outsider)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ExtractionJob.objects.count(), 0)

    def test_list_from_outside_institution_rejected(self):
        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_from_outside_institution_rejected(self):
        self._auth(self.iqac)
        create = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job_id = create.data[0]['id']

        self._auth(self.outsider)
        response = self.client.get(f'/api/v1/extraction-jobs/{job_id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_detail_accessible_to_own_institution(self):
        self._auth(self.iqac)
        create = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job_id = create.data[0]['id']
        response = self.client.get(f'/api/v1/extraction-jobs/{job_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class SuccessfulRunTests(ExtractionJobTestBase):
    """Exercises the real pipeline end to end (OpenAI calls mocked at the
    class/document level, everything else genuinely real) -- 'completed
    jobs' and 'task state transitions' coverage."""

    def test_job_completes_through_all_seven_steps(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job = ExtractionJob.objects.get(id=response.data[0]['id'])

        self.assertEqual(job.status, ExtractionJob.Status.COMPLETED)
        self.assertEqual(job.current_step, ExtractionJob.Step.PREPARING_REVIEW_WORKSPACE)
        self.assertEqual(job.progress_percentage, 100)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(job.error_message, '')
        self.assertEqual(job.retry_count, 0)

    def test_document_marked_processed_on_completion(self):
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.PROCESSED)
        self.assertIsNotNone(self.document.processed_at)
        self.assertEqual(self.document.processing_status, 'classified')

    def test_ocr_required_is_corrected_from_the_upload_time_guess(self):
        """Every PDF is flagged ocr_required=True at upload time purely by
        file extension (apps.documents.constants.OCR_REQUIRED_EXTENSIONS),
        before any content is read. Once the real PDFPageReader actually
        reads this document's real, extractable text, that stale guess must
        be corrected to False -- not left misleadingly True forever."""
        self.assertTrue(self.document.ocr_required)  # the upload-time guess
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.document.refresh_from_db()
        self.assertFalse(self.document.ocr_required)
        self.assertIsNotNone(self.document.page_count)

    def test_ocr_required_stays_true_for_a_genuinely_unreadable_document(self):
        """The other direction of the same fix: a document that genuinely
        has no extractable text must end up ocr_required=True from the real
        reader's finding, with real ocr_warnings explaining why -- not just
        coincidentally matching the upload-time guess for the wrong reason."""
        self._auth(self.iqac)
        blank_upload = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file/',
            {'file': make_pdf(name='blank.pdf', page_texts=('',)), 'document_type': 'aqar_report'},
            format='multipart',
        )
        blank_document = Document.objects.get(id=blank_upload.data['id'])

        self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/', {'document_id': str(blank_document.id)},
        )

        blank_document.refresh_from_db()
        self.assertTrue(blank_document.ocr_required)
        self.assertTrue(blank_document.ocr_warnings)

    def test_sprint_advances_from_collecting_to_reviewing(self):
        self._auth(self.iqac)
        self.assertEqual(self.sprint.status, Sprint.Status.COLLECTING)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.sprint.refresh_from_db()
        self.assertEqual(self.sprint.status, Sprint.Status.REVIEWING)

    def test_no_facts_are_fabricated_when_the_ai_finds_none(self):
        """Per 'no fake data': when the (mocked) AI genuinely returns no
        facts, a completed job must not have invented any."""
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        self.assertEqual(self.document.extracted_facts.count(), 0)

    def test_facts_are_persisted_end_to_end_through_the_real_pipeline(self):
        """The core of 'connect OpenAIFactExtractor to ExtractedFact
        database': a fact the (mocked) AI returns must actually reach the
        database, not be dropped by an unmapped field_mapper stage."""
        self.fact_openai_mock.return_value.extract_structured_data.return_value = {
            'facts': [{
                'field_name': 'Total Faculty Count', 'field_key': 'total_faculty', 'value': '42',
                'data_type': 'number', 'pillar': 'faculty_ai_capability', 'owner_role': 'hr_officer',
                'source_page': '1', 'source_snippet': 'The institution has 42 faculty members.',
                'confidence_score': 0.96, 'confidence_reason': 'Explicitly stated in the source.',
            }],
        }
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')

        fact = self.document.extracted_facts.get()
        self.assertEqual(fact.field_key, 'total_faculty')
        self.assertEqual(fact.value, 42)
        self.assertEqual(fact.normalized_value, 42)
        self.assertEqual(fact.data_type, 'number')
        self.assertEqual(fact.pillar, 'faculty_ai_capability')
        self.assertEqual(fact.owner_role, 'hr_officer')
        self.assertEqual(fact.source_page, '1')
        self.assertEqual(fact.source_document_id, self.document.id)
        self.assertEqual(fact.sprint_id, self.sprint.id)
        self.assertEqual(fact.extraction_method, 'openai')
        self.assertEqual(fact.status, 'extracted')

    def test_low_confidence_fact_creates_a_persisted_gap(self):
        """RuleBasedGapDetector's low_confidence check, exercised through
        the real pipeline (not just the unit tests further down) -- proves
        the gap it returns actually reaches the database via _persist_gaps'
        create_gap_if_new call, not just a returned-but-dropped dict."""
        self.fact_openai_mock.return_value.extract_structured_data.return_value = {
            'facts': [_valid_fact(confidence_score=0.3)],
        }
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')

        fact = self.document.extracted_facts.get()
        gap = GapItem.objects.get(gap_type=GapItem.GapType.LOW_CONFIDENCE)
        self.assertEqual(gap.source_fact_id, fact.id)
        self.assertEqual(gap.sprint_id, self.sprint.id)
        self.assertEqual(gap.priority, GapItem.Priority.HIGH)  # below the "very low" threshold too

    def test_gaps_created_on_completion_are_real_not_fabricated(self):
        """With no facts extracted (the default mocked AI response is
        empty), RuleBasedGapDetector has nothing to flag either -- so once
        the sprint reaches 'reviewing', every gap present comes from
        apps.gaps.services' real, deterministic sprint-level generation
        (see apps/gaps/tests.py): genuinely missing required documents
        (everything but the uploaded naac_ssr), not fabricated data."""
        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        gaps = list(self.sprint.gaps.all())
        self.assertTrue(gaps)
        self.assertTrue(all(gap.gap_type == GapItem.GapType.MISSING_DOCUMENT for gap in gaps))
        missing_types = {gap.title for gap in gaps}
        self.assertNotIn('Missing NAAC SSR', missing_types)

    def test_job_status_exposes_full_lifecycle_via_api(self):
        self._auth(self.iqac)
        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        detail = self.client.get(f'/api/v1/extraction-jobs/{response.data[0]["id"]}/')
        for field in ('status', 'current_step', 'progress_percentage', 'error_message', 'started_at', 'completed_at'):
            self.assertIn(field, detail.data)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class FailureTests(ExtractionJobTestBase):
    """Permanent and unexpected failures resolve in a single attempt --
    no retry-loop involved, so these are safe to exercise end to end."""

    @patch('apps.extraction.tasks.ExtractionPipeline')
    def test_permanent_error_fails_immediately_without_retry(self, mock_pipeline_cls):
        mock_pipeline_cls.return_value.run.side_effect = PermanentExtractionError('corrupt file')
        self._auth(self.iqac)

        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job = ExtractionJob.objects.get(id=response.data[0]['id'])

        self.assertEqual(job.status, ExtractionJob.Status.FAILED)
        self.assertEqual(job.retry_count, 0)
        self.assertIn('corrupt file', job.error_message)
        self.assertEqual(mock_pipeline_cls.return_value.run.call_count, 1)

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.FAILED)

    @patch('apps.extraction.tasks.ExtractionPipeline')
    def test_unrecognized_error_fails_without_retry(self, mock_pipeline_cls):
        """An error the pipeline doesn't classify as recoverable/permanent
        must not be retried blindly."""
        mock_pipeline_cls.return_value.run.side_effect = ValueError('totally unexpected bug')
        self._auth(self.iqac)

        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job = ExtractionJob.objects.get(id=response.data[0]['id'])

        self.assertEqual(job.status, ExtractionJob.Status.FAILED)
        self.assertIn('Unexpected error', job.error_message)
        self.assertEqual(mock_pipeline_cls.return_value.run.call_count, 1)

    @patch('apps.extraction.tasks.ExtractionPipeline')
    def test_missing_job_id_does_not_crash_the_task(self, mock_pipeline_cls):
        import uuid

        from .tasks import run_extraction_job
        run_extraction_job.delay(str(uuid.uuid4()))
        mock_pipeline_cls.return_value.run.assert_not_called()

    @patch('apps.extraction.tasks.ExtractionPipeline')
    def test_first_recoverable_attempt_marks_job_retrying(self, mock_pipeline_cls):
        """One recoverable failure (before retries are exhausted) leaves the
        job visibly 'retrying', not silently stuck or marked failed."""
        mock_pipeline_cls.return_value.run.side_effect = RecoverableExtractionError('transient glitch')
        self._auth(self.iqac)

        response = self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')
        job = ExtractionJob.objects.get(id=response.data[0]['id'])

        self.assertEqual(job.status, ExtractionJob.Status.RETRYING)
        self.assertEqual(job.retry_count, 1)
        self.assertIn('transient glitch', job.error_message)


class RetryDecisionLogicTests(TestCase):
    """Unit tests for the retry/backoff/exhaustion decision logic itself.

    Celery's eager mode (used above for end-to-end tests) runs a task
    exactly once per `.delay()` call and does not loop through retries --
    `self.retry()` just raises `celery.exceptions.Retry`, the same as it
    would be caught and rescheduled by a real worker. Rather than
    reimplementing Celery's own redelivery mechanics here, these tests
    drive `_handle_recoverable` directly with a stand-in task object,
    which is what actually encodes *this project's* retry policy.
    """

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        document = Document.objects.create(
            sprint=sprint, document_type='naac_ssr', status=Document.Status.UPLOADED,
        )
        self.job = ExtractionJob.objects.create(sprint=sprint, document=document)

    @staticmethod
    def _fake_task(retries):
        task = MagicMock()
        task.request.retries = retries

        def _raise(*args, **kwargs):
            raise RuntimeError('celery would reschedule here')
        task.retry.side_effect = _raise
        return task

    def test_schedules_a_retry_while_attempts_remain(self):
        task = self._fake_task(retries=0)
        with self.assertRaises(RuntimeError):
            _handle_recoverable(task, self.job, RecoverableExtractionError('flaky'))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, ExtractionJob.Status.RETRYING)
        self.assertEqual(self.job.retry_count, 1)
        task.retry.assert_called_once()
        self.assertEqual(task.retry.call_args.kwargs['countdown'], settings.EXTRACTION_RETRY_BACKOFF_SECONDS)

    def test_backoff_grows_exponentially_with_attempt_number(self):
        task = self._fake_task(retries=2)
        with self.assertRaises(RuntimeError):
            _handle_recoverable(task, self.job, RecoverableExtractionError('still flaky'))

        expected = settings.EXTRACTION_RETRY_BACKOFF_SECONDS * (2 ** 2)
        self.assertEqual(task.retry.call_args.kwargs['countdown'], expected)

    def test_gives_up_once_retries_are_exhausted(self):
        task = self._fake_task(retries=settings.EXTRACTION_MAX_RETRIES)
        _handle_recoverable(task, self.job, RecoverableExtractionError('never recovers'))

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, ExtractionJob.Status.FAILED)
        self.assertIn('Failed after', self.job.error_message)
        self.assertIn(str(settings.EXTRACTION_MAX_RETRIES), self.job.error_message)
        task.retry.assert_not_called()

    def test_does_not_endlessly_retry_past_the_configured_maximum(self):
        """A permanent-failure job never re-enters RETRYING once exhausted,
        no matter how many more times it's (hypothetically) invoked."""
        task = self._fake_task(retries=settings.EXTRACTION_MAX_RETRIES + 5)
        _handle_recoverable(task, self.job, RecoverableExtractionError('never recovers'))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, ExtractionJob.Status.FAILED)
        task.retry.assert_not_called()


def _fake_openai_request():
    return httpx.Request('POST', 'https://api.openai.com/v1/chat/completions')


def _fake_openai_response(status_code):
    return httpx.Response(status_code=status_code, request=_fake_openai_request())


def _fake_completion(content, finish_reason='stop'):
    """A stand-in for an OpenAI ChatCompletion, shaped just enough for
    OpenAIExtractionService._parse_response to read choices[0].finish_reason
    and choices[0].message.content."""
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@override_settings(AI_BASE_URL='')  # isolate from whatever the real .env happens to have set
class OpenAIExtractionServiceTests(SimpleTestCase):
    """Unit tests for the OpenAI service layer (apps.extraction.services.
    openai_client). No real network call is ever made here -- either the
    OpenAI client class itself is mocked, or a fake client double is
    injected via the constructor's `client=` param."""

    def _service(self, client=None, api_key='sk-test', model='gpt-test'):
        return OpenAIExtractionService(api_key=api_key, model=model, client=client)

    def _call(self, service):
        return service.extract_structured_data(
            system_prompt='Extract facts from this document.',
            user_content='document text...',
            response_schema={'type': 'object'},
        )

    # -- configuration --------------------------------------------------

    @override_settings(OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='gpt-test')
    def test_missing_api_key_raises_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            OpenAIExtractionService()

    @override_settings(OPENAI_API_KEY='sk-test', OPENAI_EXTRACTION_MODEL='')
    def test_missing_model_raises_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            OpenAIExtractionService()

    @patch('apps.extraction.services.openai_client.OpenAI')
    def test_client_initializes_with_the_configured_api_key(self, mock_openai_cls):
        OpenAIExtractionService(api_key='sk-test', model='gpt-test')
        mock_openai_cls.assert_called_once_with(api_key='sk-test', base_url=None)

    @patch('apps.extraction.services.openai_client.OpenAI')
    def test_custom_base_url_is_passed_to_the_client(self, mock_openai_cls):
        OpenAIExtractionService(api_key='sk-test', model='my-combo', base_url='http://localhost:20128/v1')
        mock_openai_cls.assert_called_once_with(api_key='sk-test', base_url='http://localhost:20128/v1')

    def test_injected_client_is_used_instead_of_constructing_a_real_one(self):
        fake_client = MagicMock()
        service = self._service(client=fake_client)
        self.assertIs(service._client, fake_client)

    # -- successful response ---------------------------------------------

    def test_successful_response_returns_normalized_python_data(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(
            content='{"institution_name": "MKCE", "confidence": 0.92}',
        )
        service = self._service(client=fake_client)

        result = self._call(service)

        self.assertEqual(result, {'institution_name': 'MKCE', 'confidence': 0.92})
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs['model'], 'gpt-test')
        self.assertEqual(call_kwargs['response_format']['json_schema']['schema'], {'type': 'object'})

    # -- API errors -------------------------------------------------------

    def test_rate_limit_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RateLimitError(
            'rate limited', response=_fake_openai_response(429), body=None,
        )
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_timeout_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = APITimeoutError(request=_fake_openai_request())
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_connection_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = APIConnectionError(request=_fake_openai_request())
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_server_side_status_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = APIStatusError(
            'internal error', response=_fake_openai_response(500), body=None,
        )
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_client_side_status_error_is_treated_as_permanent(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = APIStatusError(
            'bad request', response=_fake_openai_response(400), body=None,
        )
        with self.assertRaises(PermanentExtractionError):
            self._call(self._service(client=fake_client))

    # -- invalid responses ------------------------------------------------

    def test_empty_content_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(content=None)
        with self.assertRaises(OpenAIResponseError):
            self._call(self._service(client=fake_client))

    def test_non_json_content_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(content='not valid json')
        with self.assertRaises(OpenAIResponseError):
            self._call(self._service(client=fake_client))

    def test_truncated_response_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(
            content='{"partial": tr', finish_reason='length',
        )
        with self.assertRaises(OpenAIResponseError):
            self._call(self._service(client=fake_client))

    def test_content_filtered_response_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _fake_completion(
            content=None, finish_reason='content_filter',
        )
        with self.assertRaises(OpenAIResponseError):
            self._call(self._service(client=fake_client))

    def test_no_choices_raises_response_error(self):
        fake_client = MagicMock()
        empty_response = MagicMock()
        empty_response.choices = []
        fake_client.chat.completions.create.return_value = empty_response
        with self.assertRaises(OpenAIResponseError):
            self._call(self._service(client=fake_client))


def _fake_anthropic_request():
    return httpx.Request('POST', 'https://api.anthropic.com/v1/messages')


def _fake_anthropic_response(status_code):
    return httpx.Response(status_code=status_code, request=_fake_anthropic_request())


def _fake_tool_use_message(input_data=None, name='extraction_result', stop_reason='tool_use'):
    """A stand-in for an Anthropic Message, shaped just enough for
    AnthropicExtractionService._parse_response to read stop_reason and find
    a matching tool_use content block."""
    message = MagicMock()
    message.stop_reason = stop_reason
    if input_data is None:
        message.content = []
    else:
        block = MagicMock()
        block.type = 'tool_use'
        block.name = name
        block.input = input_data
        message.content = [block]
    return message


class AnthropicExtractionServiceTests(SimpleTestCase):
    """Unit tests for the Claude counterpart of OpenAIExtractionService --
    same contract, same test shape, so the two stay verifiably equivalent.
    Every Anthropic call is mocked; no real network access."""

    def _service(self, client=None, api_key='sk-ant-test', model='claude-test'):
        return AnthropicExtractionService(api_key=api_key, model=model, client=client)

    def _call(self, service):
        return service.extract_structured_data(
            system_prompt='Extract facts.', user_content='document text...',
            response_schema={'type': 'object'},
        )

    # -- configuration --------------------------------------------------

    @override_settings(AI_API_KEY='', AI_MODEL='claude-test')
    def test_missing_api_key_raises_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            AnthropicExtractionService()

    @override_settings(AI_API_KEY='sk-ant-test', AI_MODEL='')
    def test_missing_model_raises_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            AnthropicExtractionService()

    @patch('apps.extraction.services.anthropic_client.Anthropic')
    def test_client_initializes_with_the_configured_api_key(self, mock_anthropic_cls):
        AnthropicExtractionService(api_key='sk-ant-test', model='claude-test')
        mock_anthropic_cls.assert_called_once_with(api_key='sk-ant-test')

    def test_injected_client_is_used_instead_of_constructing_a_real_one(self):
        fake_client = MagicMock()
        service = self._service(client=fake_client)
        self.assertIs(service._client, fake_client)

    # -- successful response ---------------------------------------------

    def test_successful_response_returns_the_tool_calls_input(self):
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(
            input_data={'institution_name': 'MKCE', 'confidence': 0.92},
        )
        service = self._service(client=fake_client)

        result = self._call(service)

        self.assertEqual(result, {'institution_name': 'MKCE', 'confidence': 0.92})
        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs['model'], 'claude-test')
        self.assertEqual(call_kwargs['tools'][0]['input_schema'], {'type': 'object'})
        self.assertTrue(call_kwargs['tools'][0]['strict'])
        self.assertEqual(call_kwargs['tool_choice']['name'], 'extraction_result')

    # -- API errors -------------------------------------------------------

    def test_rate_limit_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = anthropic_sdk.RateLimitError(
            'rate limited', response=_fake_anthropic_response(429), body=None,
        )
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_timeout_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = anthropic_sdk.APITimeoutError(request=_fake_anthropic_request())
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_connection_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = anthropic_sdk.APIConnectionError(
            request=_fake_anthropic_request(),
        )
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_server_side_status_error_is_treated_as_recoverable(self):
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = anthropic_sdk.APIStatusError(
            'internal error', response=_fake_anthropic_response(500), body=None,
        )
        with self.assertRaises(RecoverableExtractionError):
            self._call(self._service(client=fake_client))

    def test_client_side_status_error_is_treated_as_permanent(self):
        fake_client = MagicMock()
        fake_client.messages.create.side_effect = anthropic_sdk.APIStatusError(
            'bad request', response=_fake_anthropic_response(400), body=None,
        )
        with self.assertRaises(PermanentExtractionError):
            self._call(self._service(client=fake_client))

    # -- invalid responses ------------------------------------------------

    def test_no_matching_tool_call_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(input_data=None)
        with self.assertRaises(AnthropicResponseError):
            self._call(self._service(client=fake_client))

    def test_truncated_response_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(
            input_data={'a': 1}, stop_reason='max_tokens',
        )
        with self.assertRaises(AnthropicResponseError):
            self._call(self._service(client=fake_client))

    def test_refusal_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(
            input_data=None, stop_reason='refusal',
        )
        with self.assertRaises(AnthropicResponseError):
            self._call(self._service(client=fake_client))

    def test_context_window_exceeded_raises_response_error(self):
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(
            input_data=None, stop_reason='model_context_window_exceeded',
        )
        with self.assertRaises(AnthropicResponseError):
            self._call(self._service(client=fake_client))

    def test_response_error_is_also_a_generic_ai_response_error(self):
        """Code that doesn't care which provider answered (e.g.
        openai_fact_extractor's malformed-shape check) can catch just
        AIResponseError and still catch this."""
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_tool_use_message(input_data=None)
        with self.assertRaises(AIResponseError):
            self._call(self._service(client=fake_client))


@override_settings(AI_BASE_URL='')  # isolate from whatever the real .env happens to have set
class AIServiceFactoryTests(SimpleTestCase):
    """Unit tests for apps.extraction.services.ai_service -- the provider
    detection and factory every AI call site goes through."""

    # -- provider detection -----------------------------------------------

    def test_detects_openai_from_key_prefix(self):
        self.assertEqual(detect_provider('sk-proj-abc123'), 'openai')

    def test_detects_anthropic_from_key_prefix(self):
        self.assertEqual(detect_provider('sk-ant-api03-abc123'), 'anthropic')

    def test_unrecognized_key_format_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            detect_provider('not-a-real-key-format')

    # -- factory ------------------------------------------------------------

    @override_settings(AI_API_KEY='', OPENAI_API_KEY='')
    def test_no_key_configured_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            get_ai_service()

    @override_settings(AI_API_KEY='sk-test-key', AI_MODEL='gpt-test', OPENAI_API_KEY='')
    def test_returns_openai_service_for_an_openai_key(self):
        service = get_ai_service()
        self.assertIsInstance(service, OpenAIExtractionService)
        self.assertEqual(service.model, 'gpt-test')

    @override_settings(AI_API_KEY='sk-ant-test-key', AI_MODEL='claude-test', OPENAI_API_KEY='')
    def test_returns_anthropic_service_for_an_anthropic_key(self):
        service = get_ai_service()
        self.assertIsInstance(service, AnthropicExtractionService)
        self.assertEqual(service.model, 'claude-test')

    @override_settings(AI_API_KEY='', AI_MODEL='', OPENAI_API_KEY='sk-legacy-key', OPENAI_EXTRACTION_MODEL='gpt-legacy')
    def test_falls_back_to_openai_api_key_when_ai_api_key_unset(self):
        """Anyone with a .env from before multi-provider support existed
        keeps working unchanged."""
        service = get_ai_service()
        self.assertIsInstance(service, OpenAIExtractionService)
        self.assertEqual(service.api_key, 'sk-legacy-key')
        self.assertEqual(service.model, 'gpt-legacy')

    @override_settings(AI_API_KEY='sk-new-key', OPENAI_API_KEY='sk-old-key', AI_MODEL='')
    def test_ai_api_key_takes_precedence_over_openai_api_key(self):
        service = get_ai_service()
        self.assertEqual(service.api_key, 'sk-new-key')

    @override_settings(AI_API_KEY='sk-test', AI_MODEL='', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='')
    def test_default_model_used_when_none_configured(self):
        service = get_ai_service()
        self.assertEqual(service.model, 'gpt-4o-mini')

    @override_settings(AI_API_KEY='sk-ant-test', AI_MODEL='', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='')
    def test_default_model_used_for_anthropic_when_none_configured(self):
        service = get_ai_service()
        self.assertEqual(service.model, 'claude-haiku-4-5-20251001')

    @override_settings(AI_API_KEY='sk-ant-test', AI_MODEL='', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='gpt-4o-mini')
    def test_stale_openai_extraction_model_does_not_leak_into_anthropic(self):
        """The bug this test guards against: OPENAI_EXTRACTION_MODEL is left
        over in .env from before the key was switched to Anthropic -- it
        must never be handed to a Claude client as its model name."""
        service = get_ai_service()
        self.assertIsInstance(service, AnthropicExtractionService)
        self.assertEqual(service.model, 'claude-haiku-4-5-20251001')

    @override_settings(AI_API_KEY='sk-test', AI_MODEL='', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='gpt-4o')
    def test_openai_extraction_model_still_applies_when_provider_is_openai(self):
        service = get_ai_service()
        self.assertEqual(service.model, 'gpt-4o')

    @override_settings(AI_API_KEY='sk-test', AI_MODEL='gpt-explicit-override', OPENAI_EXTRACTION_MODEL='gpt-4o')
    def test_explicit_model_argument_wins_over_everything(self):
        service = get_ai_service(model='gpt-called-with')
        self.assertEqual(service.model, 'gpt-called-with')

    # -- custom OpenAI-compatible endpoint (AI_BASE_URL) ---------------------

    @override_settings(
        AI_API_KEY='sk-45c32fe83970c5b2-nihvmj-397d2a0c', AI_MODEL='my-combo',
        AI_BASE_URL='http://localhost:20128/v1', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='',
    )
    def test_custom_base_url_returns_an_openai_compatible_service(self):
        """A local router/gateway's key doesn't look like a real OpenAI or
        Anthropic key at all -- AI_BASE_URL must be enough on its own,
        without ever calling detect_provider() on that key."""
        service = get_ai_service()
        self.assertIsInstance(service, OpenAIExtractionService)
        self.assertEqual(service.api_key, 'sk-45c32fe83970c5b2-nihvmj-397d2a0c')
        self.assertEqual(service.model, 'my-combo')
        self.assertEqual(service.base_url, 'http://localhost:20128/v1')

    @override_settings(
        AI_API_KEY='sk-ant-looks-like-anthropic', AI_MODEL='my-combo',
        AI_BASE_URL='http://localhost:20128/v1', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='',
    )
    def test_custom_base_url_wins_even_over_an_anthropic_shaped_key(self):
        """The base URL is an explicit instruction, not a hint -- it must
        override key-format detection entirely, not just act as a fallback."""
        service = get_ai_service()
        self.assertIsInstance(service, OpenAIExtractionService)
        self.assertEqual(service.base_url, 'http://localhost:20128/v1')

    @override_settings(
        AI_API_KEY='sk-45c32fe83970c5b2-nihvmj-397d2a0c', AI_MODEL='',
        AI_BASE_URL='http://localhost:20128/v1', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='',
    )
    def test_custom_base_url_without_a_model_raises(self):
        """There's no sensible default model for an endpoint this app knows
        nothing about -- unlike OpenAI/Anthropic, which fall back to
        DEFAULT_MODELS, this must fail loudly instead of guessing."""
        with self.assertRaises(ImproperlyConfigured):
            get_ai_service()

    @override_settings(
        AI_API_KEY='sk-45c32fe83970c5b2-nihvmj-397d2a0c', AI_MODEL='',
        AI_BASE_URL='http://localhost:20128/v1', OPENAI_API_KEY='', OPENAI_EXTRACTION_MODEL='my-combo',
    )
    def test_openai_extraction_model_is_accepted_as_the_model_for_a_base_url_too(self):
        """OPENAI_EXTRACTION_MODEL is still a valid fallback for AI_BASE_URL
        setups, same as for plain OpenAI -- only AI_MODEL being unset should
        matter, not which specific settings name supplied it."""
        service = get_ai_service()
        self.assertEqual(service.model, 'my-combo')


class PDFPageReaderTests(TestCase):
    """Unit tests for the real PDFPageReader (apps.extraction.services.
    pdf_reader). Every PDF here is a real, valid, pdfplumber-readable file
    built with fpdf2 -- nothing about PDF parsing is mocked."""

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.reader = PDFPageReader()

    def _make_document(self, content, filename='doc.pdf', document_type='naac_ssr', content_type='application/pdf'):
        upload = SimpleUploadedFile(filename, content, content_type=content_type)
        return Document.objects.create(
            sprint=self.sprint, document_type=document_type, file=upload,
            original_filename=filename, mime_type=content_type, status=Document.Status.UPLOADED,
        )

    def test_normal_text_pdf_extracts_real_text(self):
        document = self._make_document(
            make_pdf_bytes(['Hello, this is real NAAC SSR self-study report content for testing.']),
        )
        result = self.reader.read_pages(document)

        self.assertTrue(result['format_supported'])
        self.assertEqual(result['page_count'], 1)
        self.assertEqual(result['pages'][0]['page_number'], 1)
        self.assertIn('real NAAC SSR self-study report content', result['pages'][0]['text'])
        self.assertFalse(result['pages'][0]['requires_ocr'])
        self.assertFalse(result['requires_ocr'])

    def test_multi_page_pdf_preserves_page_numbers_and_text(self):
        document = self._make_document(
            make_pdf_bytes(['Page one content.', 'Page two content.', 'Page three content.']),
        )
        result = self.reader.read_pages(document)

        self.assertEqual(result['page_count'], 3)
        self.assertEqual([p['page_number'] for p in result['pages']], [1, 2, 3])
        self.assertIn('Page one', result['pages'][0]['text'])
        self.assertIn('Page two', result['pages'][1]['text'])
        self.assertIn('Page three', result['pages'][2]['text'])

    def test_max_pages_samples_without_changing_the_reported_page_count(self):
        document = self._make_document(make_pdf_bytes(['One', 'Two', 'Three']))
        result = self.reader.read_pages(document, max_pages=1)

        self.assertEqual(result['page_count'], 3)  # true total, not the sample size
        self.assertEqual(result['pages_read'], 1)
        self.assertEqual(len(result['pages']), 1)

    def test_empty_pdf_page_is_marked_as_requiring_ocr_not_silently_empty(self):
        document = self._make_document(make_pdf_bytes(['']))  # a page with nothing drawn on it
        result = self.reader.read_pages(document)

        self.assertEqual(result['page_count'], 1)
        self.assertEqual(result['pages'][0]['text'], '')
        self.assertTrue(result['pages'][0]['requires_ocr'])
        self.assertTrue(result['requires_ocr'])
        self.assertTrue(result['ocr_warnings'])  # the "why" isn't silent

    def test_scanned_pdf_is_detected_as_requiring_ocr_without_inventing_text(self):
        document = self._make_document(make_scanned_pdf_bytes())
        result = self.reader.read_pages(document)

        self.assertTrue(result['requires_ocr'])
        self.assertEqual(result['pages'][0]['text'], '')

    def test_corrupt_pdf_raises_permanent_error(self):
        document = self._make_document(b'this is not a pdf at all')
        with self.assertRaises(PermanentExtractionError):
            self.reader.read_pages(document)

    def test_unsupported_format_is_reported_honestly_not_silently_empty(self):
        document = self._make_document(
            b'name,value\nfoo,1\n', filename='enrolment.csv',
            document_type='student_strength', content_type='text/csv',
        )
        result = self.reader.read_pages(document)

        self.assertFalse(result['format_supported'])
        self.assertEqual(result['pages'], [])
        self.assertIsNone(result['page_count'])
        self.assertIn('.csv', result['format_note'])

    def test_configured_ocr_provider_is_consulted_for_low_text_pages(self):
        fake_ocr_provider = MagicMock()
        fake_ocr_provider.extract_text.return_value = 'This full paragraph of text was recovered by a real OCR backend.'
        reader = PDFPageReader(ocr_provider=fake_ocr_provider)
        document = self._make_document(make_pdf_bytes(['']))

        result = reader.read_pages(document)

        fake_ocr_provider.extract_text.assert_called_once_with(document, 1)
        self.assertEqual(result['pages'][0]['text'], 'This full paragraph of text was recovered by a real OCR backend.')
        self.assertFalse(result['pages'][0]['requires_ocr'])

    def test_default_ocr_provider_never_fabricates_text(self):
        """With no real OCR backend configured, a low-text page stays
        honestly flagged rather than being filled with invented content."""
        document = self._make_document(make_pdf_bytes(['']))
        result = self.reader.read_pages(document)
        self.assertEqual(result['pages'][0]['text'], '')
        self.assertTrue(result['pages'][0]['requires_ocr'])


class OpenAIDocumentClassifierTests(TestCase):
    """Unit tests for the real, OpenAI-backed DocumentClassifier (apps.
    extraction.services.openai_classifier). The OpenAI service itself is
    always a fake double here -- see PDFPageReaderTests for real PDF I/O,
    and OpenAIExtractionServiceTests for the transport-level SDK mocking."""

    VALID_RESULT = {
        'document_type': 'naac_ssr',
        'document_title': 'Self Study Report',
        'reporting_year': '2025-26',
        'institution_name': 'M. Kumarasamy College of Engineering',
        'confidence': 0.92,
        'reasoning': 'The text contains NAAC SSR section headers and criteria.',
    }

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)

    def _make_document(self, content=None, document_type='naac_ssr'):
        content = content if content is not None else make_pdf_bytes(['NAAC SSR self study report content.'])
        upload = SimpleUploadedFile('doc.pdf', content, content_type='application/pdf')
        return Document.objects.create(
            sprint=self.sprint, document_type=document_type, file=upload,
            original_filename='doc.pdf', mime_type='application/pdf', status=Document.Status.UPLOADED,
        )

    @staticmethod
    def _fake_service(result=None, side_effect=None):
        service = MagicMock()
        if side_effect is not None:
            service.extract_structured_data.side_effect = side_effect
        else:
            service.extract_structured_data.return_value = result
        return service

    def test_successful_classification_returns_the_validated_result(self):
        document = self._make_document()
        service = self._fake_service(dict(self.VALID_RESULT))
        classifier = OpenAIDocumentClassifier(openai_service=service)

        result = classifier.classify(document)

        self.assertEqual(result, self.VALID_RESULT)
        call_kwargs = service.extract_structured_data.call_args.kwargs
        self.assertIn('NAAC SSR self study report content', call_kwargs['user_content'])
        self.assertEqual(call_kwargs['response_schema'], CLASSIFICATION_SCHEMA)

    def test_uploaded_document_type_is_sent_as_a_hint(self):
        document = self._make_document(document_type='aqar_report')
        service = self._fake_service(dict(self.VALID_RESULT))
        classifier = OpenAIDocumentClassifier(openai_service=service)

        classifier.classify(document)

        call_kwargs = service.extract_structured_data.call_args.kwargs
        self.assertIn('aqar_report', call_kwargs['user_content'])

    def test_missing_information_is_accepted_as_null_not_an_error(self):
        document = self._make_document()
        service = self._fake_service({**self.VALID_RESULT, 'reporting_year': None, 'institution_name': None})
        classifier = OpenAIDocumentClassifier(openai_service=service)

        result = classifier.classify(document)

        self.assertIsNone(result['reporting_year'])
        self.assertIsNone(result['institution_name'])

    def test_document_with_no_extractable_text_still_gets_an_honest_prompt(self):
        document = self._make_document(content=make_pdf_bytes(['']))
        service = self._fake_service({**self.VALID_RESULT, 'confidence': 0.1})
        classifier = OpenAIDocumentClassifier(openai_service=service)

        classifier.classify(document)

        call_kwargs = service.extract_structured_data.call_args.kwargs
        self.assertIn('No extractable text was found', call_kwargs['user_content'])

    def test_confidence_out_of_range_is_rejected(self):
        document = self._make_document()
        service = self._fake_service({**self.VALID_RESULT, 'confidence': 1.5})
        classifier = OpenAIDocumentClassifier(openai_service=service)
        with self.assertRaises(ClassificationValidationError):
            classifier.classify(document)

    def test_negative_confidence_is_rejected(self):
        document = self._make_document()
        service = self._fake_service({**self.VALID_RESULT, 'confidence': -0.1})
        classifier = OpenAIDocumentClassifier(openai_service=service)
        with self.assertRaises(ClassificationValidationError):
            classifier.classify(document)

    def test_non_string_field_is_rejected(self):
        document = self._make_document()
        service = self._fake_service({**self.VALID_RESULT, 'document_title': 42})
        classifier = OpenAIDocumentClassifier(openai_service=service)
        with self.assertRaises(ClassificationValidationError):
            classifier.classify(document)

    def test_empty_reasoning_is_rejected(self):
        document = self._make_document()
        service = self._fake_service({**self.VALID_RESULT, 'reasoning': '   '})
        classifier = OpenAIDocumentClassifier(openai_service=service)
        with self.assertRaises(ClassificationValidationError):
            classifier.classify(document)

    def test_invalid_raw_ai_response_propagates_as_a_permanent_error(self):
        """A malformed raw response is already turned into OpenAIResponseError
        inside OpenAIExtractionService -- the classifier must let it
        propagate (it's already a PermanentExtractionError), not swallow it."""
        document = self._make_document()
        service = self._fake_service(side_effect=OpenAIResponseError('not valid JSON'))
        classifier = OpenAIDocumentClassifier(openai_service=service)
        with self.assertRaises(PermanentExtractionError):
            classifier.classify(document)


def _page(number, text):
    return {'page_number': number, 'text': text}


def _valid_fact(**overrides):
    fact = {
        'field_name': 'Total Faculty Count',
        'field_key': 'total_faculty',
        'value': '42',
        'data_type': 'number',
        'pillar': 'faculty_ai_capability',
        'owner_role': 'hr_officer',
        'source_page': '1',
        'source_snippet': 'The institution has 42 faculty members.',
        'confidence_score': 0.96,
        'confidence_reason': 'Explicitly stated in the source.',
    }
    fact.update(overrides)
    return fact


class OpenAIFactExtractorTests(TestCase):
    """Unit tests for the real, OpenAI-backed FactExtractor (apps.
    extraction.services.openai_fact_extractor). The OpenAI service is
    always a fake double here -- see PDFPageReaderTests for real PDF I/O."""

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.document = Document.objects.create(
            sprint=self.sprint, document_type='naac_ssr', original_filename='ssr.pdf',
            mime_type='application/pdf', status=Document.Status.UPLOADED,
        )

    @staticmethod
    def _fake_service(results=None, side_effect=None):
        service = MagicMock()
        if side_effect is not None:
            service.extract_structured_data.side_effect = side_effect
        elif results is not None:
            service.extract_structured_data.side_effect = results
        return service

    # -- basic behavior -----------------------------------------------------

    def test_successful_extraction_returns_the_validated_fact(self):
        service = self._fake_service(results=[{'facts': [_valid_fact()]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        pages = {'pages': [_page(1, 'The institution has 42 faculty members on its rolls.')]}

        facts = extractor.extract_facts(self.document, pages)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact['field_key'], 'total_faculty')
        self.assertEqual(fact['value'], 42)
        self.assertEqual(fact['normalized_value'], 42)
        self.assertEqual(fact['pillar'], 'faculty_ai_capability')
        self.assertEqual(fact['owner_role'], 'hr_officer')
        self.assertEqual(fact['source_page'], '1')
        self.assertEqual(fact['extraction_method'], 'openai')

    def test_empty_document_never_calls_openai(self):
        """A document with no extractable text on any page shouldn't waste
        an API call -- there's nothing to extract facts from."""
        service = self._fake_service(results=[])
        extractor = OpenAIFactExtractor(openai_service=service)

        facts = extractor.extract_facts(self.document, {'pages': [_page(1, ''), _page(2, '   ')]})

        self.assertEqual(facts, [])
        service.extract_structured_data.assert_not_called()

    def test_no_pages_at_all_never_calls_openai(self):
        service = self._fake_service(results=[])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': []})
        self.assertEqual(facts, [])
        service.extract_structured_data.assert_not_called()

    # -- evidence requirements / hallucination prevention -------------------

    def test_fact_with_missing_evidence_snippet_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(source_snippet='')]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_fact_citing_a_page_outside_the_chunk_is_dropped(self):
        """The core hallucination guard: a source_page the model wasn't
        actually given (it only saw page 1) must not be trusted."""
        service = self._fake_service(results=[{'facts': [_valid_fact(source_page='99')]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_fact_with_null_source_page_is_still_accepted(self):
        """'Prefer null over guessing' -- an honestly-unknown page shouldn't
        be penalized the way a fabricated one is."""
        service = self._fake_service(results=[{'facts': [_valid_fact(source_page=None)]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['source_page'], '')

    # -- structured output / confidence validation ---------------------------

    def test_fact_with_invalid_data_type_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(data_type='integer')]}])  # not a real choice
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_fact_with_invalid_pillar_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(pillar='not_a_real_pillar')]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_fact_with_invalid_owner_role_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(owner_role='super_admin')]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_malformed_top_level_response_is_treated_like_any_other_chunk_failure(self):
        """A response missing the "facts" list is turned into
        OpenAIResponseError inside _extract_chunk -- since that's a
        PermanentExtractionError, it's handled the same as any other
        per-chunk failure (logged, that chunk contributes no facts) rather
        than raised (see test_permanent_error_on_one_chunk_does_not_block_
        the_others for why single-chunk failures shouldn't be fatal)."""
        service = self._fake_service(results=[{'not_facts': []}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_confidence_out_of_range_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(confidence_score=1.5)]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_negative_confidence_is_dropped(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(confidence_score=-0.2)]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    def test_boundary_confidence_values_are_accepted(self):
        service = self._fake_service(results=[{'facts': [
            _valid_fact(field_key='a', confidence_score=0.0),
            _valid_fact(field_key='b', confidence_score=1.0),
        ]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual({f['field_key'] for f in facts}, {'a', 'b'})

    # -- Django-side value typing --------------------------------------------

    def test_percentage_value_is_normalized_to_a_number(self):
        service = self._fake_service(results=[{'facts': [
            _valid_fact(field_key='placement_rate', data_type='percentage', value='87%'),
        ]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Placement rate: 87%.')]})
        self.assertEqual(facts[0]['normalized_value'], 87.0)

    def test_list_value_is_split_into_items(self):
        service = self._fake_service(results=[{'facts': [
            _valid_fact(
                field_key='ai_software', data_type='list', pillar='infrastructure_digital_capability',
                owner_role='lab_admin', value='TensorFlow; PyTorch; MATLAB',
            ),
        ]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Licensed AI software text.')]})
        self.assertEqual(facts[0]['value'], ['TensorFlow', 'PyTorch', 'MATLAB'])

    def test_unparseable_number_is_dropped_not_coerced(self):
        service = self._fake_service(results=[{'facts': [_valid_fact(value='approximately forty-two')]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        facts = extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})
        self.assertEqual(facts, [])

    # -- multiple pages / multiple chunks / duplicates -----------------------

    def test_facts_from_different_pages_in_one_chunk_are_both_kept(self):
        service = self._fake_service(results=[{'facts': [
            _valid_fact(field_key='total_faculty', source_page='1'),
            _valid_fact(
                field_key='student_strength', pillar='student_ai_readiness', owner_role='registrar',
                source_page='2', value='1200', source_snippet='Total student enrolment is 1200.',
            ),
        ]}])
        extractor = OpenAIFactExtractor(openai_service=service)
        pages = {'pages': [_page(1, 'Faculty section text.'), _page(2, 'Enrolment section text.')]}

        facts = extractor.extract_facts(self.document, pages)

        by_key = {f['field_key']: f for f in facts}
        self.assertEqual(by_key['total_faculty']['source_page'], '1')
        self.assertEqual(by_key['student_strength']['source_page'], '2')

    def test_large_document_is_split_into_multiple_chunks(self):
        pages = {'pages': [_page(i, f'Page {i} content. ' * 10) for i in range(1, 4)]}
        service = self._fake_service(results=[{'facts': []}, {'facts': []}, {'facts': []}])
        # A tiny max_chunk_chars forces one page per chunk.
        extractor = OpenAIFactExtractor(openai_service=service, max_chunk_chars=50)

        extractor.extract_facts(self.document, pages)

        self.assertEqual(service.extract_structured_data.call_count, 3)
        first_call_content = service.extract_structured_data.call_args_list[0].kwargs['user_content']
        self.assertIn('chunk 1 of 3', first_call_content)

    def test_duplicate_facts_across_chunks_keep_the_strongest_evidence(self):
        pages = {'pages': [_page(i, f'Page {i} content. ' * 10) for i in range(1, 3)]}
        service = self._fake_service(results=[
            {'facts': [_valid_fact(source_page='1', confidence_score=0.6, source_snippet='Weaker mention.')]},
            {'facts': [_valid_fact(source_page='2', confidence_score=0.95, source_snippet='Clear, explicit statement.')]},
        ])
        extractor = OpenAIFactExtractor(openai_service=service, max_chunk_chars=50)

        facts = extractor.extract_facts(self.document, pages)

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['confidence_score'], 0.95)
        self.assertEqual(facts[0]['source_page'], '2')

    def test_too_many_chunks_are_capped_not_unbounded(self):
        pages = {'pages': [_page(i, f'Page {i} content. ' * 10) for i in range(1, 6)]}
        service = self._fake_service(results=[{'facts': []}] * 10)
        extractor = OpenAIFactExtractor(openai_service=service, max_chunk_chars=50, max_chunks=2)

        extractor.extract_facts(self.document, pages)

        self.assertEqual(service.extract_structured_data.call_count, 2)

    # -- OpenAI failure handling ----------------------------------------------

    def test_recoverable_error_on_a_chunk_propagates(self):
        service = self._fake_service(side_effect=RecoverableExtractionError('rate limited'))
        extractor = OpenAIFactExtractor(openai_service=service)
        with self.assertRaises(RecoverableExtractionError):
            extractor.extract_facts(self.document, {'pages': [_page(1, 'Some real page text here.')]})

    def test_permanent_error_on_one_chunk_does_not_block_the_others(self):
        pages = {'pages': [_page(i, f'Page {i} content. ' * 10) for i in range(1, 3)]}
        service = self._fake_service(side_effect=[
            PermanentExtractionError('malformed response for this chunk'),
            {'facts': [_valid_fact(source_page='2')]},
        ])
        extractor = OpenAIFactExtractor(openai_service=service, max_chunk_chars=50)

        facts = extractor.extract_facts(self.document, pages)

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]['source_page'], '2')


@unittest.skipUnless(
    settings.RUN_OPENAI_INTEGRATION_TESTS,
    'Set RUN_OPENAI_INTEGRATION_TESTS=true (and a real OPENAI_API_KEY) to run this against the real API.',
)
class OpenAIFactExtractorIntegrationTests(TestCase):
    """Opt-in only -- makes a real call to the real OpenAI API against a
    real PDF, spending real quota. Never runs as part of a normal
    `manage.py test`; see the skip condition above."""

    def test_real_extraction_against_a_real_pdf(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        document = Document.objects.create(
            sprint=sprint, document_type='naac_ssr', original_filename='ssr.pdf',
            mime_type='application/pdf', status=Document.Status.UPLOADED,
        )
        pages = {'pages': [_page(1, (
            'AIOS Institute of Technology — Self Study Report\n'
            'The institution has 128 full-time faculty members, of whom 34 hold an AI/ML '
            'certification recognized by AICTE. Total student enrolment for AY 2025-26 is 2,450. '
            'The placement cell reported an 82% placement rate for the graduating batch, with 47 '
            'signed industry MoUs including partnerships with three AI research labs.'
        ))]}

        extractor = OpenAIFactExtractor()  # real OpenAIExtractionService, real API key from settings
        facts = extractor.extract_facts(document, pages)

        self.assertTrue(facts, 'Expected the real API to extract at least one fact from clearly-stated content.')
        for fact in facts:
            self.assertTrue(fact['source_snippet'])
            self.assertTrue(0.0 <= fact['confidence_score'] <= 1.0)


class RuleBasedGapDetectorTests(TestCase):
    """Unit tests for the real, deterministic GapDetector (apps.extraction.
    services.gap_detector). No AI involved -- nothing here is mocked."""

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.document = Document.objects.create(
            sprint=self.sprint, document_type='naac_ssr', original_filename='ssr.pdf',
            mime_type='application/pdf', status=Document.Status.PROCESSED, uploaded_at=timezone.now(),
        )
        self.detector = RuleBasedGapDetector()

    def _make_fact(self, **overrides):
        defaults = {
            'sprint': self.sprint, 'document': self.document, 'source_document': self.document,
            'field_name': 'Total Faculty Count', 'field_key': 'total_faculty', 'value': 42,
            'normalized_value': 42, 'data_type': ExtractedFact.DataType.NUMBER,
            'pillar': 'faculty_ai_capability', 'owner_role': 'hr_officer',
            'source_snippet': '42 faculty members.', 'confidence_score': 0.9,
            'extraction_method': 'openai', 'status': ExtractedFact.Status.EXTRACTED,
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    def test_low_confidence_fact_yields_low_confidence_gap(self):
        fact = self._make_fact(confidence_score=0.3)
        gaps = self.detector.detect_gaps(self.document, [])
        low_conf = [g for g in gaps if g['gap_type'] == GapItem.GapType.LOW_CONFIDENCE]
        self.assertEqual(len(low_conf), 1)
        self.assertEqual(low_conf[0]['source_fact'], fact)
        self.assertEqual(low_conf[0]['priority'], GapItem.Priority.HIGH)  # below the "very low" threshold

    def test_moderately_low_confidence_is_medium_priority(self):
        self._make_fact(confidence_score=0.6)
        gaps = self.detector.detect_gaps(self.document, [])
        low_conf = [g for g in gaps if g['gap_type'] == GapItem.GapType.LOW_CONFIDENCE]
        self.assertEqual(low_conf[0]['priority'], GapItem.Priority.MEDIUM)

    def test_high_confidence_fact_yields_unconfirmed_fact_gap(self):
        fact = self._make_fact(confidence_score=0.95)
        gaps = self.detector.detect_gaps(self.document, [])
        unconfirmed = [g for g in gaps if g['gap_type'] == GapItem.GapType.UNCONFIRMED_FACT]
        self.assertEqual(len(unconfirmed), 1)
        self.assertEqual(unconfirmed[0]['source_fact'], fact)

    def test_confirmed_fact_yields_no_gap(self):
        self._make_fact(confidence_score=0.95, status=ExtractedFact.Status.CONFIRMED)
        gaps = self.detector.detect_gaps(self.document, [])
        self.assertEqual(gaps, [])

    def test_stale_document_yields_stale_data_gap(self):
        self.document.uploaded_at = timezone.now() - timedelta(days=settings.GAP_STALE_DATA_DAYS + 1)
        self.document.save(update_fields=['uploaded_at'])
        gaps = self.detector.detect_gaps(self.document, [])
        stale = [g for g in gaps if g['gap_type'] == GapItem.GapType.STALE_DATA]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]['related_document'], self.document)

    def test_recent_document_yields_no_stale_gap(self):
        gaps = self.detector.detect_gaps(self.document, [])
        self.assertEqual([g for g in gaps if g['gap_type'] == GapItem.GapType.STALE_DATA], [])

    def test_document_with_no_uploaded_at_yields_no_stale_gap(self):
        self.document.uploaded_at = None
        self.document.save(update_fields=['uploaded_at'])
        gaps = self.detector.detect_gaps(self.document, [])
        self.assertEqual([g for g in gaps if g['gap_type'] == GapItem.GapType.STALE_DATA], [])

    def test_never_detects_missing_document(self):
        """Deliberate scope boundary -- see gap_detector.py's module
        docstring for why missing_document stays a sprint-level concern
        rather than something this per-document detector attempts."""
        gaps = self.detector.detect_gaps(self.document, [])
        self.assertFalse(any(g['gap_type'] == GapItem.GapType.MISSING_DOCUMENT for g in gaps))


class OpenAIConflictCheckerTests(TestCase):
    """Unit tests for the real, OpenAI-backed ConflictChecker (apps.
    extraction.services.conflict_checker). The OpenAI service is always a
    fake double here -- never a real network call."""

    def setUp(self):
        institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.document_a = Document.objects.create(
            sprint=self.sprint, document_type='naac_ssr', original_filename='a.pdf',
            mime_type='application/pdf', status=Document.Status.PROCESSED,
        )
        self.document_b = Document.objects.create(
            sprint=self.sprint, document_type='aqar_report', original_filename='b.pdf',
            mime_type='application/pdf', status=Document.Status.PROCESSED,
        )

    def _make_fact(self, document, **overrides):
        defaults = {
            'sprint': self.sprint, 'document': document, 'source_document': document,
            'field_name': 'Total Faculty Count', 'field_key': 'total_faculty', 'value': 42,
            'normalized_value': 42, 'data_type': ExtractedFact.DataType.NUMBER,
            'pillar': 'faculty_ai_capability', 'owner_role': 'hr_officer',
            'source_snippet': '42 faculty members.', 'confidence_score': 0.9,
            'extraction_method': 'openai', 'status': ExtractedFact.Status.EXTRACTED,
        }
        defaults.update(overrides)
        return ExtractedFact.objects.create(**defaults)

    @staticmethod
    def _fake_service(results=None, side_effect=None):
        service = MagicMock()
        if side_effect is not None:
            service.extract_structured_data.side_effect = side_effect
        elif results is not None:
            service.extract_structured_data.side_effect = results
        return service

    def test_no_other_documents_never_calls_openai(self):
        self._make_fact(self.document_a)
        service = self._fake_service(results=[])
        checker = OpenAIConflictChecker(openai_service=service)
        conflicts = checker.check_conflicts(self.document_a, [])
        self.assertEqual(conflicts, [])
        service.extract_structured_data.assert_not_called()

    def test_matching_normalized_values_are_not_candidates(self):
        """The deterministic pre-filter: two facts that genuinely agree
        never reach the AI at all."""
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=42, normalized_value=42)
        service = self._fake_service(results=[])
        checker = OpenAIConflictChecker(openai_service=service)
        conflicts = checker.check_conflicts(self.document_a, [])
        self.assertEqual(conflicts, [])
        service.extract_structured_data.assert_not_called()

    def test_confirmed_semantic_conflict_creates_a_conflict_dict(self):
        fact_a = self._make_fact(self.document_a, value=42, normalized_value=42)
        fact_b = self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(results=[
            {'is_conflict': True, 'confidence': 0.88, 'explanation': 'Both describe total faculty headcount.'},
        ])
        checker = OpenAIConflictChecker(openai_service=service)

        conflicts = checker.check_conflicts(self.document_a, [])

        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertEqual(conflict['gap_type'], GapItem.GapType.CONFLICT)
        self.assertEqual(conflict['source_fact'], fact_a)
        self.assertEqual(conflict['conflict_fact_b'], fact_b)
        self.assertEqual(conflict['conflict_value_a'], 42)
        self.assertEqual(conflict['conflict_value_b'], 47)
        self.assertEqual(conflict['conflict_confidence'], 0.88)
        self.assertIn('faculty headcount', conflict['description'])

    def test_semantic_non_conflict_creates_nothing(self):
        """The AI can determine the two values don't actually conflict
        (different populations) -- no gap, and neither fact's own value is
        touched (never 'silently resolved')."""
        fact_a = self._make_fact(self.document_a, value=42, normalized_value=42)
        fact_b = self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(results=[{
            'is_conflict': False, 'confidence': 0.7,
            'explanation': 'One covers the CS department only, the other the whole institution.',
        }])
        checker = OpenAIConflictChecker(openai_service=service)

        conflicts = checker.check_conflicts(self.document_a, [])

        self.assertEqual(conflicts, [])
        fact_a.refresh_from_db()
        fact_b.refresh_from_db()
        self.assertEqual(fact_a.value, 42)
        self.assertEqual(fact_b.value, 47)

    def test_invalid_is_conflict_type_is_dropped(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(results=[{'is_conflict': 'yes', 'confidence': 0.8, 'explanation': 'x'}])
        checker = OpenAIConflictChecker(openai_service=service)
        self.assertEqual(checker.check_conflicts(self.document_a, []), [])

    def test_confidence_out_of_range_is_dropped(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(results=[{'is_conflict': True, 'confidence': 1.4, 'explanation': 'x'}])
        checker = OpenAIConflictChecker(openai_service=service)
        self.assertEqual(checker.check_conflicts(self.document_a, []), [])

    def test_empty_explanation_is_dropped(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(results=[{'is_conflict': True, 'confidence': 0.8, 'explanation': '   '}])
        checker = OpenAIConflictChecker(openai_service=service)
        self.assertEqual(checker.check_conflicts(self.document_a, []), [])

    def test_rejected_facts_excluded_from_candidates(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47, status=ExtractedFact.Status.REJECTED)
        service = self._fake_service(results=[])
        checker = OpenAIConflictChecker(openai_service=service)
        conflicts = checker.check_conflicts(self.document_a, [])
        self.assertEqual(conflicts, [])
        service.extract_structured_data.assert_not_called()

    def test_recoverable_error_propagates(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47)
        service = self._fake_service(side_effect=RecoverableExtractionError('rate limited'))
        checker = OpenAIConflictChecker(openai_service=service)
        with self.assertRaises(RecoverableExtractionError):
            checker.check_conflicts(self.document_a, [])

    def test_permanent_error_on_one_pair_does_not_block_others(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        self._make_fact(self.document_b, value=47, normalized_value=47)
        document_c = Document.objects.create(
            sprint=self.sprint, document_type='placement_report', original_filename='c.pdf',
            mime_type='application/pdf', status=Document.Status.PROCESSED,
        )
        self._make_fact(document_c, value=50, normalized_value=50)
        service = self._fake_service(side_effect=[
            PermanentExtractionError('malformed response'),
            {'is_conflict': True, 'confidence': 0.9, 'explanation': 'Genuinely disagree.'},
        ])
        checker = OpenAIConflictChecker(openai_service=service)

        conflicts = checker.check_conflicts(self.document_a, [])

        self.assertEqual(len(conflicts), 1)

    def test_too_many_pairs_are_capped(self):
        self._make_fact(self.document_a, value=42, normalized_value=42)
        for i in range(5):
            doc = Document.objects.create(
                sprint=self.sprint, document_type='placement_report', original_filename=f'extra{i}.pdf',
                mime_type='application/pdf', status=Document.Status.PROCESSED,
            )
            self._make_fact(doc, value=100 + i, normalized_value=100 + i)
        service = self._fake_service(results=[{'is_conflict': False, 'confidence': 0.5, 'explanation': 'x'}] * 10)
        checker = OpenAIConflictChecker(openai_service=service, max_pairs=2)

        checker.check_conflicts(self.document_a, [])

        self.assertEqual(service.extract_structured_data.call_count, 2)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class EndToEndGapAndConflictTests(ExtractionJobTestBase):
    """Proves the full documented flow -- PDF -> PageReader -> Classifier ->
    OpenAIFactExtractor -> AuditFieldMapper -> GapDetector -> ConflictChecker
    -> Review Workspace -- actually persists real GapItem rows, including a
    genuine cross-document conflict, rather than returning temporary
    results that never reach the database."""

    def setUp(self):
        super().setUp()
        self._auth(self.iqac)
        upload = self.client.post(
            f'/api/v1/sprints/{self.sprint.id}/upload-file/',
            {
                'file': make_pdf(name='doc2.pdf', page_texts=('A second, distinct document for conflict tests.',)),
                'document_type': 'aqar_report',
            },
            format='multipart',
        )
        self.document2 = Document.objects.get(id=upload.data['id'])
        self.client.credentials()

    def test_conflicting_facts_across_documents_are_persisted_as_a_conflict_gap(self):
        def fake_extract_facts(*, system_prompt, user_content, response_schema, schema_name='extraction_result', **kwargs):
            if 'doc2.pdf' in user_content:
                return {'facts': [_valid_fact(value='47', source_snippet='There are 47 teaching staff.')]}
            return {'facts': [_valid_fact(value='42', source_snippet='The institution has 42 faculty members.')]}

        self.fact_openai_mock.return_value.extract_structured_data.side_effect = fake_extract_facts

        conflict_patcher = patch('apps.extraction.services.conflict_checker.get_ai_service')
        mock_conflict_openai_cls = conflict_patcher.start()
        mock_conflict_openai_cls.return_value.extract_structured_data.return_value = {
            'is_conflict': True, 'confidence': 0.85,
            'explanation': 'Both figures describe the same total faculty headcount.',
        }
        self.addCleanup(conflict_patcher.stop)

        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')

        facts = list(ExtractedFact.objects.filter(sprint=self.sprint, field_key='total_faculty'))
        self.assertEqual(len(facts), 2)
        self.assertEqual({f.value for f in facts}, {42, 47})

        conflict = GapItem.objects.get(gap_type=GapItem.GapType.CONFLICT)
        self.assertEqual({conflict.conflict_value_a, conflict.conflict_value_b}, {42, 47})
        self.assertEqual(conflict.conflict_confidence, 0.85)
        self.assertIn('faculty headcount', conflict.description)
        self.assertEqual(conflict.status, GapItem.Status.OPEN)  # marked for human review, not auto-resolved

    def test_matching_facts_across_documents_create_no_conflict(self):
        self.fact_openai_mock.return_value.extract_structured_data.return_value = {
            'facts': [_valid_fact(value='42')],
        }
        conflict_patcher = patch('apps.extraction.services.conflict_checker.get_ai_service')
        mock_conflict_openai_cls = conflict_patcher.start()
        self.addCleanup(conflict_patcher.stop)

        self._auth(self.iqac)
        self.client.post(f'/api/v1/sprints/{self.sprint.id}/extraction-jobs/')

        self.assertEqual(GapItem.objects.filter(gap_type=GapItem.GapType.CONFLICT).count(), 0)
        mock_conflict_openai_cls.return_value.extract_structured_data.assert_not_called()
