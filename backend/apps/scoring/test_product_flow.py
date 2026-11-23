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
from .capability import explanations
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
CONTRA = 'CONTRADICTS'
WITHDRAWN = (f'{CONTRA} Council resolution, June 2025: the AI policy and the programmes under it were withdrawn for the '
             '2024-25 year; no AI teaching, research or administration ran under them after that date.')
SETTINGS = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_JUDGMENT='parts',
                CAPABILITY_AGREEMENT_PASSES=2, CAPABILITY_TIE_BREAK=True, CAPABILITY_MAX_HTTP_CALLS=108,
                CAPABILITY_MAX_COST_USD='20', CAPABILITY_OUTPUT_TOKENS=3000, CAPABILITY_REQUEST_TIMEOUT_SECONDS=60,
                CAPABILITY_RECOMMENDATIONS_ENABLED=True, SECOND_LAYER_JOBS_ENABLED=True,
                SECOND_LAYER_MAX_HTTP_CALLS=None, SECOND_LAYER_MAX_COST_USD=None, AI_RATE_LIMIT_ENABLED=False,
                AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
                AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')


def rubric_area(code):
    return next(i['pillar'] for i in release()['indicators'] if i['code'] == code)


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
        self.contradict = set()   # requirements the stand-in finds contradicted by a CONTRA passage

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
        against = [s for s in windows if CONTRA in s['text']]
        credited = payload['indicator']['code'] in self.credited
        rows = {}
        for condition in payload['indicator']['conditions']:
            findings = []
            if against and condition['id'] in self.contradict:
                findings = [{'part_id': part['id'], 'finding': 'contradicted',
                             'citations': [{'source_id': against[0]['id'], 'quote': against[0]['text'][:80]}]}
                            for part in condition['parts']]
                rows[condition['id']] = {'reason': 'Stand-in: contradicted.', 'scope_supported': True,
                                         'period_supported': True, 'findings': findings}
                continue
            for part in condition['parts']:
                cite = new[0] if new else (windows[0] if credited and windows else None)
                findings.append({'part_id': part['id'], 'finding': 'full' if cite else 'not_found',
                                 'citations': [{'source_id': cite['id'], 'quote': cite['text'][:80]}] if cite else []})
            rows[condition['id']] = {'reason': 'Stand-in.', 'scope_supported': True, 'period_supported': True,
                                     'findings': findings}
        return {'conditions': rows}

    def reply_score_explanations(self, payload):
        # A careful writer: credit from the first quotation, gaps from what is missing, nothing else.
        requirements, indicators = [], []
        for indicator in payload['indicators']:
            indicators.append({'code': indicator['code'], 'found': 'You have made a start here.',
                               'text': 'Some requirements are shown; the rest are next steps.', 'looked': '',
                               'next_step': 'See the next step under each requirement.'})
            for r in indicator['requirements']:
                credited = r['result'] in ('shown in full', 'partly shown') and r['quotations']
                full = r['result'] == 'shown in full'
                gap = not full and not r['result'].startswith('not judged')
                requirements.append({
                    'condition_id': r['condition_id'], 'quote_ids': ['Q1'] if credited else [],
                    'found': f"Your {r['quotations'][0]['document']} records this." if credited else '',
                    'text': 'This is shown.' if full else 'This is partly shown.' if credited else 'Not yet shown.',
                    'looked': 'We read the documents listed for this area.' if gap else '',
                    'next_step': 'Add a record that shows what is missing.' if gap else ''})
        return {'area': {'found': 'Your foundations are good.', 'text': 'You have made a solid start.', 'looked': '', 'next_step': ''},
                'indicators': indicators, 'requirements': requirements}

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

    def reply_depth_question_links(self, payload):
        # Links the first depth questions of two different key indicators, as the same fact asked twice.
        firsts = {}
        for q in payload['questions']:
            firsts.setdefault(q['key_indicator'], q['id'])
        ids = list(firsts.values())[:2]
        return {'groups': [{'question_ids': ids, 'text': 'Which body approved this programme, and on what date? '
                                                          'Please share the minutes.'}] if len(ids) == 2 else []}

    def reply_depth_question_plan(self, payload):
        questions = [{'condition_id': r['condition_id'], 'dimension_ids': [d['id'] for d in r['dimensions'][:2]],
                      'text': 'How many hours did the programme run, and who accredited it? Please attach the register.'}
                     for r in payload['credited_requirements']]
        items = [{'condition_id': r['condition_id'], 'text': 'A record that shows this happening in your college'}
                 for r in payload['requirements_not_yet_shown']]
        return {'answered': [], 'questions': questions, 'missing_items': items}

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
        # A linked question is asked through its group's question, so the college sees one fewer.
        self.assertEqual(shown['progress']['questions'], questions.filter(linked_to__isnull=True).count())
        self.assertEqual(shown['progress']['linked'], questions.filter(linked_to__isnull=False).count())
        self.assertEqual(shown['next']['question']['rank'], 1)
        # A lead lists the questions it answers ("Also answers: ..."); they are never served on their own.
        served = DepthQuestion.objects.get(pk=shown['next']['question']['id'])
        self.assertEqual([q['id'] for q in shown['next']['question']['linked']],
                         [str(q.pk) for q in served.linked.order_by('rank')])
        from .capability.layer2_views import serialize_question
        lead = questions.filter(linked__isnull=False).distinct().first()
        self.assertIsNotNone(lead)
        listed = serialize_question(lead)['linked']
        self.assertEqual({q['id'] for q in listed}, {str(q.pk) for q in lead.linked.all()})
        self.assertTrue(all(q['status'] == 'linked' and q['condition_ids'] and q['text'] for q in listed))
        self.assertNotIn('linked', serialize_question(lead.linked.first()))
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
        # Nothing here contradicts a credit, so nothing falls (lowering: test_a_document_that_contradicts_...).
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
        self.assertEqual({'capability_parts', 'capability_advice', 'depth_question_plan', 'answer_check',
                          'depth_judgment'} - set(self.schemas), set())

        # The second layer exports for offline review of the questions (layer2_export; no model calls).
        import json, tempfile, os
        from django.core.management import call_command
        out = os.path.join(tempfile.mkdtemp(), 'layer2.json')
        call_command('layer2_export', str(provisional.pk), out=out, stdout=open(os.devnull, 'w'))
        exported = json.load(open(out, encoding='utf-8'))
        self.assertEqual(len(exported['questions']), questions.count())
        self.assertEqual({q['text'] for q in exported['questions']}, set(questions.values_list('text', flat=True)))
        linked = questions.filter(linked_to__in=[depth_q, missing_q, skipped]).count()   # answered through a lead
        self.assertEqual(len(exported['responses']), 3 + linked)
        self.assertTrue(exported['depth_judgments'] and exported['jobs'] and exported['events'])

    # ---------------------------------------------------------------- why a page was or wasn't used (#41)

    def test_page_use_explains_where_a_page_went(self):
        import json as _json
        from io import StringIO
        from django.core.management import call_command
        from .capability.page_use import page_use
        run = self.assess()
        payload = run.events.filter(state='completed').last().payload
        page = payload['traces'][0]['source_excerpts'][0]['id']
        result = page_use(run, [page])
        in_trace = {t['indicator'] for t in payload['traces'] if any(e['id'] == page for e in t['source_excerpts'])}
        self.assertEqual({r['indicator'] for r in result['indicators'] if r['in_packet']}, in_trace)
        self.assertTrue(all(r['recompute']['reproduced'] for r in result['indicators'] if 'recompute' in r))
        cited = {r['condition_id'] for r in payload['records'] if (r.get('credit') or 0) > 0 and any(
            c.get('source_id') == page for p in r.get('parts') or [] for c in p.get('citations') or [])}
        self.assertEqual({c for r in result['indicators'] for c in r['credited_requirements_citing_it']}, cited)
        out = StringIO()
        call_command('capability_page_use', str(run.pk), '--page', page, '--json', stdout=out)
        self.assertEqual(_json.loads(out.getvalue())['summary'], result['summary'])
        out = StringIO()
        call_command('capability_page_use', str(run.pk), '--document', payload['traces'][0]['source_excerpts'][0]
                     ['document_id'], '--no-recompute', stdout=out)
        self.assertIn('In the packet of', out.getvalue())

    def test_page_use_on_a_final_run_reproduces_every_packet(self):
        """Test 13 (22 Nov): on the final run, page-use-1 reported "does not reproduce" for C2.1, the one key indicator
        re-judged, because it counted the second layer's windows as retrieval and searched the added pages too."""
        from .capability.page_use import page_use, SECOND_LAYER_ROLES
        indicator = next(i for i in release()['indicators'] if i['code'] in self.credited)
        cid = indicator['conditions'][0]['id']
        _, _, rejudge, final, _ = self.contradict_and_publish([cid], [cid])
        payload = final.events.filter(state='completed').last().payload
        traces = {t['indicator']: t for t in payload['traces']}
        rejudged = set(rejudge.result['targets'])
        self.assertEqual(rejudged, {indicator['code']})
        self.assertTrue(any(e.get('evidence_role') in SECOND_LAYER_ROLES for e in traces[indicator['code']]['source_excerpts']))
        page = traces[indicator['code']]['source_excerpts'][0]['id']
        result = page_use(final, [page])
        self.assertEqual(result['final_run_of'], final.inputs['refines_run_id'])
        self.assertEqual(result['summary']['reproduced'], result['summary']['recomputed'])
        self.assertEqual(result['summary']['recomputed'], len(release()['indicators']))
        row = next(r for r in result['indicators'] if r['indicator'] == indicator['code'])
        self.assertTrue(row['rejudged_in_second_layer'])
        self.assertTrue(set(row['windows_added_after_first_judgment']) <= SECOND_LAYER_ROLES)
        # A page the second layer added: retrieval never read it, and the tool says so.
        added = final.inputs['second_layer']['added_sources']
        self.assertTrue(added)
        result = page_use(final, [added[0]], indicators=[indicator['code']])
        self.assertEqual(result['pages_added_in_second_layer'], [added[0]])
        self.assertTrue(result['indicators'][0]['recompute']['reproduced'])
        # A packet that differs is reported passage by passage.
        from .capability.page_use import compare_packets
        same, diff = compare_packets(traces[indicator['code']]['source_excerpts'][1:],
                                     [e for e in traces[indicator['code']]['source_excerpts']
                                      if e.get('evidence_role') not in SECOND_LAYER_ROLES])
        self.assertFalse(same)
        self.assertEqual(diff['counts'], {'only_in_run': 0, 'only_in_rebuild': 1})

    # ---------------------------------------------------------------- follow-up outcomes (21 Nov)

    def test_follow_up_answers_have_the_outcomes_they_should(self):
        """A scripted set of answers with known expected outcomes (the test 13 audit: the suite did not measure the
        follow-up questions). Credit held for depth (reserve.py) is earned back only by an answer a document backs."""
        from apps.documents.models import Document
        from .capability import reserve
        provisional = self.assess()
        detail = self.client.get(f'{self.base}/{provisional.pk}').data['assessment']
        records = {r['condition_id']: r for r in detail['records']}
        held = detail['result']['depth_reserve']
        self.assertEqual(held['share'], 0.25)
        self.assertGreater(held['held_points'], 0)
        self.assertEqual(held['earned_back_points'], 0)
        self.assertAlmostEqual(detail['result']['score'], held['evidence_score'] * 0.75, delta=0.011)
        credited = sorted(c for c, r in records.items() if (r.get('credit') or 0) > 0)
        html = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'leadership', 'file': 'html'})
        self.assertIn('is held until your follow-up answers show how far the evidence goes', html.content.decode())

        # Coverage: every key indicator is asked about; no total cap; tied questions spread across areas.
        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'questions'}, key='plan', expect=202)
        self.run_queued()
        questions = list(DepthQuestion.objects.filter(run_ref=str(provisional.pk)).order_by('rank'))
        depth_qs = [q for q in questions if q.kind == 'depth']
        self.assertEqual({q.condition_ids[0] for q in depth_qs}, set(credited))
        rubric = release()
        gaps = {i['code'] for i in rubric['indicators'] for c in i['conditions'] if (records[c['id']].get('credit') or 0) < 1}
        self.assertEqual({q.indicator_code for q in questions if q.kind == 'missing'}, gaps)
        self.assertEqual(len(questions), len(depth_qs) + len(gaps))   # nothing cut
        top = [q for q in depth_qs[:4]]
        self.assertEqual(len({rubric_area(q.indicator_code) for q in top}), 2)   # C1 and C2 take turns
        self.assertTrue(all(float(q.points_at_stake) > 0 for q in questions))
        self.assertEqual(sorted((float(q.points_at_stake) for q in questions), reverse=True),
                         [float(q.points_at_stake) for q in questions])
        listed = self.client.get(f'{self.base}/{provisional.pk}/questions').data
        self.assertIn('points_at_stake', listed['next']['question'])
        # Missing-evidence items: starting capability, then repeated use, then results; no rubric codes.
        level = {c['id']: c['level'] for i in rubric['indicators'] for c in i['conditions']}
        for q in questions:
            if q.kind == 'missing':
                self.assertEqual([level[c] for c in q.condition_ids],
                                 sorted((level[c] for c in q.condition_ids), key='FAO'.index))
                self.assertNotIn('AIQIF', q.text)

        by_condition = {}
        for q in depth_qs:
            by_condition.setdefault(q.condition_ids[0], []).append(q)
        # 0. Repeated questions linked (questions-0.3): the college sees the lead with one wording; the member waits.
        member = next(q for q in depth_qs if q.linked_to_id)
        lead = member.linked_to
        self.assertEqual((member.status, lead.status), ('linked', 'open'))
        self.assertNotEqual(lead.indicator_code, member.indicator_code)
        involved = set(lead.condition_ids) | set(member.condition_ids)
        free = [c for c in credited if c not in involved and all(q.status == 'open' for q in by_condition.get(c, []))]
        backed, dont_know, typed, already = free[0], free[1], free[2], free[3]
        respond = lambda q, body: self.post(f'{self.base}/{provisional.pk}/questions/{q.pk}/responses', body, expect=201)
        # 1. An answer a new document backs: should earn back held credit.
        for q in by_condition[backed]:
            respond(q, {'answer': '85 of 120 faculty completed the 40-hour accredited programme.',
                        'document_ids': [self.document(ATTACHMENT)]})
        # 2. "Don't know": stays evidenced, no model call.
        for q in by_condition[dont_know]:
            respond(q, {'skip': True})   # "don't know" in the API
        # 3. A typed answer with no document: counts for nothing.
        for q in by_condition[typed]:
            respond(q, {'answer': 'We run a 300-hour accredited programme.'})
        # 4. A document the first assessment had already read: the college is told it was already counted.
        ssr = str(Document.objects.get(sprint=self.sprint, document_type='naac_ssr').pk)
        already_q = by_condition[already][0]
        made = respond(already_q, {'answer': 'It is in our self-study report.', 'document_ids': [ssr]})
        # 5. A new document for a missing-evidence question: re-judged, so the final result has new evidence as well
        # as depth answers, and both must reach it.
        missing_q = next(q for q in questions if q.kind == 'missing')
        respond(missing_q, {'answer': 'Our certificate register.', 'document_ids': [self.document(ATTACHMENT)]})
        # 6. One answer to a linked question is recorded for both and checked against each one's requirement.
        respond(lead, {'answer': 'The Academic Council approved it on 12 June 2024; minutes attached.',
                       'document_ids': [self.document(ATTACHMENT)]})
        self.assertEqual(DepthQuestion.objects.get(pk=member.pk).status, 'answered')
        copy = DepthResponse.objects.get(question=member)
        self.assertEqual((copy.answer, copy.submitted_via), (DepthResponse.objects.get(question=lead).answer, 'linked'))
        with self.assertRaises(AssertionError):   # the member itself cannot be answered separately
            respond(member, {'skip': True})
        self.run_queued()
        self.assertEqual(DepthResponse.objects.get(pk=copy.pk).status, 'checked')   # checked on its own
        # A member the shared answer does not resolve gets its own follow-up, shown next.
        from .capability.layer2_service import progress
        before = progress(str(provisional.pk))['follow_ups_open']
        DepthResponse.objects.filter(pk=copy.pk).update(supported=False, follow_up_text='Thank you. For the AI '
                                                        'policy specifically, which body approved it?')
        self.assertEqual(progress(str(provisional.pk))['follow_ups_open'], before + 1)
        follow = self.client.get(f'{self.base}/{provisional.pk}/questions').data
        self.assertEqual(follow['next']['type'], 'follow_up')
        checked = DepthResponse.objects.get(pk=made.data['id'])
        self.assertEqual([d['document_id'] for d in checked.support_check['search']['already_counted']], [ssr])
        self.assertTrue(checked.follow_up_text.startswith('We had already read'), checked.follow_up_text)

        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'depth'}, key='depth', expect=202)
        judged = self.run_queued()[0].result
        levels = {j['condition_id']: j['final_level'] for j in judged['judged']}
        self.assertEqual(levels[backed], 'substantiated')
        self.assertEqual(levels[dont_know], 'evidenced')
        self.assertNotIn(typed, levels)

        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'rejudge'}, key='final', expect=202)
        rejudge = self.run_queued()[0]
        self.assertIsNotNone(rejudge.final_run_id, rejudge.result)
        self.assertTrue(rejudge.result['targets'])   # new evidence re-judged, and depth carried through the merge
        self.assertIn({'condition_id': backed, 'level': 'substantiated'}, rejudge.result['depth_changes'])
        final = CapabilityRun.objects.get(pk=rejudge.final_run_id)
        final_detail = self.client.get(f'{self.base}/{final.pk}').data['assessment']
        final_records = {r['condition_id']: r for r in final_detail['records']}
        self.assertEqual(final_records[backed]['depth_level'], 'substantiated')
        self.assertEqual(final_records[dont_know]['depth_level'], 'evidenced')
        self.assertEqual(float(reserve.record_factor(final_records[backed])), 0.875)
        final_held = final_detail['result']['depth_reserve']
        self.assertGreater(final_held['earned_back_points'], 0)
        self.assertGreater(final_detail['result']['score'], detail['result']['score'])
        self.assertGreaterEqual(final_held['evidence_score'], held['evidence_score'])   # credit only rose
        html = self.client.get(f'{self.base}/{final.pk}/report', {'audience': 'leadership', 'file': 'html'})
        self.assertIn('Your follow-up answers earned back', html.content.decode())
        self.reports(final)
        # The priority plan and plan baseline read the same score.
        self.assertEqual(self.recommend(final, 'advice-final')['plan']['priority_plan']['score'],
                         round(final_detail['result']['score'], 2))
        from .capability.plan_execution import validate_baseline
        validate_baseline(final, final.events.filter(state='completed').last())

    # ---------------------------------------------------------------- score explanations

    def test_explanations_for_the_provisional_and_the_final_result(self):
        from .models import CapabilityExplanation
        provisional = self.assess()
        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'explain'}, key='explain',
                  expect=202)
        explained = self.run_queued()[0]
        self.assertEqual((explained.operation, explained.result['explained'], explained.result['fallbacks']),
                         ('explain', 216, 0))
        self.assertEqual(explained.result['calls'], 9)   # one per area
        detail = self.client.get(f'{self.base}/{provisional.pk}').data['assessment']
        credited = next(r for r in detail['records'] if (r.get('credit') or 0) > 0)
        self.assertIn('records this', credited['explanation']['found'])
        self.assertTrue(all(r['explanation']['text'] for r in detail['records']))
        self.assertEqual(detail['result']['documented']['pillars'][0]['explanation']['text'], 'You have made a solid start.')
        report = self.reports(provisional)   # all four formats render with them
        html = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'leadership', 'file': 'html'})
        self.assertIn('Your foundations are good. You have made a solid start.', html.content.decode())   # the area explanation
        # Test 13 (20 Nov) found the leadership PDF and both evidence reports without them; all three carry them now.
        import fpdf
        printed = []
        real = fpdf.FPDF.multi_cell

        def capture(pdf, w, h=None, text='', *args, **kwargs):
            printed.append(str(text))
            return real(pdf, w, h, text, *args, **kwargs)
        with patch.object(fpdf.FPDF, 'multi_cell', capture):
            for audience in ('leadership', 'evidence'):
                response = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': audience, 'file': 'pdf'})
                self.assertEqual(response.status_code, 200, audience)
                text = ' '.join(printed)
                self.assertIn('You have made a start here.', text, audience)   # a key indicator's explanation
                printed.clear()
        with patch.object(fpdf.FPDF, 'multi_cell', capture):
            self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'evidence', 'file': 'pdf'})
        self.assertIn('Next step: Add a record that shows what is missing.', ' '.join(printed))   # per requirement
        evidence = self.client.get(f'{self.base}/{provisional.pk}/report', {'audience': 'evidence', 'file': 'html'})
        self.assertIn('records this.', evidence.content.decode())   # a requirement's "what we found"
        self.assertIn('<strong>Where we looked:</strong>', evidence.content.decode())
        self.assertIn('You have made a start here.', html.content.decode())   # a key indicator's
        self.assertEqual(report['explanations_version'], explanations.VERSION)
        # Stored beside the run: the completed event, and so every integrity hash, is unchanged.
        event = provisional.events.get(state='completed')
        self.assertNotIn('explanation', json.dumps(event.payload['records'][0]))
        # Explaining a final result that does not exist yet is refused up front.
        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'explain', 'options': {'final': True}},
                  key='explain-missing-final', expect=400)
        # The final result gets its own, started by itself once it is published.
        self.post(f'{self.base}/{provisional.pk}/additional-evidence',
                  {'document_ids': [self.document(ADDITIONAL)], 'note': 'Our AI lab register',
                   'picked': [sorted(set(i['code'] for i in release()['indicators']) - self.credited)[0]]},
                  expect=201)
        self.run_queued()
        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'rejudge'}, key='publish-final',
                  expect=202)
        rejudge, explain_final = self.run_queued()
        self.assertEqual((explain_final.operation, explain_final.options), ('explain', {'final': True}))
        self.assertEqual(rejudge.result['explain_job_id'], str(explain_final.pk))
        final = CapabilityRun.objects.get(pk=rejudge.final_run_id)
        self.assertEqual(CapabilityExplanation.objects.get(job=explain_final).run, final)
        final_detail = self.client.get(f'{self.base}/{final.pk}').data['assessment']
        self.assertTrue(all(r['explanation']['text'] for r in final_detail['records']))
        self.reports(final)


    # ---------------------------------------------------------------- depth decision 1: answers can lower a score

    def contradict_and_publish(self, picked, contradict):
        provisional = self.assess()
        detail = self.client.get(f'{self.base}/{provisional.pk}').data
        records = {r['condition_id']: r for r in detail['assessment']['records']}
        self.contradict = set(contradict)
        self.assertTrue(all((records[c].get('credit') or 0) > 0 for c in contradict))
        self.post(f'{self.base}/{provisional.pk}/additional-evidence',
                  {'document_ids': [self.document(WITHDRAWN)], 'note': 'The council withdrew the policy',
                   'picked': picked}, expect=201)
        self.run_queued()
        self.post(f'{self.base}/{provisional.pk}/second-layer/jobs', {'operation': 'rejudge'}, key='publish-final',
                  expect=202)
        rejudge = self.run_queued()[0]
        final = CapabilityRun.objects.get(pk=rejudge.final_run_id)
        final_detail = self.client.get(f'{self.base}/{final.pk}').data
        return records, detail['assessment']['result']['score'], rejudge, final, final_detail

    def test_a_document_that_contradicts_the_credit_lowers_the_final_result(self):
        indicator = next(i for i in release()['indicators'] if i['code'] in self.credited)
        cid = indicator['conditions'][0]['id']
        records, provisional_score, rejudge, final, final_detail = self.contradict_and_publish([cid], [cid])
        final_records = {r['condition_id']: r for r in final_detail['assessment']['records']}
        self.assertLess(final_records[cid]['credit'], records[cid]['credit'])
        self.assertEqual(final_records[cid]['state'], 'not_met')
        # The final run keeps why: the merge row, with the quotes from the document the college sent.
        second_layer = final.inputs['second_layer']
        row = next(r for r in second_layer['merge'] if r['condition_id'] == cid)
        self.assertEqual(row['decision'], 'lowered')
        self.assertIn(CONTRA, row['contradicting_quotes'][0]['quote'])
        self.assertEqual([r['condition_id'] for r in second_layer['lowerings']], [cid])
        self.assertEqual([r['condition_id'] for r in rejudge.result['lowerings']], [cid])
        self.assertLess(final_detail['assessment']['result']['score'], provisional_score)
        # Nothing else fell, and the final result renders in every report.
        self.assertFalse([c for c, r in final_records.items() if c != cid
                          and (r.get('credit') or 0) < (records[c].get('credit') or 0)])
        stage = self.reports(final)['assessment_stage']
        self.assertEqual((stage['stage'], stage['lowered']), ('final', [cid]))
        self.assertIn('1 requirement went down', stage['note'])

    def test_one_document_contradicting_many_requirements_is_held_for_review(self):
        indicator = next(i for i in release()['indicators'] if i['code'] in self.credited
                         and len(i['conditions']) > 3)
        ids = [c['id'] for c in indicator['conditions']]
        records, provisional_score, rejudge, final, final_detail = self.contradict_and_publish([indicator['code']], ids)
        final_records = {r['condition_id']: r for r in final_detail['assessment']['records']}
        self.assertEqual(rejudge.result['lowerings'], [])
        self.assertEqual({r['condition_id'] for r in rejudge.result['contradictions'] if r['held']}, set(ids))
        self.assertEqual([final_records[c]['credit'] for c in ids], [records[c]['credit'] for c in ids])
        self.assertEqual(final_detail['assessment']['result']['score'], provisional_score)


@override_settings(**SETTINGS, CAPABILITY_INDICATOR_CONCURRENCY=4)
class ProductFlowConcurrentTests(APITransactionTestCase):
    """The same flow on a committed database with four indicators judged at once (worker threads use their own
    connections): the assessment and the second layer's re-judgment both run concurrently, as in production."""
    setUp = ProductFlowTests.setUp
    test_the_whole_flow = ProductFlowTests.test_the_whole_flow
    # Explanations write four areas at once here (the job takes the assessment's indicator concurrency).
    test_explanations_for_the_provisional_and_the_final_result = \
        ProductFlowTests.test_explanations_for_the_provisional_and_the_final_result

    @contextlib.contextmanager
    def captureOnCommitCallbacks(self, execute=False):
        yield []   # autocommit: on_commit callbacks already ran


for _name, _value in vars(ProductFlowTests).items():
    if _name.startswith(('reply_', 'model', 'service', 'assess', 'post', 'run_queued', 'document', 'reports',
                         'recommend', 'contradict_and_publish')) and callable(_value):
        setattr(ProductFlowConcurrentTests, _name, _value)
