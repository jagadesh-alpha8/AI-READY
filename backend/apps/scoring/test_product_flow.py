"""The whole product flow offline, through the API and the Celery tasks, with a stand-in model.

One college: documents, the assessment (part judgment, two passes), the provisional report and recommendations, then
the second layer as background jobs (questions, the college's answers with new documents, a skip, additional
evidence, checks, depth, the credit re-judgment) and the final run, with every report, recommendations and the plan
baseline on it. The stand-in model answers each request in the shape its schema asks for and only cites text it was
sent, so citations survive publication's revalidation. No network, no embedding model.
"""
import contextlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APITestCase, APITransactionTestCase

from apps.extraction.models import AIUsage
from apps.extraction.services.openai_client import OpenAIExtractionService

from .capability import second_layer_jobs as jobs
from .capability.engine import release
from .models import (CapabilityExecution, CapabilityRun, DepthJudgment, DepthQuestion, DepthResponse,
                     RecommendationExecution, SecondLayerBudget, SecondLayerJob)
from .tasks import run_capability_assessment

JOBS = 'apps.scoring.capability.second_layer_jobs'
NEW = 'NEWEVIDENCE'
PAGES = [
    'The institution approved an Artificial Intelligence and Machine Learning policy in 2024-25, owned by the IQAC '
    'coordinator, covering teaching, research and administration for all faculty and students.',
    'Faculty development: 120 faculty completed a five-day workshop on generative AI in teaching in 2024-25, with '
    'attendance registers and feedback forms kept by the Centre for Teaching Excellence.',
    'The computing centre provides a GPU cluster and licensed AI tools to every department; usage logs are reviewed '
    'each semester by the IT committee for the 2024-25 academic year.',
]
ATTACHMENT = (f'{NEW} Certificate register 2024-25: 85 of 120 faculty completed the 40-hour accredited AI '
              'programme run with the state university; hours, provider accreditation and completion are recorded.')
ADDITIONAL = (f'{NEW} Board minutes 2024-25: the college adopted an AI research ethics review procedure, with a named '
              'committee, approval records and an annual review of every AI research project.')
SETTINGS = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_JUDGMENT='parts',
                CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=108,
                CAPABILITY_MAX_COST_USD='20', CAPABILITY_OUTPUT_TOKENS=3000, CAPABILITY_REQUEST_TIMEOUT_SECONDS=60,
                CAPABILITY_RECOMMENDATIONS_ENABLED=True, SECOND_LAYER_JOBS_ENABLED=True,
                SECOND_LAYER_MAX_HTTP_CALLS=None, SECOND_LAYER_MAX_COST_USD=None, AI_RATE_LIMIT_ENABLED=False,
                AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
                AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')


@override_settings(**SETTINGS)
class ProductFlowTests(APITestCase):
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
        ssr = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', status='processed')
        for n, text in enumerate(PAGES, 1):
            DocumentPage.objects.create(document=ssr, page_number=n, text=text)
        self.base = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
        codes = [i['code'] for i in release()['indicators']]
        self.credited = set(codes[:6])   # the stand-in credits these key indicators in the first assessment
        self.sdk = MagicMock()
        self.sdk.with_options.return_value = self.sdk
        self.sdk.chat.completions.create.side_effect = self.model
        self.schemas = []
        self.queued = []

    # ---------------------------------------------------------------- the stand-in model

    def model(self, **kwargs):
        name = kwargs['response_format']['json_schema']['name']
        payload = json.loads(kwargs['messages'][1]['content'])
        self.schemas.append(name)
        body = getattr(self, 'reply_' + name)(payload)
        return SimpleNamespace(model='actual-test-model',
                               usage=SimpleNamespace(prompt_tokens=400, completion_tokens=200, prompt_tokens_details=None,
                                                     completion_tokens_details=None, total_tokens=600),
                               choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                                   content=json.dumps(body), refusal=None))])

    def reply_capability_parts(self, payload):
        windows = [s for s in payload['sources'] if len(s['text']) > 60]
        new = [s for s in windows if NEW in s['text']]
        credited = payload['indicator']['code'] in self.credited
        rows = {}
        for condition in payload['indicator']['conditions']:
            findings = []
            for part in condition['parts']:
                cite = new[0] if new else (windows[0] if credited and windows else None)
                findings.append({'part_id': part['id'], 'finding': 'full' if cite else 'not_found',
                                 'citations': [{'source_id': cite['id'], 'quote': cite['text'][:80]}] if cite else []})
            rows[condition['id']] = {'reason': 'Stand-in.', 'scope_supported': True, 'period_supported': True,
                                     'findings': findings}
        return {'conditions': rows}

    def reply_capability_advice(self, payload):
        return {'advice': [{'condition_id': a['id'], 'operation': a['operation'],
                            'steps': ['Build on the existing records for ' + a['requirement']],
                            'suggested_role': 'IQAC coordinator (suggested)', 'effort': 'unknown', 'dependencies': [],
                            'completion_evidence': 'Verify ' + str(a['completion_evidence']),
                            'basis': a.get('citations', [])} for a in payload['actions']]}

    def reply_depth_questions(self, payload):
        ids = [d['id'] for d in payload['dimensions']]
        return {'dimensions': [{'dimension_id': i, 'answered_by_evidence': False, 'evidence_quote': ''} for i in ids],
                'questions': [{'dimension_ids': ids[:2], 'text': 'How many hours did the programme run, and who '
                                                                  'accredited it? Please attach the register.'}]}

    def reply_answer_check(self, payload):
        attached = [p['id'] for p in payload['passages'] if NEW in p['text']]
        return {'dimensions': [{'dimension_id': d['id'], 'support': 'supported' if attached else 'not_supported',
                                'passage_ids': attached[:1], 'note': 'Stand-in.'} for d in payload['dimensions']],
                'follow_up': ''}

    def reply_depth_judgment(self, payload):
        ids = [d['id'] for d in payload.get('dimensions') or []]
        return {'level': 'substantiated', 'contradicts_evidence': False, 'relies_on_unsupported': False,
                'dimension_findings': [{'dimension_id': i, 'finding': 'Shown by the register.'} for i in ids],
                'reason': 'Stand-in.'}

    # ---------------------------------------------------------------- helpers

    def service(self):
        return OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)

    def assess(self):
        with patch('apps.scoring.capability.execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                started = self.client.post(self.base, {'population': 'All faculty and students',
                                                       'reference_period': '2024-25'}, format='json',
                                           HTTP_IDEMPOTENCY_KEY='provisional')
        self.assertEqual(started.status_code, 202, started.data)
        execution = CapabilityExecution.objects.get(run_id=started.data['id'])
        with patch('apps.scoring.tasks.get_ai_service', return_value=self.service()), patch(
                'apps.scoring.tasks.get_router_pool', return_value=None):
            run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        return execution.run

    def post(self, url, body, key=None, expect=None):
        headers = {'HTTP_IDEMPOTENCY_KEY': key} if key else {}
        with patch(f'{JOBS}.dispatch', side_effect=lambda job_id, task_id: self.queued.append(job_id)):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, body, format='json', **headers)
        if expect is not None:
            self.assertEqual(response.status_code, expect, response.data)
        return response

    def run_queued(self):
        """Run every dispatched second-layer job, including follow-ons, in order."""
        done = []
        while self.queued:
            job = SecondLayerJob.objects.get(pk=self.queued.pop(0))
            with patch(f'{JOBS}.get_ai_service', return_value=self.service()), patch(
                    f'{JOBS}.get_router_pool', return_value=None), patch(
                    f'{JOBS}.dispatch', side_effect=lambda job_id, task_id: self.queued.append(job_id)):
                with self.captureOnCommitCallbacks(execute=True):
                    jobs.run_second_layer_job.run(str(job.pk), str(job.task_id))
            job.refresh_from_db()
            self.assertEqual(job.status, 'completed', (job.operation, job.error_code, job.detail))
            done.append(job)
        return done

    def document(self, text):
        from apps.documents.models import Document
        from apps.extraction.models import DocumentPage
        doc = Document.objects.create(sprint=self.sprint, document_type='other', status='processed')
        DocumentPage.objects.create(document=doc, page_number=1, text=text)
        return str(doc.pk)

    def reports(self, run):
        for audience in ('leadership', 'evidence'):
            for fmt in ('html', 'pdf', 'json'):
                response = self.client.get(f'{self.base}/{run.pk}/report', {'audience': audience, 'file': fmt})
                self.assertEqual(response.status_code, 200, (audience, fmt))
        return json.loads(self.client.get(f'{self.base}/{run.pk}/report', {'file': 'json'}).content)

    def recommend(self, run, key):
        with patch('apps.scoring.capability.recommendation_execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                started = self.client.post(f'{self.base}/{run.pk}/recommendations', {}, format='json',
                                           HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(started.status_code, 202, started.data)
        from .capability.recommendation_execution import generate_recommendations
        execution = RecommendationExecution.objects.get(snapshot_id=started.data['id'])
        with patch('apps.scoring.capability.recommendation_execution.get_ai_service', return_value=self.service()), \
                patch('apps.scoring.capability.recommendation_execution.get_router_pool', return_value=None):
            generate_recommendations.run(str(execution.snapshot_id), str(execution.task_id))
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        return self.client.get(f'{self.base}/{run.pk}/recommendations/{execution.snapshot_id}').data

    # ---------------------------------------------------------------- the flow

    def test_the_whole_flow(self):
        # Step 2a: the provisional assessment.
        provisional = self.assess()
        detail = self.client.get(f'{self.base}/{provisional.pk}').data
        records = {r['condition_id']: r for r in detail['assessment']['records']}
        provisional_score = detail['assessment']['result']['score']
        self.assertGreater(provisional_score, 0)
        self.assertLess(provisional_score, 100)
        self.assertEqual(self.reports(provisional)['assessment_stage']['stage'], 'provisional')
        advice = self.recommend(provisional, 'advice-provisional')
        self.assertTrue(advice['plan']['priority_plan']['actions'])
        events_before = list(provisional.events.values_list('id', flat=True))

        # Step 2b: the second layer, as background jobs.
        jobs_url = f'{self.base}/{provisional.pk}/second-layer/jobs'
        self.post(jobs_url, {'operation': 'questions'}, key='plan-questions', expect=202)
        self.run_queued()
        questions = DepthQuestion.objects.filter(run_ref=str(provisional.pk))
        depth_q = questions.filter(kind='depth').order_by('rank').first()
        missing_q = questions.filter(kind='missing').order_by('rank').first()
        self.assertIsNotNone(depth_q)
        self.assertIsNotNone(missing_q)
        skipped = questions.exclude(pk__in=[depth_q.pk, missing_q.pk]).order_by('rank').first()

        shown = self.client.get(f'{self.base}/{provisional.pk}/questions').data
        self.assertEqual(shown['progress']['questions'], questions.count())
        self.assertEqual(shown['next']['question']['rank'], 1)
        made = self.post(f'{self.base}/{provisional.pk}/questions/{depth_q.pk}/responses',
                         {'answer': 'Yes: 85 faculty completed the 40-hour accredited programme; register attached.',
                          'document_ids': [self.document(ATTACHMENT)]}, expect=201)
        self.assertEqual(made.data['status'], 'pending')
        self.post(f'{self.base}/{provisional.pk}/questions/{missing_q.pk}/responses',
                  {'answer': 'See the certificate register.', 'document_ids': [self.document(ATTACHMENT)]}, expect=201)
        self.post(f'{self.base}/{provisional.pk}/questions/{skipped.pk}/responses', {'skip': True}, expect=201)
        uncredited = next(i['code'] for i in release()['indicators'] if i['code'] not in self.credited
                          and i['code'] != missing_q.indicator_code)
        self.post(f'{self.base}/{provisional.pk}/additional-evidence',
                  {'document_ids': [self.document(ADDITIONAL)], 'note': 'AI research ethics review procedure',
                   'picked': [uncredited]}, expect=201)
        ran = self.run_queued()   # one checks job covers all three submissions
        self.assertEqual([j.operation for j in ran], ['checks'])
        self.assertFalse(DepthResponse.objects.filter(question__run_ref=str(provisional.pk), status='pending').exists())
        checked = self.client.get(f"{self.base}/{provisional.pk}/responses/{made.data['id']}").data
        self.assertEqual((checked['status'], checked['supported']), ('checked', True))

        self.post(jobs_url, {'operation': 'depth'}, key='judge-depth', expect=202)
        self.run_queued()
        self.assertTrue(DepthJudgment.objects.filter(run_ref=str(provisional.pk)).exists())

        self.post(jobs_url, {'operation': 'rejudge'}, key='publish-final', expect=202)
        rejudge = self.run_queued()[0]
        self.assertIsNotNone(rejudge.final_run_id, rejudge.result)
        final = CapabilityRun.objects.get(pk=rejudge.final_run_id)

        # The provisional run is untouched; the final run is what reports, recommendations and plans read.
        self.assertEqual(list(provisional.events.values_list('id', flat=True)), events_before)
        final_detail = self.client.get(f'{self.base}/{final.pk}').data
        final_records = {r['condition_id']: r for r in final_detail['assessment']['records']}
        final_score = final_detail['assessment']['result']['score']
        self.assertGreater(final_score, provisional_score)
        rose = [cid for cid, r in final_records.items() if (r.get('credit') or 0) > (records[cid].get('credit') or 0)]
        self.assertTrue(rose)
        self.assertTrue({c['id'] for i in release()['indicators'] if i['code'] == uncredited
                         for c in i['conditions']} & set(rose))
        self.assertFalse([cid for cid, r in final_records.items()
                          if (r.get('credit') or 0) < (records[cid].get('credit') or 0)])
        stage = self.reports(final)['assessment_stage']
        self.assertEqual((stage['stage'], stage['provisional_run_id']), ('final', str(provisional.pk)))
        listed = {row['id']: row for row in self.client.get(self.base).data['results']}
        self.assertEqual(listed[str(final.pk)]['stage'], 'final')
        self.assertEqual(self.client.get(f'{self.base}/{provisional.pk}/questions').data['progress']['final_run_id'],
                         str(final.pk))
        self.assertTrue(self.recommend(final, 'advice-final')['plan']['priority_plan'])
        from .capability.plan_execution import validate_baseline
        validate_baseline(final, final.events.filter(state='completed').last())

        # Spending: every second-layer call reserved against the run's one budget and attributed.
        budget = SecondLayerBudget.objects.get(run=provisional)
        spent = SecondLayerJob.objects.filter(run=provisional)
        self.assertEqual(budget.requests_reserved, sum(j.requests_reserved for j in spent))
        self.assertGreater(budget.requests_reserved, 0)
        self.assertEqual(AIUsage.objects.filter(capability_run=provisional, stage='capability_second_layer').count(),
                         budget.requests_reserved)
        inference = final.events.filter(state='completed').last().payload['inference']
        self.assertTrue(inference['second_layer_metered'])
        self.assertEqual(sum(1 for c in inference['calls'] if c.get('kind') == 'request_reserved'),
                         rejudge.requests_reserved)
        self.assertEqual({'capability_parts', 'capability_advice', 'depth_questions', 'answer_check',
                          'depth_judgment'} - set(self.schemas), set())


@override_settings(**SETTINGS, CAPABILITY_INDICATOR_CONCURRENCY=4)
class ProductFlowConcurrentTests(APITransactionTestCase):
    """The same flow on a committed database with four indicators judged at once (worker threads use their own
    connections): the assessment and the second layer's re-judgment both run concurrently, as in production."""
    setUp = ProductFlowTests.setUp
    test_the_whole_flow = ProductFlowTests.test_the_whole_flow

    @contextlib.contextmanager
    def captureOnCommitCallbacks(self, execute=False):
        yield []   # autocommit: on_commit callbacks already ran


for _name, _value in vars(ProductFlowTests).items():
    if _name.startswith(('reply_', 'model', 'service', 'assess', 'post', 'run_queued', 'document', 'reports',
                         'recommend')) and callable(_value):
        setattr(ProductFlowConcurrentTests, _name, _value)
