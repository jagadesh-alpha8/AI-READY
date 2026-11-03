"""Synthetic evidence-to-report contracts. No institutional exports or live model work."""
import json
import tempfile
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.models import DocumentPage, ExtractionJob
from apps.facts.models import ExtractedFact, FactReviewHistory, ReviewBatch
from apps.facts.review_queue import start, view, decide
from apps.facts.verification import conflicts, metrics
from apps.gaps.models import GapItem
from apps.institutions.models import Institution
from apps.scoring.capability.evaluation import evaluate, validate_decisions
from apps.scoring.capability.storage import create_run, digest
from apps.scoring.capability.reviewed_evidence import snapshot
from apps.sprints.models import Sprint

POSITIVE = 'In 2025-26, computing resources were accessible to 20 learners in the engineering programme.'
NEGATIVE = 'In 2025-26, computing resources were accessible to 0 learners in the engineering programme.'


@override_settings(SECURE_SSL_REDIRECT=False, FACT_VERIFICATION_MODE='shadow')
class ReviewJourneyTests(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='Synthetic College')
        self.sprint = Sprint.objects.create(institution=self.institution)
        self.user = User.objects.create_user(username='reviewer', email='review@example.test',
            role=User.Role.IQAC_COORDINATOR, institution=self.institution)
        self.client.force_authenticate(self.user)
        self.url = f'/api/v1/sprints/{self.sprint.pk}/review-batch'
        self.doc = Document.objects.create(sprint=self.sprint, original_filename='synthetic.pdf', document_type='naac_ssr')
        self.page = DocumentPage.objects.create(document=self.doc, page_number=1, text=POSITIVE)

    def fact(self, **overrides):
        values = dict(sprint=self.sprint, document=self.doc, source_document=self.doc,
            field_key='computing_access', field_name='Learner access to computing resources', value=20,
            data_type='number', source_page='1', source_snippet=POSITIVE, confidence_score=0.98,
            owner_role='iqac_coordinator', scope={'period': '2025-26', 'programme': 'engineering'}, fact_kind='context')
        values.update(overrides)
        return ExtractedFact.objects.create(**values)

    def run_snapshot(self):
        return create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk,
            population='Engineering learners', reference_period='2025-26')

    def test_total_budget_persisted_across_categories_and_no_refill(self):
        for n in range(30):
            self.fact(field_key=f'computing_access_{n}', verification_status=['needs_review', 'invalid', 'conflicting'][n % 3])
        self.fact(field_key='flower_colour', field_name='Flower colour', source_snippet='The flowers are blue.', value='blue', data_type='string')
        self.assertEqual(self.client.get(self.url).data['started'], False)
        self.assertFalse(ReviewBatch.objects.exists())
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data['cases']), 25)
        self.assertEqual(len(response.data['overflow']), 5)
        ids = [c['id'] for c in response.data['cases']]
        for case in response.data['cases']:
            result = self.client.post(f'{self.url}/{case["id"]}', {'action': 'defer', 'reason': 'Not known yet'}, format='json')
            self.assertEqual(result.status_code, 200, result.data)
        self.fact(field_key='new_computing_access')
        data = self.client.post(self.url, {}, format='json').data
        self.assertEqual([c['id'] for c in data['cases']], ids)
        self.assertEqual(len(data['overflow']), 5)
        self.assertTrue(all(c['state'] == 'defer' for c in data['cases']))
        self.assertGreater(data['new_unbatched_fact_count'], 0)
        extra = data['overflow'][0]
        self.assertEqual(self.client.post(f'{self.url}/{extra["id"]}', {'action': 'defer', 'reason': 'Unknown'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{self.url}/{extra["id"]}', {'action': 'defer', 'reason': 'Unknown', 'optional_follow_up': True}, format='json').status_code, 200)

    def test_duplicate_question_applies_one_decision_idempotently(self):
        a, b = self.fact(), self.fact()
        batch, _ = start(self.sprint)
        self.assertEqual(len(batch.cases), 1)
        case = batch.cases[0]
        body = {'action': 'confirm'}
        decide(self.sprint, self.user, case['id'], body)
        decide(self.sprint, self.user, case['id'], body)
        self.assertEqual(FactReviewHistory.objects.filter(fact__in=[a, b]).count(), 2)
        self.assertEqual(ExtractedFact.objects.filter(status='confirmed').count(), 2)
        self.assertEqual(view(self.sprint)['cases'][0]['state'], 'confirm')
        self.assertEqual(metrics.workload(self.sprint)['current']['resolved_by_you'], 2)
        a.refresh_from_db()
        self.assertEqual(a.verification_status, 'verified')

    def test_conflict_resolution_freezes_provider_payload_and_rejected_history(self):
        a = self.fact()
        page2 = DocumentPage.objects.create(document=self.doc, page_number=2, text=NEGATIVE)
        b = self.fact(value=0, source_page='2', source_snippet=NEGATIVE)
        gap = GapItem.objects.create(sprint=self.sprint, gap_type='conflict', source_fact=a,
                                    conflict_fact_b=b, title='Synthetic access discrepancy')
        old = self.run_snapshot()
        before = deepcopy(old.inputs)
        batch, _ = start(self.sprint)
        decide(self.sprint, self.user, batch.cases[0]['id'], {'action': 'choose', 'fact_id': str(a.pk), 'reason': 'Supported engineering access record'})
        gap.refresh_from_db()
        self.assertEqual(gap.status, 'resolved')
        fresh = self.run_snapshot()
        ledger = fresh.inputs['reviewed_evidence']
        self.assertEqual(next(c for c in ledger['claims'] if c['id'] == str(b.pk))['disposition'], 'rejected')
        self.assertTrue(next(c for c in ledger['claims'] if c['id'] == str(a.pk))['decisions'])
        seen = []
        class FixtureProvider:
            def extract_structured_data(inner, **kwargs):
                payload = json.loads(kwargs['user_content']); seen.append(payload)
                return {'conditions': {c['id']: {'state': 'unknown', 'reason': 'No further supported requirement',
                    'citations': [], 'scope_supported': False, 'period_supported': False} for c in payload['indicator']['conditions']}}
        evaluated = evaluate(fresh.inputs['sources'], service=FixtureProvider(),
            population=fresh.inputs['population'], reference_period=fresh.inputs['reference_period'],
            reviewed_evidence=ledger)
        self.assertEqual(len(evaluated['records']), 216)
        sent_claims = [c for p in seen for c in p['reviewed_evidence']['claims']]
        self.assertTrue(any(c['id'] == str(a.pk) and c['decisions'][-1]['actor_id'] == str(self.user.pk) for c in sent_claims))
        from apps.scoring.capability.engine import release
        indicator = release()['indicators'][20]
        rows = {'conditions': [{'condition_id': c['id'], 'state': 'met', 'reason': 'Use rejected source',
            'scope_supported': True, 'period_supported': True,
            'citations': [{'source_id': str(page2.pk), 'quote': NEGATIVE}]} for c in indicator['conditions']]}
        checked = validate_decisions(indicator, rows, fresh.inputs['sources'], reviewed_evidence=ledger)
        self.assertTrue(all(r['state'] == 'unknown' for r in checked))
        old.refresh_from_db()
        self.assertEqual(old.inputs, before)
        self.assertEqual(old.inputs_hash, digest(before))
        self.assertNotEqual(old.inputs_hash, fresh.inputs_hash)
        self.assertFalse(snapshot(self.sprint)['issues'][-1]['status'] == 'open')
        self.assertFalse(conflicts.disagreements(list(ExtractedFact.objects.filter(sprint=self.sprint))))
        # Material new evidence explicitly reopens the issue without undoing history.
        new_doc = Document.objects.create(sprint=self.sprint, original_filename='new-source.pdf')
        DocumentPage.objects.create(document=new_doc, page_number=1, text=NEGATIVE)
        self.fact(document=new_doc, source_document=new_doc, value=0, source_snippet=NEGATIVE)
        reopened = snapshot(self.sprint)['issues']
        self.assertTrue(any(i['status'] == 'open' and 'New or changed' in i.get('rationale', '') for i in reopened))

    def test_scopes_do_not_create_false_conflicts(self):
        base = self.fact()
        for changed in ({'department': 'marine'}, {'programme': 'mathematics'}, {'population': 'postgraduate'},
                        {'period': '2024-25'}, {'unit': 'percent'}, {'entity': 'other campus'}):
            a = self.fact(scope={**base.scope, 'department': 'engineering', 'entity': 'main campus', 'population': 'undergraduate'})
            b = self.fact(value=0, scope={**a.scope, **changed},
                          source_snippet=POSITIVE.replace('2025-26', changed.get('period', '2025-26')))
            self.assertFalse(conflicts.disagreements([a, b]), changed)

    def test_unsupported_correction_is_declaration_not_quote_or_credit(self):
        f = self.fact()
        batch, _ = start(self.sprint)
        decide(self.sprint, self.user, batch.cases[0]['id'], {'action': 'correct', 'value': 200, 'reason': 'My recollection; evidence unavailable'})
        ledger = self.run_snapshot().inputs['reviewed_evidence']
        claim = ledger['claims'][0]
        self.assertEqual(claim['value'], 200)
        self.assertEqual(claim['source']['quote'], '')
        self.assertEqual(claim['original_source']['quote'], POSITIVE)
        self.assertNotEqual(claim['verification']['grounding'], 'exact')
        self.assertEqual(claim['decisions'][-1]['rationale'], 'My recollection; evidence unavailable')

    def test_unavailable_is_not_negative_and_warning_history_remains(self):
        f = self.fact(source_snippet='No matching quotation')
        batch, _ = start(self.sprint)
        f.refresh_from_db()
        warning = f.verification_status
        decide(self.sprint, self.user, batch.cases[0]['id'], {'action': 'cannot_establish', 'reason': 'Document unavailable'})
        f.refresh_from_db()
        self.assertEqual(f.status, 'extracted')
        self.assertEqual(f.verification_status, warning)
        self.assertEqual(view(self.sprint)['cases'][0]['state'], 'cannot_establish')
        self.assertEqual(snapshot(self.sprint)['review_batch']['decisions'][batch.cases[0]['id']]['action'], 'cannot_establish')

    def test_tenant_boundary_stale_decisions_and_read_only_gets(self):
        f = self.fact(); batch, _ = start(self.sprint)
        foreign = Institution.objects.create(name='Other')
        sprint2 = Sprint.objects.create(institution=foreign)
        self.fact(sprint=sprint2, value=777)
        self.assertEqual(len(self.run_snapshot().inputs['reviewed_evidence']['claims']), 1)
        self.assertEqual(self.client.get(f'/api/v1/sprints/{sprint2.pk}/review-batch').status_code, 403)
        f.value = 21; f.save()
        response = self.client.post(f'{self.url}/{batch.cases[0]["id"]}', {'action': 'confirm'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FactReviewHistory.objects.filter(fact=f).exists())
        self.assertEqual(view(self.sprint)['cases'][0]['state'], 'stale')
        count = f.verifications.count()
        with patch('apps.scoring.capability.execution.dispatch') as dispatch:
            self.client.get(self.url); self.client.get(f'/api/v1/sprints/{self.sprint.pk}/verification/summary')
            dispatch.assert_not_called()
        self.assertEqual(f.verifications.count(), count)

    def test_identity_question_shares_budget_and_controls_fresh_scope(self):
        self.page.text = 'Institution name: Synthetic Source University\n' + POSITIVE
        self.page.save()
        for n in range(30): self.fact(field_key=f'computing_access_{n}')
        batch, _ = start(self.sprint)
        self.assertEqual(len([c for c in batch.cases if c['initial']]), 25)
        self.assertEqual(batch.cases[0]['kind'], 'identity')
        result = self.client.post(f'{self.url}/{batch.cases[0]["id"]}',
            {'action': 'identity', 'source_institution': 'Synthetic Source University'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        fresh = self.run_snapshot()
        self.assertEqual(fresh.inputs['scope']['institution']['assessed_name'], 'Synthetic Source University')
        self.assertEqual(self.institution.name, 'Synthetic College')

    @override_settings(FACT_VERIFICATION_MODE='enforce')
    def test_enforce_uses_existing_policy_shadow_remains_distinct(self):
        self.fact()
        start(self.sprint)
        self.assertEqual(view(self.sprint)['mode'], 'enforce')
        # Eligibility follows calibrated policy; never raise it to meet the budget.
        for fact in ExtractedFact.objects.filter(status='confirmed'):
            self.assertEqual(fact.verification_status, 'verified')
            self.assertIn(fact.automation_decision, ('auto_verified', 'precedent'))

    @override_settings(CAPABILITY_ASSESSMENT_ENABLED=True, CAPABILITY_MAX_HTTP_CALLS=72,
        CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000, AI_RATE_LIMIT_ENABLED=False,
        AI_PROCESSING_MODE='single', AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
        AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
    def test_real_upload_extraction_grouped_review_worker_and_report(self):
        """Real upload, PDF reader, pipeline, checks, queue, metered worker, report.
        Only extraction interpretation and model inference use deterministic fixtures.
        The fixture deliberately establishes one scoped enabling assertion only.
        """
        import fitz
        from apps.extraction.services.pipeline import ExtractionPipeline
        from apps.extraction.services.pdf_reader import PDFPageReader
        from apps.extraction.services.openai_fact_extractor import IdentityAuditFieldMapper
        from apps.extraction.services.openai_client import OpenAIExtractionService
        from apps.extraction.services import stub
        from apps.scoring.models import CapabilityExecution
        from apps.scoring.tasks import run_capability_assessment
        from apps.scoring.capability.recommendations import build_inputs

        self.doc.delete()  # the uploaded synthetic PDF is the only corpus
        pdf = fitz.open()
        for text in (POSITIVE, NEGATIVE):
            page = pdf.new_page(); page.insert_text((50, 70), text, fontsize=9)
        uploaded = SimpleUploadedFile('synthetic-access.pdf', pdf.tobytes(), content_type='application/pdf')
        pdf.close()
        class FixtureExtractor:
            def extract_facts(inner, document, pages):
                return [dict(field_key='computing_access', field_name='Learner access to computing resources',
                    value=value, data_type='number', source_page=str(n), source_snippet=text,
                    confidence_score=0.98, owner_role='iqac_coordinator', pillar='aiqif_c6',
                    fact_kind='context', scope={'period': '2025-26', 'programme': 'engineering'})
                    for n, value, text in ((1, 20, POSITIVE), (2, 0, NEGATIVE))]
        payloads = []
        sdk = MagicMock(); sdk.with_options.return_value = sdk
        def respond(**kwargs):
            payload = json.loads(kwargs['messages'][1]['content']); payloads.append(payload)
            claims = payload['reviewed_evidence']['claims']
            resolved = any(c['value'] == 20 and c['disposition'] == 'confirmed' for c in claims)
            rows = {}
            for c in payload['indicator']['conditions']:
                met = resolved and c['id'] == 'AIQIF-C6.1.F1'
                rows[c['id']] = {'state': 'met' if met else 'unknown',
                    'reason': 'Scoped engineering computing access established.' if met else 'Insufficient evidence for this separate requirement.',
                    'scope_supported': met, 'period_supported': met,
                    'citations': [{'source_id': str(DocumentPage.objects.get(document_id=document_id, page_number=1).pk), 'quote': POSITIVE}] if met else []}
            return SimpleNamespace(model='test-model', usage=SimpleNamespace(prompt_tokens=200, completion_tokens=100,
                prompt_tokens_details=None, completion_tokens_details=None, total_tokens=300),
                choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps({'conditions': rows}), refusal=None))])
        sdk.chat.completions.create.side_effect = respond
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            response = self.client.post(f'/api/v1/sprints/{self.sprint.pk}/upload-file',
                {'file': uploaded, 'document_type': 'naac_ssr', 'owner_role': 'IQAC_COORDINATOR'}, format='multipart')
            self.assertEqual(response.status_code, 201, response.data)
            document_id = response.data['id']
            doc = Document.objects.get(pk=document_id)
            job = ExtractionJob.objects.create(document=doc, sprint=self.sprint)
            pipeline = ExtractionPipeline(page_reader=PDFPageReader(ocr_provider=stub.NullOCRProvider()),
                classifier=stub.KnownMetadataClassifier(), fact_extractor=FixtureExtractor(),
                field_mapper=IdentityAuditFieldMapper(), gap_detector=stub.NullGapDetector(), conflict_checker=stub.NullConflictChecker())
            with patch.object(pipeline, '_ai_check_tags'):
                pipeline.run(job)
            self.assertEqual(ExtractedFact.objects.filter(sprint=self.sprint).count(), 2)
            self.assertEqual(DocumentPage.objects.filter(document=doc).count(), 2)
            batch_response = self.client.post(self.url, {}, format='json')
            self.assertEqual(batch_response.status_code, 201, batch_response.data)
            self.assertEqual(len(batch_response.data['cases']), 1)
            chosen = ExtractedFact.objects.get(sprint=self.sprint, value=20)
            decision = self.client.post(f'{self.url}/{batch_response.data["cases"][0]["id"]}',
                {'action': 'choose', 'fact_id': str(chosen.pk), 'reason': 'Use the supported access record for this programme'}, format='json')
            self.assertEqual(decision.status_code, 200, decision.data)
            run_url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs'
            with patch('apps.scoring.capability.execution.dispatch'):
                response = self.client.post(run_url, {'population': 'Engineering learners', 'reference_period': '2025-26'},
                    format='json', HTTP_IDEMPOTENCY_KEY='synthetic-e2e')
            self.assertEqual(response.status_code, 202, response.data)
            execution = CapabilityExecution.objects.get(run_id=response.data['id'])
            service = OpenAIExtractionService(api_key='sk-fixture', model='test-model', client=sdk)
            with patch('apps.scoring.tasks.get_ai_service', return_value=service), patch('apps.scoring.tasks.get_router_pool', return_value=None):
                run_capability_assessment.run(str(execution.run_id), str(execution.task_id))
            execution.refresh_from_db()
            self.assertEqual(execution.status, 'completed')
            completed = execution.run.events.filter(state='completed').last()
            states = {r['condition_id']: r['state'] for r in completed.payload['records']}
            self.assertEqual(states['AIQIF-C6.1.F1'], 'met')
            self.assertEqual(states['AIQIF-C6.1.F2'], 'unknown')
            self.assertEqual(states['AIQIF-C6.1.A1'], 'unknown')
            self.assertEqual(sum(v == 'met' for v in states.values()), 1)
            inputs = build_inputs(execution.run, completed, {})
            self.assertEqual(inputs['reviewed_evidence']['claims'][0]['sprint_id'], str(self.sprint.pk))
            calls = sdk.chat.completions.create.call_count
            report = self.client.get(f'{run_url}/{execution.run_id}/report?file=json')
            self.assertEqual(report.status_code, 200, getattr(report, 'data', None))
            body = json.loads(report.content)
            self.assertIn('reviewed_evidence', body)
            self.assertTrue(any('claims with their review decisions' in x for x in body['report_view']['limitations']))
            self.assertEqual(sdk.chat.completions.create.call_count, calls)
            detail = self.client.get(f'{run_url}/{execution.run_id}').data
            self.assertFalse(detail['review_changes_since_assessment'])
            chosen.status = 'rejected'; chosen.save()
            self.assertTrue(self.client.get(f'{run_url}/{execution.run_id}').data['review_changes_since_assessment'])
            later = json.loads(self.client.get(f'{run_url}/{execution.run_id}/report?file=json').content)
            later.pop('exported_at'); body.pop('exported_at')
            self.assertEqual(later, body)

    def test_optional_new_corpus_review_never_refills_initial_questions(self):
        old = self.fact()
        batch, _ = start(self.sprint)
        decide(self.sprint, self.user, batch.cases[0]['id'], {'action': 'confirm'})
        new_doc = Document.objects.create(sprint=self.sprint, original_filename='new-access.pdf')
        DocumentPage.objects.create(document=new_doc, page_number=1, text=NEGATIVE)
        new = self.fact(document=new_doc, source_document=new_doc, value=0, source_snippet=NEGATIVE)
        initial_ids = [c['id'] for c in view(self.sprint)['cases']]
        result = self.client.post(self.url, {'optional_follow_up': True}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual([c['id'] for c in result.data['cases']], initial_ids)
        self.assertEqual(len(result.data['overflow']), 1)
        follow = result.data['overflow'][0]
        self.assertEqual(set(follow['fact_ids']), {str(old.pk), str(new.pk)})
        self.assertTrue(follow['conflict'])
        chosen = self.client.post(f'{self.url}/{follow["id"]}',
            {'action': 'choose', 'fact_id': str(new.pk), 'reason': 'New supported scope evidence', 'optional_follow_up': True}, format='json')
        self.assertEqual(chosen.status_code, 200, chosen.data)
        old.refresh_from_db(); self.assertEqual(old.status, 'rejected')

    def test_bounded_source_repair_uses_exact_line_and_retains_history(self):
        f = self.fact(source_snippet='The extraction accidentally quoted another page.')
        start(self.sprint)
        f.refresh_from_db()
        self.assertEqual(f.source_snippet, POSITIVE)
        self.assertEqual(f.status, 'extracted')  # shadow mode unchanged
        h = f.review_history.get(action='source_repaired')
        self.assertEqual(h.decision_source, 'rule')
        self.assertIn('accidentally', h.details['before_quote'])
        self.assertEqual(h.details['after_quote'], POSITIVE)
        self.assertTrue(f.verifications.filter(grounding__quote='not_found').exists())
        self.assertTrue(f.verifications.filter(outcome='verified').exists())

    def test_supported_correction_reaches_payload_with_independent_source(self):
        self.fact(value=0, value_text='0', source_snippet=NEGATIVE)
        self.page.text = NEGATIVE; self.page.save()
        source = Document.objects.create(sprint=self.sprint, original_filename='correcting-source.pdf')
        page = DocumentPage.objects.create(document=source, page_number=1, text=POSITIVE)
        batch, _ = start(self.sprint)
        decide(self.sprint, self.user, batch.cases[0]['id'], {'action': 'correct', 'value': 20,
            'reason': 'Corrected from the explicitly cited programme access record',
            'source_document_id': str(source.pk), 'source_page': '1', 'source_snippet': POSITIVE})
        run = self.run_snapshot()
        claim = run.inputs['reviewed_evidence']['claims'][0]
        self.assertEqual(claim['source']['document_id'], str(source.pk))
        self.assertEqual(claim['verification']['grounding'], 'exact')
        self.assertEqual(claim['verification']['outcome'], 'verified')
        self.assertEqual(claim['decisions'][-1]['action'], 'corrected')
        from apps.scoring.capability.reviewed_evidence import for_context, citation_issue
        sent = for_context(run.inputs['reviewed_evidence'], run.inputs['sources'])
        self.assertEqual(sent['claims'][0]['value'], 20)
        self.assertEqual(sent['claims'][0]['decisions'][-1]['rationale'], 'Corrected from the explicitly cited programme access record')
        self.assertEqual(citation_issue([{'source_id': str(page.pk), 'quote': POSITIVE}], run.inputs['reviewed_evidence'], run.inputs['sources'], state='met'), '')
