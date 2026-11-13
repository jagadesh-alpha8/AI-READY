"""Second-layer background jobs (capability/second_layer_jobs.py): every model call metered against the run's shared
second-layer budget, one active job per run, nothing saved once a job is cancelled or out of budget."""
import json
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.extraction.exceptions import AIResponseError
from apps.extraction.services.openai_client import OpenAIExtractionService

from .capability import second_layer_jobs as jobs
from .capability.layer2_service import check_pending, document_sources, export_for_run
from .models import (AdditionalEvidence, CapabilityExecution, CapabilityRun, CapabilityRunEvent, DepthQuestion,
                     DepthResponse, SecondLayerBudget, SecondLayerJob)

JOBS = 'apps.scoring.capability.second_layer_jobs'
QUOTE = 'Current institutional evidence for every faculty and student in 2025-26.'


@override_settings(SECURE_SSL_REDIRECT=False, SECOND_LAYER_JOBS_ENABLED=True, CAPABILITY_ASSESSMENT_ENABLED=True,
                   CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
                   CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single',
                   AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42, SECOND_LAYER_MAX_HTTP_CALLS=None,
                   SECOND_LAYER_MAX_COST_USD=None, AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class SecondLayerJobTests(APITestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        from apps.institutions.models import Institution
        from apps.sprints.models import Sprint
        self.institution = Institution.objects.create(name='College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.user = User.objects.create_user(username='coordinator', email='coord@example.com',
                                             role=User.Role.IQAC_COORDINATOR, institution=self.institution)
        self.client.force_authenticate(self.user)
        self.doc = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='processed')
        self.page = DocumentPage.objects.create(document=self.doc, page_number=1, text=QUOTE)
        base = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
        with patch('apps.scoring.capability.execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                started = self.client.post(base, {'population': 'All', 'reference_period': '2025-26'},
                                           format='json', HTTP_IDEMPOTENCY_KEY='provisional')
        self.assertEqual(started.status_code, 202, started.data)
        self.run = CapabilityRun.objects.get(pk=started.data['id'])
        CapabilityExecution.objects.filter(run=self.run).update(status='completed')
        self.url = f'{base}/{self.run.pk}'
        self.rubric = self.run.inputs['rubric']
        self.credited = [c['id'] for c in self.rubric['indicators'][0]['conditions'][:2]]
        records = [{'condition_id': c['id'], 'state': 'met' if c['id'] in self.credited else 'not_met',
                    'credit': 1.0 if c['id'] in self.credited else 0,
                    'citations': [{'source_id': str(self.page.pk), 'quote': QUOTE}] if c['id'] in self.credited else []}
                   for i in self.rubric['indicators'] for c in i['conditions']]
        CapabilityRunEvent.objects.create(run=self.run, state='completed', payload={
            'result': {'score': 1}, 'records': records, 'traces': [], 'inference': {'provider': 'none'}})
        self.sdk = MagicMock()
        self.sdk.with_options.return_value = self.sdk
        self.sdk.chat.completions.create.side_effect = self.reply
        self.on_call = None

    # ---------------------------------------------------------------- helpers

    def reply(self, **kwargs):
        payload = json.loads(kwargs['messages'][1]['content'])
        if self.on_call:
            self.on_call()
        if 'max_questions' in payload:
            ids = [d['id'] for d in payload['dimensions']]
            content = {'dimensions': [{'dimension_id': i, 'answered_by_evidence': False, 'evidence_quote': ''}
                                      for i in ids],
                       'questions': [{'dimension_ids': ids[:1], 'text': 'How many hours did the programme run?'}]}
        else:
            content = {'unexpected': True}
        return SimpleNamespace(model='actual-test-model',
                               usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150, prompt_tokens_details=None,
                                                     completion_tokens_details=None, total_tokens=350),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                                   content=json.dumps(content), refusal=None))])

    def post_job(self, operation, key='job-1', options=None, expect=202):
        body = {'operation': operation} if options is None else {'operation': operation, 'options': options}
        with patch(f'{JOBS}.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(f'{self.url}/second-layer/jobs', body, format='json',
                                            HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, expect, response.data)
        if expect == 202:
            send.assert_called_once()
            return SecondLayerJob.objects.get(pk=response.data['id'])
        return response

    def execute(self, job):
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)
        with patch(f'{JOBS}.get_ai_service', return_value=service), patch(f'{JOBS}.get_router_pool', return_value=None):
            with self.captureOnCommitCallbacks(execute=False):
                jobs.run_second_layer_job.run(str(job.pk), str(job.task_id))
        job.refresh_from_db()
        return job

    def calls(self):
        return self.sdk.chat.completions.create.call_count

    # ---------------------------------------------------------------- questions

    def test_questions_job_is_metered_against_the_run_budget_and_saves_the_questions(self):
        from apps.extraction.models import AIUsage
        job = self.execute(self.post_job('questions'))
        self.assertEqual(job.status, 'completed', job.detail)
        self.assertEqual(self.calls(), 2)   # one per credited condition
        budget = SecondLayerBudget.objects.get(run=self.run)
        self.assertEqual((job.requests_reserved, budget.requests_reserved), (2, 2))
        self.assertEqual(budget.max_http_calls, 72)   # the run's own assessment limit, settings unset
        self.assertGreater(budget.usd_reserved, 0)
        depth_questions = DepthQuestion.objects.filter(run_ref=str(self.run.pk), kind='depth')
        self.assertEqual(depth_questions.count(), 2)
        self.assertEqual(job.result['questions'], DepthQuestion.objects.filter(run_ref=str(self.run.pk)).count())
        kinds = list(job.events.values_list('payload__kind', flat=True))
        self.assertEqual(kinds.count('request_reserved'), 2)
        self.assertEqual(kinds[-1], 'terminal')
        self.assertTrue(AIUsage.objects.filter(capability_run=self.run, stage='capability_second_layer').exists())
        shown = self.client.get(f'{self.url}/second-layer/jobs')
        self.assertEqual(shown.data['budget']['requests_reserved'], 2)
        self.assertEqual(shown.data['results'][0]['status'], 'completed')
        # Planning again is refused unless replace is asked for.
        self.post_job('questions', key='job-2', expect=400)

    @override_settings(SECOND_LAYER_MAX_HTTP_CALLS=1)
    def test_a_spent_budget_saves_nothing_and_a_raised_budget_is_shared_across_jobs(self):
        job = self.execute(self.post_job('questions'))
        self.assertEqual((job.status, job.error_code), ('failed', 'budget_exhausted'))
        self.assertFalse(DepthQuestion.objects.filter(run_ref=str(self.run.pk)).exists())
        self.assertEqual(self.calls(), 1)
        out = StringIO()
        call_command('layer2_budget', str(self.run.pk), '--max-calls', '5', stdout=out)
        self.assertIn('Requests: 1 of 5', out.getvalue())
        second = self.execute(self.post_job('questions', key='job-2'))
        self.assertEqual(second.status, 'completed', second.detail)
        self.assertEqual(SecondLayerBudget.objects.get(run=self.run).requests_reserved, 3)
        with self.assertRaises(Exception):
            call_command('layer2_budget', str(self.run.pk), '--max-calls', '2', stdout=StringIO())

    def test_cancelling_during_the_calls_saves_nothing(self):
        job = self.post_job('questions')
        self.on_call = lambda: self.calls() == 2 and jobs.finish(job.pk, 'cancelled', 'cancelled_by_user')
        job = self.execute(job)
        self.assertEqual(job.status, 'cancelled')
        self.assertFalse(DepthQuestion.objects.filter(run_ref=str(self.run.pk)).exists())
        self.assertEqual(self.calls(), 2)

    def test_one_active_job_per_run_and_idempotent_keys(self):
        job = self.post_job('questions')
        again = self.client.post(f'{self.url}/second-layer/jobs', {'operation': 'questions'}, format='json',
                                 HTTP_IDEMPOTENCY_KEY='job-1')
        self.assertEqual((again.status_code, again.data['id'], again.data['reused']), (200, str(job.pk), True))
        changed = self.client.post(f'{self.url}/second-layer/jobs', {'operation': 'questions',
                                   'options': {'replace': True}}, format='json', HTTP_IDEMPOTENCY_KEY='job-1')
        self.assertEqual(changed.status_code, 409)
        other = self.client.post(f'{self.url}/second-layer/jobs', {'operation': 'depth'}, format='json',
                                 HTTP_IDEMPOTENCY_KEY='job-2')
        self.assertEqual(other.status_code, 409)
        bad = self.client.post(f'{self.url}/second-layer/jobs', {'operation': 'questions', 'options': {'publish': 1}},
                               format='json', HTTP_IDEMPOTENCY_KEY='job-3')
        self.assertEqual(bad.status_code, 400)
        cancelled = self.client.post(f'{self.url}/second-layer/jobs/{job.pk}/cancel')
        self.assertEqual((cancelled.status_code, cancelled.data['status'], cancelled.data['changed']),
                         (200, 'cancelled', True))
        self.execute(job)   # the queued message arrives after the cancel: nothing runs
        self.assertEqual(self.calls(), 0)

    def test_refusals(self):
        with override_settings(SECOND_LAYER_JOBS_ENABLED=False):
            self.post_job('questions', expect=503)
        self.post_job('depth', expect=400)        # no questions yet
        self.post_job('checks', expect=400)       # nothing waiting
        self.post_job('everything', expect=400)
        final = CapabilityRun.objects.create(sprint=self.sprint, inputs={**self.run.inputs, 'second_layer': {
            'provisional_run_id': str(self.run.pk)}}, inputs_hash='x')
        with self.assertRaises(Exception):
            jobs.start(run=final, operation='questions', user=None, key='final')

    def test_a_job_whose_worker_was_lost_is_expired_when_the_next_starts(self):
        job = self.post_job('questions')
        SecondLayerJob.objects.filter(pk=job.pk).update(status='running', created_at=timezone.now() - timedelta(days=2),
                                                        started_at=timezone.now() - timedelta(days=1))
        second = self.post_job('questions', key='job-2')
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ('failed', 'worker_lost'))
        self.assertEqual(second.status, 'queued')
        # A job that waited long in the queue but started recently is not taken for lost.
        SecondLayerJob.objects.filter(pk=second.pk).update(status='running',
                                                           created_at=timezone.now() - timedelta(days=1),
                                                           started_at=timezone.now())
        self.post_job('questions', key='job-3', expect=409)

    def test_another_college_cannot_see_or_start_jobs(self):
        from apps.accounts.models import User
        from apps.institutions.models import Institution
        other = Institution.objects.create(name='Other')
        stranger = User.objects.create_user(username='stranger', email='s@example.com',
                                            role=User.Role.IQAC_COORDINATOR, institution=other)
        job = self.post_job('questions')
        self.client.force_authenticate(stranger)
        for response in (self.client.get(f'{self.url}/second-layer/jobs'),
                         self.client.get(f'{self.url}/second-layer/jobs/{job.pk}'),
                         self.client.post(f'{self.url}/second-layer/jobs/{job.pk}/cancel'),
                         self.client.post(f'{self.url}/second-layer/jobs', {'operation': 'questions'}, format='json',
                                          HTTP_IDEMPOTENCY_KEY='stranger')):
            self.assertIn(response.status_code, (403, 404))
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')

    # ---------------------------------------------------------------- checks

    def missing_question(self, rank=1):
        indicator = self.rubric['indicators'][1]
        return DepthQuestion.objects.create(run_ref=str(self.run.pk), kind='missing', indicator_code=indicator['code'],
                                            condition_ids=[indicator['conditions'][0]['id']], rank=rank,
                                            text='We found nothing for this. Do you have anything?', spec_version='t')

    def answer(self, question, key=None):
        with patch(f'{JOBS}.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                made = self.client.post(f'{self.url}/questions/{question.pk}/responses',
                                        {'answer': 'Our evidence register', 'document_ids': [str(self.doc.pk)]},
                                        format='json')
        self.assertEqual(made.status_code, 201, made.data)
        return DepthResponse.objects.get(pk=made.data['id']), send

    def test_a_submitted_answer_requests_a_checks_job(self):
        response, send = self.answer(self.missing_question())
        send.assert_called_once()
        job = SecondLayerJob.objects.get(run=self.run)
        self.assertEqual((job.operation, job.idempotency_key), ('checks', f'response-{response.pk}'))
        job = self.execute(job)
        self.assertEqual(job.status, 'completed', job.detail)
        response.refresh_from_db()
        self.assertEqual(response.status, 'checked')
        self.assertEqual((job.result['checked'], job.result['model_calls'], self.calls()), (1, 0, 0))
        self.assertIsNone(job.result['follow_on_job_id'])

    def test_an_answer_submitted_while_checks_run_gets_a_follow_on_job(self):
        response, _ = self.answer(self.missing_question())
        job = SecondLayerJob.objects.get(run=self.run)
        second_question = self.missing_question(rank=2)

        def submit_during(*args, **kwargs):
            counts = check_pending(*args, **kwargs)
            # Submitted after this job's scan: its own request for a check meets the active job, quietly refused.
            later, send = self.answer(second_question)
            send.assert_not_called()
            return counts
        with patch('apps.scoring.capability.layer2_service.check_pending', side_effect=submit_during):
            job = self.execute(job)
        self.assertEqual(job.status, 'completed', job.detail)
        follow_on = SecondLayerJob.objects.get(pk=job.result['follow_on_job_id'])
        self.assertEqual((follow_on.operation, follow_on.status), ('checks', 'queued'))
        follow_on = self.execute(follow_on)
        self.assertEqual(follow_on.status, 'completed')
        self.assertFalse(DepthResponse.objects.filter(question__run_ref=str(self.run.pk), status='pending').exists())

    def test_the_sweep_checks_answers_once_their_documents_are_extracted(self):
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        late = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='processing')
        question = self.missing_question()
        response = DepthResponse.objects.create(question=question, kind='answer', answer='See the register',
                                                document_ids=[str(late.pk)], status='pending')
        additional = AdditionalEvidence.objects.create(run_ref=str(self.run.pk), document_ids=[str(late.pk)],
                                                       picked=[self.rubric['indicators'][1]['code']],
                                                       routing={'indicators': [self.rubric['indicators'][1]['code']]})
        with patch(f'{JOBS}.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(jobs.sweep_second_layer_checks(), 0)   # still extracting
        DocumentPage.objects.create(document=late, page_number=1, text='Register of the evidence for 2025-26.')
        late.status = 'processed'
        late.save()
        with patch(f'{JOBS}.dispatch') as send:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(jobs.sweep_second_layer_checks(), 1)
                self.assertEqual(jobs.sweep_second_layer_checks(), 0)   # one active job per run
        send.assert_called_once()
        job = self.execute(SecondLayerJob.objects.get(run=self.run, operation='checks'))
        self.assertEqual(job.status, 'completed', job.detail)
        response.refresh_from_db()
        additional.refresh_from_db()
        self.assertEqual((response.status, additional.status, job.result['additional_checked']),
                         ('checked', 'checked', 1))
        with patch(f'{JOBS}.dispatch'):
            self.assertEqual(jobs.sweep_second_layer_checks(), 0)   # nothing left waiting

    def test_the_sweep_does_not_retry_an_item_it_already_tried(self):
        question = self.missing_question()
        DepthResponse.objects.create(question=question, kind='answer', answer='See the register',
                                     document_ids=[str(self.doc.pk)], status='pending')
        with patch(f'{JOBS}.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(jobs.sweep_second_layer_checks(), 1)
        job = SecondLayerJob.objects.get(run=self.run)
        with patch('apps.scoring.capability.layer2_service.check_response', side_effect=AIResponseError('bad')):
            job = self.execute(job)
        self.assertEqual((job.status, job.result['failed']), ('completed', 1))
        with patch(f'{JOBS}.dispatch'):
            self.assertEqual(jobs.sweep_second_layer_checks(), 0)

    def test_check_pending_skips_a_malformed_reply_and_checks_the_rest(self):
        first = DepthResponse.objects.create(question=self.missing_question(), kind='answer', answer='One',
                                             status='pending')
        second = DepthResponse.objects.create(question=self.missing_question(rank=2), kind='answer', answer='Two',
                                              status='pending')
        from .capability import layer2_service
        real = layer2_service.check_response

        def flaky(response, *args, **kwargs):
            if response.pk == first.pk:
                raise AIResponseError('malformed')
            return real(response, *args, **kwargs)
        with patch.object(layer2_service, 'check_response', side_effect=flaky):
            counts = check_pending(str(self.run.pk), model=None, ranker=None,
                                   skip_error=lambda exc: isinstance(exc, AIResponseError))
            self.assertEqual((counts['checked'], counts['failed']), (1, 1))
            with self.assertRaises(AIResponseError):
                check_pending(str(self.run.pk), model=None, ranker=None)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ('pending', 'checked'))

    def test_a_rejected_document_does_not_hold_an_answer(self):
        from apps.documents.models import Document
        rejected = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='rejected')
        sources, ready, failed = document_sources([str(rejected.pk)], self.sprint.pk)
        self.assertEqual((sources, ready, failed), ([], True, [str(rejected.pk)]))

    # ---------------------------------------------------------------- re-judge and publish

    def rejudge_result(self, export, service):
        """Stands in for rejudge_credit: one metered call, then a merged result raising the first condition."""
        service.extract_structured_data(system_prompt='s', user_content=json.dumps({'probe': True}),
                                        response_schema={'type': 'object'}, schema_name='probe')
        new_sources = document_sources([str(self.doc.pk)], self.sprint.pk)[0]
        records = [dict(r) for r in export['assessment']['records']]
        cid = self.rubric['indicators'][2]['conditions'][0]['id']
        code = self.rubric['indicators'][2]['code']
        for row in records:
            if row['condition_id'] == cid:
                row.update(credit=0.25, state='partly_met',
                           citations=[{'source_id': new_sources[0]['id'], 'quote': QUOTE}])
        trace = {'indicator': code, 'source_ids': [new_sources[0]['id']],
                 'source_excerpts': [{**new_sources[0], 'text_offset': 0}]}
        return {'run_ref': export['run_id'], 'records': records, 'traces': [trace], 'new_sources': new_sources,
                'provisional_score': 1, 'final_score': 1.1, 'targets': {code: [cid]}, 'merge': [],
                'contradictions': [], 'context_audit': {}, 'routes': 1, 'note': ''}

    def test_rejudge_job_publishes_the_final_result_with_its_metered_calls(self):
        job = self.post_job('rejudge')
        with patch('apps.scoring.capability.layer2_service.rejudge_credit',
                   side_effect=lambda export, service, **kw: self.rejudge_result(export, service)) as fake:
            job = self.execute(job)
        self.assertEqual(job.status, 'completed', job.detail)
        self.assertTrue(fake.call_args.kwargs['evaluate_options']['strict_errors'])
        self.assertIsNotNone(job.final_run_id)
        final = job.final_run
        self.assertEqual(final.inputs['refines_run_id'], str(self.run.pk))
        inference = final.events.filter(state='completed').last().payload['inference']
        self.assertTrue(inference['second_layer_metered'])
        self.assertTrue(any(c.get('kind') == 'request_reserved' for c in inference['calls']))
        self.assertEqual(job.result['final_run_id'], str(final.pk))
        self.assertEqual(SecondLayerBudget.objects.get(run=self.run).requests_reserved, 1)
        # A final run takes no jobs of its own.
        with self.assertRaises(Exception):
            jobs.start(run=final, operation='checks', user=None, key='on-final')

    def test_rejudge_without_publishing_reports_only(self):
        job = self.post_job('rejudge', options={'publish': False})
        with patch('apps.scoring.capability.layer2_service.rejudge_credit',
                   side_effect=lambda export, service, **kw: self.rejudge_result(export, service)):
            job = self.execute(job)
        self.assertEqual(job.status, 'completed', job.detail)
        self.assertIsNone(job.final_run_id)
        self.assertEqual(job.result['final_score'], 1.1)
        self.assertEqual(CapabilityRun.objects.filter(inputs__second_layer__isnull=False).count(), 0)

    def test_rejudge_with_no_new_evidence_publishes_nothing_and_makes_no_call(self):
        job = self.execute(self.post_job('rejudge'))
        self.assertEqual(job.status, 'completed', job.detail)
        self.assertIsNone(job.final_run_id)
        self.assertEqual(self.calls(), 0)
        self.assertEqual(job.result['note'], 'No new evidence to re-judge.')

    def test_export_still_reads_the_provisional_run(self):
        self.assertEqual(export_for_run(self.run.pk)['run_id'], str(self.run.pk))
