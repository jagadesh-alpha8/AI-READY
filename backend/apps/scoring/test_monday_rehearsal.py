"""Rehearsal of the three SSR-only runs planned for the full-corpus demo (3a conditions, 3b parts, 3c parts with
the targeted extra search), through the real path: run creation, the Celery task, publication and every report
format, with the 200,000-character lane, page deduplication, repeat skipping, two passes and four workers.

Needs the local embedding model (CAPABILITY_EMBEDDING_PATH) and the private SSR page export; skipped otherwise.
The assessor is fake: it answers in the Gemini response shape and cites exact text from the packet it is sent.
"""
import contextlib
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import CapabilityExecution
from .tasks import run_capability_assessment

MODEL = os.environ.get('REHEARSAL_EMBEDDING_PATH', '')
PAGES = os.environ.get('REHEARSAL_SSR_PAGES', '')
GEMINI = 'https://generativelanguage.googleapis.com/v1beta/openai/'
BASE = dict(SECURE_SSL_REDIRECT=False, CAPABILITY_ASSESSMENT_ENABLED=True, AI_RATE_LIMIT_ENABLED=False,
            AI_PROCESSING_MODE='single', AI_TEMPERATURE=0, AI_SEED=42,
            AI_PRICING_JSON='{"gemini-3.8-flash":{"input":0.75,"output":3.75}}',
            CAPABILITY_RETRIEVAL_MODE='hybrid', CAPABILITY_EMBEDDING_PATH=MODEL,
            CAPABILITY_RETRIEVAL_ALLOCATION='protected-baseline-then-discovery-xwide-v1',
            CAPABILITY_DEDUPLICATE_PAGES=True, CAPABILITY_REPEAT_SKIP=True,
            CAPABILITY_MAX_INPUT_TOKEN_BOUND=400000, CAPABILITY_AGREEMENT_PASSES=2,
            CAPABILITY_GEMINI_REASONING_EFFORT='high', CAPABILITY_INDICATOR_CONCURRENCY=4,
            CAPABILITY_EMBEDDING_CACHE_DIR=os.environ.get('REHEARSAL_CACHE_DIR', ''))
RUNS = {
    '3a': dict(CAPABILITY_MAX_HTTP_CALLS=108, CAPABILITY_MAX_COST_USD='60'),
    '3b': dict(CAPABILITY_MAX_HTTP_CALLS=108, CAPABILITY_MAX_COST_USD='60', CAPABILITY_JUDGMENT='parts'),
    '3c': dict(CAPABILITY_MAX_HTTP_CALLS=170, CAPABILITY_MAX_COST_USD='90', CAPABILITY_JUDGMENT='parts',
               CAPABILITY_FOLLOW_UP_SEARCH=True),
}


@unittest.skipUnless(MODEL and PAGES and Path(MODEL).is_dir() and Path(PAGES).is_file(),
                     'Set REHEARSAL_EMBEDDING_PATH and REHEARSAL_SSR_PAGES to rehearse the demo runs.')
class MondayRehearsal(APITransactionTestCase):
    @contextlib.contextmanager
    def captureOnCommitCallbacks(self, execute=False):
        yield []

    def setUp(self):
        institution = Institution.objects.create(name='Vels Institute of Science, Technology and Advanced Studies')
        self.sprint = Sprint.objects.create(institution=institution)
        user = User.objects.create_user(username='coordinator', email='c@example.com',
                                        role=User.Role.IQAC_COORDINATOR, institution=institution)
        self.client.force_authenticate(user)
        pages = [p for p in json.load(open(PAGES))['pages'] if p['text'].strip()]
        ssr = Document.objects.create(sprint=self.sprint, document_type='naac_ssr')
        for p in pages:
            DocumentPage.objects.create(document=ssr, page_number=p['page_number'], text=p['text'])
        # A second document that restates SSR pages, as the AQAR does: exercises deduplication and repeat skipping.
        copy = Document.objects.create(sprint=self.sprint, document_type='other')
        for n, p in enumerate(pages[40:60], 1):
            DocumentPage.objects.create(document=copy, page_number=n, text=p['text'] if n % 2 else p['text'] + ' Restated.')
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
        self.sdk = MagicMock()
        self.sdk.with_options.return_value = self.sdk
        self.sdk.chat.completions.create.side_effect = self.response
        self.largest_request = 0

    def response(self, **kwargs):
        content = kwargs['messages'][1]['content']
        self.largest_request = max(self.largest_request, len(content.encode()))
        payload = json.loads(content)
        windows = [s for s in payload['sources'] if s.get('evidence_role') != 'report_timestamp' and len(s['text']) > 60]
        extra = [s for s in windows if s.get('evidence_role') == 'follow_up_search']
        cite = lambda w: [{'source_id': w['id'], 'quote': w['text'][:50]}]
        conditions = payload['indicator']['conditions']
        if 'parts' in conditions[0]:
            body = {'conditions': {c['id']: {
                'reason': 'Rehearsal.', 'scope_supported': True, 'period_supported': True,
                'findings': [{'part_id': p['id'], 'finding': 'full' if n == 0 or extra else 'not_found',
                              'citations': cite(extra[0] if n and extra else windows[0]) if n == 0 or extra else []}
                             for n, p in enumerate(c['parts'])]} for c in conditions}}
        else:
            body = {'conditions': {c['id']: {'state': 'met' if n % 3 == 0 else 'unknown', 'reason': 'Rehearsal.',
                                             'scope_supported': True, 'period_supported': True,
                                             'citations': cite(windows[0]) if n % 3 == 0 else []}
                                   for n, c in enumerate(conditions)}}
        return SimpleNamespace(model='gemini-3.8-flash',
            usage=SimpleNamespace(prompt_tokens=60000, completion_tokens=20000, prompt_tokens_details=None,
                                  completion_tokens_details=None, total_tokens=80000),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(body), refusal=None))])

    def rehearse(self, name):
        with override_settings(**BASE, **RUNS[name]):
            with patch('apps.scoring.capability.execution.dispatch'):
                started = self.client.post(self.url, {'population': 'All students and faculty', 'reference_period': '2023-24'},
                                           format='json', HTTP_IDEMPOTENCY_KEY=name)
            self.assertEqual(started.status_code, 202, started.data)
            execution = CapabilityExecution.objects.get(run_id=started.data['id'])
            service = OpenAIExtractionService(api_key='test', model='gemini-3.8-flash', client=self.sdk, base_url=GEMINI)
            with patch('apps.scoring.tasks.get_ai_service', return_value=service), patch(
                    'apps.scoring.tasks.get_router_pool', return_value=None):
                run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
            execution.refresh_from_db()
            detail = self.client.get(f'{self.url}/{execution.run_id}')
            self.assertEqual(execution.status, 'completed', detail.data.get('events', '')[-1:] if isinstance(detail.data, dict) else '')
            assessment = detail.data['assessment']
            self.assertEqual(len(assessment['records']), 216)
            for query in ('', '?file=json', '?file=pdf', '?audience=evidence', '?audience=evidence&file=pdf'):
                report = self.client.get(f'{self.url}/{execution.run_id}/report{query}')
                self.assertEqual(report.status_code, 200, (query, getattr(report, 'data', None)))
            evidence = self.client.get(f'{self.url}/{execution.run_id}/evidence')
            self.assertEqual(evidence.status_code, 200)
            return execution, assessment

    def test_3a_3b_3c(self):
        summary = {}
        for name in ('3a', '3b', '3c'):
            execution, assessment = self.rehearse(name)
            policy = assessment['traces'][0]['retrieval_policy']
            self.assertEqual(policy['baseline_chars'], 200000)
            self.assertIn('repeat_skip', policy)
            records = assessment['records']
            reserved = float(execution.usd_reserved)
            summary[name] = {'requests': execution.requests_reserved, 'reserved_usd': round(reserved, 2),
                             'largest_request_bytes': self.largest_request,
                             'max_input_bound': max(c.get('input_token_bound', 0) for c in assessment['inference']['calls']),
                             'timeout': assessment['inference']['settings']['timeout_seconds'],
                             'output_tokens': assessment['inference']['settings']['output_tokens']}
            if name != '3a':
                self.assertIn('documented', assessment['result'])
            if name == '3c':
                raised = [r for r in records if r.get('follow_up', {}).get('replaced')]
                self.assertTrue(raised)
                summary[name]['raised_by_extra_search'] = len(raised)
        print(json.dumps(summary, indent=1))
