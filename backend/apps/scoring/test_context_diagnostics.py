"""Capability request construction: offline measurement, preserved review semantics and target behaviours.

Synthetic data only. The reference-run suite at the end reads a private export named by
CAPABILITY_REFERENCE_EXPORT and is skipped without it; never commit an institutional export.

The three construction behaviours (page-wide claim association, repeated quotation/review
detail, whole-ledger recommendation requests) are fixed since A1 f76fbcb and tested directly.
Corpus-scale tests pin the fixed bound for conflicts spanning many
documents, and advice labelling. Remove a marker when its fix lands; an unexpected success
fails the suite.
"""
import hashlib
import json
import os
import tempfile
import unittest
from copy import deepcopy
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.extraction.models import AIUsage, DocumentPage
from apps.extraction.services.openai_client import OpenAIExtractionService
from apps.facts.models import ExtractedFact
from . import test_capability_api as fixtures
from .capability import context_diagnostics as diag
from .capability.engine import release
from .capability.evaluation import PROMPT_VERSION, SYSTEM_PROMPT, evaluate
from .capability.recommendation_execution import generate_recommendations
from .capability.reviewed_evidence import citation_issue, for_context
from .capability.storage import checkpoint, create_run, publish
from .models import CapabilityExecution, CapabilityRunEvent, RecommendationEvent, RecommendationExecution
from apps.scoring.capability.storage import frozen_sources

DOC = '00000000-0000-0000-0000-00000000d0c1'
FILLER = ('Administrative records were filed with the registrar and archived according to the retention schedule. ' * 40)


def page(number, text, document=DOC):
    return {'id': f'{document[-4:]}-page-{number}', 'document_id': document, 'page_number': number,
            'text': text, 'text_source': 'pdf'}


def claim(cid, page_number, quote, *, value='recorded', original_value=None, original_quote=None, disposition='extracted',
          decisions=(), attribute='synthetic_attribute', document=DOC):
    return {'id': cid, 'revision': '2026-01-01T00:00:00+00:00', 'institution_id': 'institution', 'sprint_id': 'sprint',
            'attribute': attribute, 'label': attribute.replace('_', ' ').title(), 'value': value,
            'original_value': value if original_value is None else original_value, 'value_origin': 'extracted',
            'scope': {'period': '2024-25', 'population': ['whole institution']}, 'kind': 'evidence',
            'verification': {'outcome': 'verified', 'grounding': 'exact', 'validation': 'pass', 'automation': 'review'},
            'disposition': disposition,
            'source': {'document_id': document, 'version': 1, 'current': True, 'page': str(page_number), 'quote': quote},
            'original_source': {'document_id': document, 'page': str(page_number),
                                'quote': quote if original_quote is None else original_quote},
            'decisions': list(decisions)}


def decision(action, before, after, rationale=''):
    return {'id': f'decision-{action}', 'actor_id': 'reviewer', 'timestamp': '2026-01-02T00:00:00+00:00', 'action': action,
            'decision_source': 'person', 'before': before, 'after': after, 'rationale': rationale, 'details': {}}


STRATEGY = 'The governing council approved the institutional plan identifying digital and AI priorities for 2024-25.'
OUTSIDE = 'The council also recorded that the digital priority register was updated by the planning office.'
CORRECTED = 'The approved budget allocation for the AI laboratory was 40 lakhs in 2024-25.'
SUPERSEDED = 'The approved budget allocation for the AI laboratory was 30 lakhs in 2024-25.'
REJECTED = 'The AI laboratory was closed for the whole of 2024-25 pending renovation work.'
ALLOWANCE_ISSUE = 'Reviewed-evidence context exceeds the bounded input allowance. Capability is unknown; no model request was made.'


def fixture():
    """Two selected pages carrying a correction, a rejected alternative, an unresolved conflict and duplicates."""
    pages = [page(1, STRATEGY + ' ' + FILLER + OUTSIDE),
             page(2, CORRECTED + ' ' + REJECTED + ' Student strength was 1200 in 2024-25.'),
             page(9, 'Hostel maintenance schedule for the summer vacation period.')]
    context = [{**pages[0], 'text': pages[0]['text'][:600], 'text_offset': 0}, {**pages[1], 'text_offset': 0}]
    claims = [
        claim('c-anchored', 1, STRATEGY, disposition='confirmed', decisions=[decision('confirmed', 'recorded', 'recorded')]),
        claim('c-page-only', 1, OUTSIDE),
        claim('c-corrected', 2, CORRECTED, value='40 lakhs', original_value='30 lakhs', original_quote=SUPERSEDED,
              disposition='corrected', attribute='ai_lab_budget',
              decisions=[decision('confirmed', '30 lakhs', '30 lakhs'), decision('evidence_requested', '30 lakhs', '30 lakhs'),
                         decision('correction_proposed', '30 lakhs', '40 lakhs'),
                         decision('corrected', '30 lakhs', '40 lakhs', 'Audited statement gives 40 lakhs.')]),
        claim('c-rejected', 2, REJECTED, disposition='rejected', attribute='ai_lab_status',
              decisions=[decision('rejected', 'closed', 'closed', 'Renovation notice concerns a different building.')]),
        claim('c-students-a', 1, STRATEGY, value=1100, attribute='student_count'),
        claim('c-students-b', 2, 'Student strength was 1200 in 2024-25.', value=1200, attribute='student_count'),
        claim('c-duplicate-1', 2, CORRECTED, value='40 lakhs', attribute='ai_lab_budget_repeat'),
        claim('c-duplicate-2', 2, CORRECTED, value='40 lakhs', attribute='ai_lab_budget_repeat'),
        claim('c-far', 9, 'Hostel maintenance schedule for the summer vacation period.'),
    ]
    issues = [
        {'id': 'conflict-open', 'kind': 'conflict', 'status': 'open', 'claim_ids': ['c-students-a', 'c-students-b'],
         'rationale': '', 'title': 'Student count differs', 'alternatives_at_detection': [1100, 1200], 'events': []},
        {'id': 'conflict-resolved', 'kind': 'conflict', 'status': 'resolved', 'claim_ids': ['c-corrected'],
         'rationale': 'Audited statement gives 40 lakhs.', 'title': 'Budget differs', 'alternatives_at_detection': ['30 lakhs', '40 lakhs'],
         'events': [{'id': 'event-1', 'action': 'resolved', 'rationale': 'Audited statement gives 40 lakhs.'}]},
        {'id': 'unconfirmed-page-only', 'kind': 'unconfirmed_fact', 'status': 'open', 'claim_ids': ['c-page-only'],
         'rationale': '', 'title': 'Needs confirmation: register update', 'alternatives_at_detection': [None, None], 'events': []},
    ]
    batch = {'id': 'batch', 'cases': [
        {'id': 'identity', 'kind': 'identity', 'question': 'Which institution?', 'scope': {}, 'fact_ids': [],
         'affected_requirements': [], 'initial': True},
        {'id': 'case-budget', 'question': 'Which budget figure applies?', 'scope': {'period': '2024-25'},
         'fact_ids': ['c-corrected'], 'affected_requirements': ['AIQIF-C1.3.F1'], 'initial': True}],
        'decisions': {'case-budget': {'id': 'decision-case-budget', 'action': 'correct', 'claim_ids': ['c-corrected'],
                                    'rationale': 'Audited statement gives 40 lakhs.'}}}
    ledger = {'version': 'reviewed-evidence-1', 'claims': claims, 'issues': issues, 'review_batch': batch}
    return pages, context, ledger


def indicator(code='AIQIF-C1.1'):
    return next(i for i in release()['indicators'] if i['code'] == code)


def request_for(context, ledger, code='AIQIF-C1.1', projection=for_context):
    return diag.evaluation_request(indicator(code), context, ledger=ledger, scope=None, projection=projection,
                                   population='Institutional overview', reference_period='Source-specific')


class Recorder:
    """Stands in for the provider: records each request and answers every requirement unknown."""

    def __init__(self):
        self.requests = []

    def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name):
        self.requests.append({'system': system_prompt, 'user': user_content, 'schema': response_schema})
        ids = response_schema['properties']['conditions']['required']
        return {'conditions': {cid: {'state': 'unknown', 'reason': 'Not established in the supplied passages.',
                                     'scope_supported': False, 'period_supported': False, 'citations': []} for cid in ids}}


class Forbidden:
    def extract_structured_data(self, **kwargs):
        raise AssertionError('No provider request may be made.')


class MeasurementTests(SimpleTestCase):
    def test_rebuilt_request_is_byte_identical_to_what_evaluate_sends(self):
        pages, _, ledger = fixture()
        recorder = Recorder()
        rubric = {'indicators': [indicator()]}
        result = evaluate(pages, service=recorder, population='Institutional overview', reference_period='Source-specific',
                          rubric=rubric, reviewed_evidence=ledger)
        trace = result['traces'][0]
        rebuilt = request_for(trace['source_excerpts'], ledger)
        self.assertEqual(rebuilt['payload'], recorder.requests[0]['user'])
        self.assertEqual(rebuilt['input_hash'], trace['input_hash'])
        self.assertEqual(rebuilt['schema'], recorder.requests[0]['schema'])

    def test_gemini_omits_only_citation_enums_and_still_validates_quotes(self):
        pages, _, ledger = fixture()

        class GeminiRecorder(Recorder):
            provider = 'gemini'

            def extract_structured_data(self, **kwargs):
                response = super().extract_structured_data(**kwargs)
                for cid, source_id in zip(response['conditions'], ('outside-packet', pages[0]['id'])):
                    response['conditions'][cid].update(
                        state='met', scope_supported=True, period_supported=True,
                        citations=[{'source_id': source_id, 'quote': 'This quotation was fabricated.'}],
                    )
                return response

        recorder = GeminiRecorder()
        item = indicator()
        result = evaluate(pages, service=recorder, population='Institutional overview', reference_period='Source-specific',
                          rubric={'indicators': [item]}, reviewed_evidence=ledger)
        trace = result['traces'][0]
        expected = diag.indicator_schema(item, trace['source_excerpts'])
        for decision in expected['properties']['conditions']['properties'].values():
            del decision['properties']['citations']['items']['properties']['source_id']['enum']
        self.assertEqual(recorder.requests[0]['schema'], expected)
        self.assertEqual(trace['schema_binding_version'], 'required-condition-properties-gemini-0.3')
        self.assertEqual(len(recorder.requests), 2)
        self.assertTrue(all(r['state'] == 'unknown' for r in result['records']))
        for request in recorder.requests:
            for decision in request['schema']['properties']['conditions']['properties'].values():
                citation = decision['properties']['citations']['items']
                self.assertEqual(citation['properties']['source_id'], {'type': 'string'})
                self.assertIn('source_id', citation['required'])
        self.assertEqual(sum(bool(r['validation_issue']) for r in result['records']), 2)

    def test_named_parts_account_for_every_user_message_character(self):
        _, context, ledger = fixture()
        request = request_for(context, ledger)
        parts = diag.components(request)
        user = sum(v for k, v in parts.items() if k not in ('instructions', 'schema_in_instructions', 'response_schema'))
        self.assertEqual(user, len(request['payload']))
        self.assertLess(parts['user_framing'], 400)
        self.assertEqual(parts['instructions'] + parts['schema_in_instructions'], len(request['system']))
        self.assertGreater(parts['schema_in_instructions'], 0, 'OpenAI-compatible requests repeat the schema in the instructions.')

    def test_counts_repetition_and_anchoring_under_the_previous_page_projection(self):
        _, context, ledger = fixture()
        request = request_for(context, ledger, projection=diag.page_projection)
        self.assertEqual(diag.counts(request), {'windows': 2, 'pages': 2, 'claims': 8, 'issues': 3, 'conflicts': 2,
                                                'review_cases': 2, 'case_decisions': 1, 'review_answers': 0})
        repetition = diag.repetition(request)
        self.assertEqual(repetition['original_quotation_equals_current'], 7)
        self.assertEqual(repetition['repeated_quotations'], 3)
        self.assertEqual(repetition['duplicate_claim_records'], 1)
        self.assertEqual(repetition['current_quotation_inside_supplied_window'], 7)
        anchoring = diag.anchoring(request)
        self.assertEqual((anchoring['anchored_claims'], anchoring['page_only_claims']), (7, 1))
        self.assertEqual(anchoring['issues_only_via_page_only_claims'], 1)

    def test_counts_repetition_and_anchoring_under_the_current_construction(self):
        _, context, ledger = fixture()
        request = request_for(context, ledger)
        self.assertEqual(diag.counts(request), {'windows': 2, 'pages': 2, 'claims': 7, 'issues': 2, 'conflicts': 2,
                                                'review_cases': 0, 'case_decisions': 0, 'review_answers': 1})
        repetition = diag.repetition(request)
        self.assertEqual((repetition['original_quotation_equals_current'], repetition['repeated_quotations'],
                          repetition['current_quotation_inside_supplied_window']), (0, 0, 0))
        self.assertEqual(repetition['duplicate_claim_records'], 1)
        anchoring = diag.anchoring(request)
        self.assertEqual((anchoring['anchored_claims'], anchoring['page_only_claims']), (7, 0))
        self.assertGreater(diag.components(request)['passage_references'], 0)

    def test_current_prompt_hash_and_projection_are_exact(self):
        self.assertIs(diag.projection_for(PROMPT_VERSION), for_context)
        self.assertEqual(diag.system_prompt_for(hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()), SYSTEM_PROMPT)
        self.assertIsNone(diag.system_prompt_for('0' * 64))

    def test_large_review_ledger_is_bounded_without_blocking_evaluation(self):
        pages, _, ledger = fixture()
        ledger['claims'] += [claim(f'c-bulk-{n}', 1, STRATEGY, value=n) for n in range(150)]
        result = evaluate(pages, service=Recorder(), population='Institutional overview', reference_period='Source-specific',
                          rubric={'indicators': [indicator()]}, reviewed_evidence=ledger)
        trace = result['traces'][0]
        self.assertTrue(trace['model_call_attempted'])
        review = for_context(ledger, trace['source_excerpts'])
        self.assertLessEqual(len(json.dumps(review)), 24000)
        self.assertGreater(review['omissions']['matching_claims'], 0)
        self.assertEqual(len(ledger['claims']), 159)

    def test_unknown_causes_distinguish_processing_from_evidence(self):
        unknown = {'state': 'unknown', 'reason': 'No record was supplied.', 'validation_issue': ''}
        self.assertEqual(diag.condition_cause(unknown, {'error': ''}), 'model_unknown:insufficient_in_supplied_windows')
        self.assertEqual(diag.condition_cause({**unknown, 'reason': 'The reporting period is not stated.'}, {'error': ''}),
                         'model_unknown:scope_or_period_heuristic')
        self.assertEqual(diag.condition_cause({**unknown, 'validation_issue': 'Quote does not match a supplied source passage.'},
                                              {'error': ''}), 'validation_rejected')
        self.assertEqual(diag.condition_cause(unknown, {'error': 'Model evaluation failed (Timeout). Capability is unknown.'}),
                         'provider_failure')
        self.assertEqual(diag.condition_cause(unknown, {'error': 'Evaluation call budget reached. Capability is unknown.'}),
                         'not_evaluated:call_budget')
        self.assertEqual(diag.condition_cause({**unknown, 'state': 'met'}, {'error': ''}), 'decided:met')

    def test_token_figures_keep_actual_estimate_and_bound_apart(self):
        self.assertIsNone(diag.calibration([]))
        calibrated = diag.calibration([(3200, 1000), (3000, 1000), (3400, 1000)])
        self.assertEqual(calibrated['bytes_per_token'], 3.2)
        kwargs = diag.provider_kwargs('system', 'user', {'type': 'object'}, 'name', model='m', settings={'max_tokens': 3000})
        self.assertEqual(diag.envelope_input_bound(kwargs),
                         len(json.dumps(kwargs, ensure_ascii=False).encode()) + diag.ENVELOPE_FRAMING_TOKENS)


class ReviewPreservationTests(SimpleTestCase):
    """Must keep holding as construction changes: selection or compaction never loses review semantics."""

    def test_selection_keeps_corrections_rejections_conflicts_and_resolutions(self):
        _, context, ledger = fixture()
        review = for_context(ledger, context)
        claims = {c['id']: c for c in review['claims']}
        self.assertEqual(claims['c-corrected']['original_value'], '30 lakhs')
        self.assertIn('original_source', claims['c-corrected'])
        self.assertEqual([(d['action'], d['rationale']) for d in claims['c-corrected']['decisions']],
                         [('corrected', 'Audited statement gives 40 lakhs.')])
        self.assertEqual(claims['c-rejected']['disposition'], 'rejected')
        issues = {i['id']: i for i in review['issues']}
        self.assertEqual(issues['conflict-open']['status'], 'open')
        self.assertEqual(issues['conflict-resolved']['rationale'], 'Audited statement gives 40 lakhs.')
        self.assertEqual([a['id'] for a in review['review_answers']], ['decision-case-budget'])
        self.assertNotIn('c-far', claims)

    def test_off_window_alternative_of_an_applicable_conflict_is_kept_but_not_citable_support(self):
        _, context, ledger = fixture()
        ledger['claims'].append(claim('c-students-far', 9, 'Student strength was 900 in 2024-25.', value=900,
                                      disposition='rejected', attribute='student_count'))
        ledger['issues'][0]['claim_ids'].append('c-students-far')
        far = {c['id']: c for c in for_context(ledger, context)['claims']}['c-students-far']
        self.assertEqual(far['disposition'], 'rejected')
        self.assertFalse(far['source']['source_support_in_selected_passages'])

    def test_rejected_and_superseded_quotations_stay_uncitable(self):
        # evaluate() validates against the full frozen ledger, not the projected packet.
        _, context, ledger = fixture()
        cite = lambda quote: [{'source_id': context[1]['id'], 'quote': quote}]
        self.assertTrue(citation_issue(cite(REJECTED), ledger, context, state='met'))
        self.assertTrue(citation_issue(cite(SUPERSEDED), ledger, context, state='met'))
        self.assertTrue(citation_issue(cite('Student strength was 1200 in 2024-25.'), ledger, context, state='met'))
        self.assertEqual(citation_issue(cite(CORRECTED), ledger, context, state='met'), '')


class ConstructionBehaviourTests(SimpleTestCase):
    """The three construction behaviours, each measured independently (fixed in A1 f76fbcb)."""

    def test_selected_excerpt_brings_only_supported_claims_or_conflict_alternatives(self):
        _, context, ledger = fixture()
        anchoring = diag.anchoring(request_for(context, ledger))
        self.assertEqual(anchoring['unsupported_unconnected_claims'], 0)
        self.assertEqual(diag.anchoring(request_for(context, ledger, projection=diag.page_projection))['unsupported_unconnected_claims'], 1)

    def test_quotations_and_review_detail_are_not_repeated(self):
        _, context, ledger = fixture()
        request = request_for(context, ledger)
        parts = diag.components(request)
        self.assertEqual((parts['current_quotations'], parts['original_quotations']), (0, 0))
        self.assertEqual(diag.repetition(request)['original_quotation_equals_current'], 0)
        self.assertLess(parts['review_history'], diag.components(request_for(context, ledger, projection=diag.page_projection))['review_history'])

    def test_recommendation_request_carries_only_its_own_windows_evidence(self):
        pages, ledger = corpus(10)
        plan = advice_plan(ledger, pages)
        plan['actions'][0]['citations'] = [{'source_id': pages[1]['id'], 'quote': 'x'}]
        rows = diag.recommendation_requests(plan, pages, release())['batches']
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row['unsupported_unconnected_claims'], 0)
            self.assertLess(row['ledger_claims'], row['page_projection_ledger_claims'])


def advice_plan(ledger, pages, indicator_code='AIQIF-C1.3'):
    """Minimal recommendation inputs: one documented shortfall citing page 2, so a model batch exists."""
    condition = indicator(indicator_code)['conditions'][0]
    cited = next(p for p in pages if p['page_number'] == 2)
    return {'profile': {'name': 'Synthetic College'}, 'population': 'Institutional overview', 'reference_period': 'Source-specific',
            'reviewed_evidence': ledger, 'scope': {'mode': 'default'}, 'foundation_plan': {},
            'actions': [{'id': condition['id'], 'indicator': indicator_code, 'type': 'develop_capability',
                         'operation': 'develop_and_verify', 'requirement': condition['text'], 'completion_evidence': 'x',
                         'state': 'not_met', 'reason': 'Documented shortfall.', 'automatic_points': False,
                         'citations': [{'source_id': cited['id'], 'quote': CORRECTED}]}]}


def corpus(documents):
    """Synthetic corpus of `documents` three-page PDFs with ledger claims on every page.

    Each document also states its student count, so the snapshot's corpus reconciliation yields
    one open conflict naming every such claim, as reviewed_evidence.snapshot() does.
    """
    pages, claims = [], []
    for d in range(documents):
        doc = f'00000000-0000-0000-0000-{d:012d}'
        for p in (1, 2, 3):
            lead = (f'Report {d} page {p}. The governing council approved the institutional plan identifying digital and AI '
                    f'priorities, a budget allocation for the AI laboratory and faculty AI training in 2024-25.')
            tail = f'Student strength recorded in report {d} was {1000 + d} in 2024-25.'
            # The student count sits beside the relevant text, so any window retrieval picks there includes it.
            pages.append(page(p, lead + ' ' + tail + ' ' + FILLER[:2500], document=doc))
            claims.append(claim(f'c-{d}-{p}-plan', p, lead, document=doc))
            claims.append(claim(f'c-{d}-{p}-budget', p, lead, attribute='ai_lab_budget', document=doc))
        claims.append(claim(f'c-{d}-students', 1, tail, value=1000 + d, attribute='student_count', document=doc))
    issues = [{'id': 'corpus-conflict:students', 'kind': 'conflict', 'status': 'open',
               'claim_ids': [c['id'] for c in claims if c['attribute'] == 'student_count'], 'rationale': ''}]
    return pages, {'version': 'reviewed-evidence-1', 'claims': claims, 'issues': issues, 'review_batch': None}


class CorpusScaleTests(SimpleTestCase):
    """One offline 200-PDF simulation; every individual request must stay bounded as the corpus grows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rubric = {'indicators': [indicator('AIQIF-C1.1'), indicator('AIQIF-C1.3')]}
        cls.runs = {}
        for documents in (10, 200):
            pages, ledger = corpus(documents)
            recorder = Recorder()
            result = evaluate(pages, service=recorder, population='Institutional overview', reference_period='Source-specific',
                              rubric=cls.rubric, reviewed_evidence=ledger)
            cls.runs[documents] = {'pages': pages, 'ledger': ledger, 'recorder': recorder, 'result': result}

    def sizes(self, documents):
        return [len(r['system']) + len(r['user']) for r in self.runs[documents]['recorder'].requests]

    @staticmethod
    def without_conflict(ledger):
        return {**ledger, 'issues': [i for i in ledger['issues'] if i['id'] != 'corpus-conflict:students']}

    def test_every_batch_is_evaluated_at_10_pdfs(self):
        self.assertTrue(all(t['model_call_attempted'] for t in self.runs[10]['result']['traces']))

    def test_cross_document_conflict_does_not_block_batches_at_200_pdfs(self):
        # Fails since f76fbcb: every alternative of an applicable conflict joins the packet, here one claim per document.
        self.assertTrue(all(t['model_call_attempted'] for t in self.runs[200]['result']['traces']))

    def test_same_excerpts_cost_the_same_when_unrelated_documents_are_added(self):
        # corpus(200) extends corpus(10) with 190 further documents; the selected excerpts stay fixed.
        context = self.runs[10]['result']['traces'][0]['source_excerpts']
        small = request_for(context, self.runs[10]['ledger'])
        large = request_for(context, self.runs[200]['ledger'])
        self.assertLessEqual(abs(len(large['payload']) - len(small['payload'])), 1024)
        self.assertLessEqual(len(json.dumps(large['review'])), 24000)

    def test_growth_comes_from_the_cross_document_conflict_alone(self):
        context = self.runs[10]['result']['traces'][0]['source_excerpts']
        small = request_for(context, self.without_conflict(self.runs[10]['ledger']))
        large = request_for(context, self.without_conflict(self.runs[200]['ledger']))
        self.assertEqual(large['payload'], small['payload'])
        grown = request_for(context, self.runs[200]['ledger'])
        unsupported = [c for c in grown['review']['claims'] if not c['source']['source_support_in_selected_passages']]
        self.assertTrue(all(c['attribute'] == 'student_count' for c in unsupported))
        self.assertTrue(any(i.get('omitted_alternatives', 0) for i in grown['review']['issues']))
        self.assertEqual(diag.anchoring(grown)['unsupported_unconnected_claims'], 0)

    def test_sent_evaluation_requests_stay_within_a_fixed_ceiling(self):
        # 18,000 source characters + 32,000 ledger characters + rubric, scope, schema and instructions.
        self.assertLess(max(self.sizes(10) + self.sizes(200)), 100_000)

    def test_recommendation_request_size_does_not_grow_with_the_corpus(self):
        # Advice batches select their own windows now, but the same conflict alternatives still join them.
        sizes = {}
        for documents in (10, 200):
            run = self.runs[documents]
            plan = advice_plan(run['ledger'], run['pages'], indicator_code='AIQIF-C1.3')
            plan['actions'][0]['citations'] = [{'source_id': run['pages'][1]['id'], 'quote': 'x'}]
            rows = diag.recommendation_requests(plan, run['pages'], {'indicators': [indicator('AIQIF-C1.3')]})['batches']
            sizes[documents] = max(r['user_chars'] for r in rows)
        self.assertLessEqual(sizes[200], sizes[10] * 1.05)

    def test_rejected_alternatives_survive_selection_at_scale(self):
        run = self.runs[200]
        ledger = deepcopy(run['ledger'])
        trace = run['result']['traces'][0]
        chosen = trace['source_excerpts'][0]
        ledger['claims'].append(claim('c-rejected-in-window', chosen['page_number'], chosen['text'][:120],
                                      disposition='rejected', document=chosen['document_id']))
        review = {c['id']: c for c in for_context(ledger, trace['source_excerpts'])['claims']}
        self.assertEqual(review['c-rejected-in-window']['disposition'], 'rejected')
        self.assertTrue(review['c-rejected-in-window']['source']['source_support_in_selected_passages'])


# Database-backed: production request paths, export and history immutability.
@override_settings(SECURE_SSL_REDIRECT=False, CAPABILITY_RECOMMENDATIONS_ENABLED=True,
    CAPABILITY_MAX_HTTP_CALLS=72, CAPABILITY_MAX_COST_USD='2', CAPABILITY_OUTPUT_TOKENS=3000,
    CAPABILITY_REQUEST_TIMEOUT_SECONDS=60, AI_RATE_LIMIT_ENABLED=False, AI_PROCESSING_MODE='single',
    AI_BASE_URL='', AI_TEMPERATURE=0, AI_SEED=42,
    AI_PRICING_JSON='{"test-model":{"input":0.1,"output":0.2}}')
class ProductionPathTests(APITestCase):
    def setUp(self):
        fixtures.CapabilityAPITests.setUp(self)
        document = self.page.document
        ExtractedFact.objects.create(sprint=self.sprint, document=document, field_key='faculty_count', value=40,
                                     source_page='1', source_snippet='Current institutional evidence for every faculty')
        DocumentPage.objects.create(document=document, page_number=2, text='Hostel maintenance schedule for the summer.')
        ExtractedFact.objects.create(sprint=self.sprint, document=document, field_key='hostel_rooms', value=12,
                                     source_page='2', source_snippet='Hostel maintenance schedule')
        self.run = create_run(institution_id=self.institution.pk, sprint_id=self.sprint.pk,
                              population='All faculty and students', reference_period='2025-26')
        checkpoint(institution_id=self.institution.pk, run_id=self.run.pk, state='running')
        evaluation = evaluate([], service=None, population='All', reference_period='2025-26')
        self.blocked = evaluation['records'][0]['condition_id']
        for row in evaluation['records']:
            if row['condition_id'] == self.blocked:
                row.update(reason=ALLOWANCE_ISSUE, validation_issue=ALLOWANCE_ISSUE)
            else:
                row.update(state='not_met', reason='Scoped documented shortfall', validation_issue='', scope_supported=True,
                           period_supported=True, citations=[{'source_id': str(self.page.pk), 'quote': self.page.text}])
        publish(institution_id=self.institution.pk, run_id=self.run.pk, evaluation=evaluation,
                inference={'provider': 'none', 'model': 'none', 'settings': {}, 'calls': []})
        CapabilityExecution.objects.create(run=self.run, sprint=self.sprint, status='completed',
                                           idempotency_key=str(self.run.pk), request_hash=self.run.inputs_hash)
        self.url = f'/api/v1/sprints/{self.sprint.pk}/capability-runs/{self.run.pk}'
        self.sent = []

    def response(self, **kwargs):
        user = kwargs['messages'][1]['content']
        self.sent.append(user)
        rows = [{'condition_id': a['id'], 'operation': a['operation'], 'steps': ['Develop and verify ' + a['requirement']],
                 'suggested_role': 'Coordinator (suggested)', 'effort': 'unknown', 'dependencies': [],
                 'completion_evidence': 'Verify ' + str(a['completion_evidence']), 'basis': a['citations']}
                for a in json.loads(user)['actions']]
        return SimpleNamespace(model='actual-test-model',
            usage=SimpleNamespace(prompt_tokens=200, completion_tokens=150, prompt_tokens_details=None,
                                  completion_tokens_details=None, total_tokens=350),
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps({'advice': rows}), refusal=None))])

    def tailor(self):
        with patch('apps.scoring.capability.recommendation_execution.dispatch'):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(f'{self.url}/recommendations', {}, format='json', HTTP_IDEMPOTENCY_KEY='advice-1')
        self.assertEqual(response.status_code, 202, response.data)
        execution = RecommendationExecution.objects.get(snapshot_id=response.data['id'])
        service = OpenAIExtractionService(api_key='sk-test', model='test-model', client=self.sdk)
        with patch('apps.scoring.capability.recommendation_execution.get_ai_service', return_value=service), patch(
                'apps.scoring.capability.recommendation_execution.get_router_pool', return_value=None):
            generate_recommendations.run(str(execution.snapshot_id), str(execution.task_id))
        execution.refresh_from_db()
        self.assertEqual(execution.status, 'completed')
        return execution

    def advice(self):
        return self.tailor().snapshot.events.filter(payload__kind='completed').last().payload['advice']

    def test_rebuilt_recommendation_requests_match_what_production_sends(self):
        execution = self.tailor()
        rebuilt = diag.recommendation_requests(execution.snapshot.inputs, frozen_sources(self.run), self.run.inputs['rubric'])['batches']
        self.assertEqual([r['payload_hash'] for r in rebuilt], [hashlib.sha256(u.encode()).hexdigest() for u in self.sent])
        self.assertTrue(all(r['unsupported_unconnected_claims'] == 0 for r in rebuilt))

    def test_request_replay_is_independent_of_jsonb_object_key_order(self):
        execution = self.tailor()
        # PostgreSQL JSONB reorders object keys; arrays and values are unchanged.
        reordered_plan = json.loads(json.dumps(execution.snapshot.inputs, sort_keys=True))
        reordered_sources = json.loads(json.dumps(frozen_sources(self.run), sort_keys=True))
        rebuilt = diag.recommendation_requests(reordered_plan, reordered_sources, self.run.inputs['rubric'])['batches']
        self.assertEqual([r['payload_hash'] for r in rebuilt], [hashlib.sha256(u.encode()).hexdigest() for u in self.sent])

    def test_inspection_and_export_make_no_model_calls_and_change_no_history(self):
        execution = self.tailor()
        calls = self.sdk.chat.completions.create.call_count
        history = lambda: (list(CapabilityRunEvent.objects.filter(run=self.run).values_list('id', 'payload')),
                           list(RecommendationEvent.objects.values_list('id', 'payload')), AIUsage.objects.count())
        before = history()
        self.sdk.chat.completions.create.side_effect = AssertionError('No provider request may be made.')
        with tempfile.TemporaryDirectory() as folder:
            response = self.client.get(f'{self.url}/report', {'file': 'json', 'recommendation_id': str(execution.snapshot_id)})
            self.assertEqual(response.status_code, 200)
            exported = Path(folder) / 'export.json'
            exported.write_bytes(response.content)
            call_command('capability_context_report', str(exported), '--database', '--output-dir',
                         str(Path(folder) / 'report'), stdout=StringIO())
            report = json.loads((Path(folder) / 'report' / 'diagnostics.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report['analysis']['batches']), 36)
        # This fixture publishes hand-built traces, not ones evaluated from the frozen inputs; the report must say so.
        self.assertFalse(any(b['input_hash_matches'] or b['retrieval_replayed'] for b in report['analysis']['batches']))
        self.assertTrue(report['scoring']['matches_saved_result'])
        self.assertEqual(report['pipeline']['ingestion']['pages'], 2)
        self.assertEqual(report['pipeline']['interval']['upper'], report['scoring']['upper'])
        self.assertEqual(self.sdk.chat.completions.create.call_count, calls)
        self.assertEqual(history(), before)

    def test_oracle_check_sends_nothing_without_send_and_uses_the_configured_service_with_it(self):
        execution = self.tailor()
        response = self.client.get(f'{self.url}/report', {'file': 'json', 'recommendation_id': str(execution.snapshot_id)})
        before = list(CapabilityRunEvent.objects.filter(run=self.run).values_list('id', 'payload'))
        with tempfile.TemporaryDirectory() as folder:
            exported, gold = Path(folder) / 'export.json', Path(folder) / 'gold.json'
            exported.write_bytes(response.content)
            gold.write_text(json.dumps([{'indicator': 'AIQIF-C1.3', 'page': 1, 'quote': 'Current institutional evidence'}]), encoding='utf-8')
            with patch('apps.extraction.services.ai_service.get_ai_service', side_effect=AssertionError('No provider client.')):
                call_command('capability_oracle_check', str(exported), '--gold', str(gold), '--output-dir',
                             str(Path(folder) / 'dry'), stdout=StringIO())
            dry = json.loads((Path(folder) / 'dry' / 'oracle.json').read_text(encoding='utf-8'))
            recorder = Recorder()
            with patch('apps.extraction.services.ai_service.get_ai_service', return_value=recorder):
                call_command('capability_oracle_check', str(exported), '--gold', str(gold), '--send', '--output-dir',
                             str(Path(folder) / 'sent'), stdout=StringIO())
            sent = json.loads((Path(folder) / 'sent' / 'oracle.json').read_text(encoding='utf-8'))
        self.assertFalse(dry['sent'])
        self.assertEqual((dry['summary']['requests'], dry['plan'][0]['labelled_windows_found']), (1, 1))
        self.assertEqual(len(recorder.requests), 1)
        self.assertIn('Current institutional evidence', recorder.requests[0]['user'])
        self.assertEqual(sent['labelled_credited'], {'saved': 0, 'oracle': 0, 'of': 1})
        self.assertEqual(list(CapabilityRunEvent.objects.filter(run=self.run).values_list('id', 'payload')), before)

    def test_gold_evidence_needs_the_frozen_page_text(self):
        with tempfile.TemporaryDirectory() as folder:
            export, gold = Path(folder) / 'export.json', Path(folder) / 'gold.json'
            export.write_text('{}', encoding='utf-8')
            gold.write_text('[]', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('capability_context_report', str(export), '--gold', str(gold), '--output-dir', str(Path(folder) / 'out'))

    def test_report_is_never_written_inside_the_repository(self):
        with self.assertRaises(CommandError):
            call_command('capability_context_report', 'unused.json', '--output-dir', str(Path(settings.BASE_DIR) / 'diagnostics'))

    def test_every_advice_item_declares_whether_it_is_deterministic_or_model_tailored(self):
        origins = diag.advice_origins(self.advice())
        self.assertNotIn('unlabelled', origins)
        self.assertGreater(origins.get('model_tailored', 0), 0)

    def test_unevaluated_requirement_is_not_advised_as_missing_institutional_evidence(self):
        item = next(a for a in self.advice() if a['condition_id'] == self.blocked)
        self.assertEqual(item['origin'], 'processing_rerun')
        self.assertFalse(any(step.startswith('Request evidence') for step in item['steps']))
        self.assertTrue(all(json.loads(u)['actions'] and self.blocked not in u for u in self.sent))

    def test_invalid_advice_is_repaired_without_discarding_valid_neighbours(self):
        answer = self.response
        def first_batch_invalid(**kwargs):
            response = answer(**kwargs)
            if len(self.sent) == 1:  # the first batch answers with an unsupported citation
                body = json.loads(response.choices[0].message.content)
                body['advice'][0]['basis'] = [{'source_id': 'not-supplied', 'quote': 'A quotation no supplied passage holds.'}]
                response.choices[0].message.content = json.dumps(body)
            return response
        self.sdk.chat.completions.create.side_effect = first_batch_invalid
        advice = self.advice()
        origins = diag.advice_origins(advice)
        fallback = [a for a in advice if a['origin'] == 'deterministic_fallback']
        self.assertEqual(fallback, [])
        repair = json.loads(self.sent[1])
        self.assertEqual(len(repair['actions']), 1)
        self.assertIn(repair['actions'][0]['id'], repair['validation_errors'])
        self.assertGreater(origins.get('model_tailored', 0), 0)


class AdviceBasisTests(SimpleTestCase):
    """A basis may quote a passage supplied with the request verbatim; nothing else outside the action's citations."""
    action = {'id': 'AIQIF-C1.3.F1', 'type': 'supply_evidence', 'operation': 'gather_evidence', 'citations': []}
    sources = [{'id': 'page-7', 'text': 'The governing council approved the AI laboratory budget for 2024-25.'}]

    def answer(self, quote, source_id='page-7'):
        return {'advice': [{'condition_id': self.action['id'], 'operation': 'gather_evidence', 'steps': ['Check the budget.'],
                            'suggested_role': 'Finance officer (suggested)', 'effort': 'small', 'dependencies': [],
                            'completion_evidence': 'An approved budget record.', 'basis': [{'source_id': source_id, 'quote': quote}]}]}

    def test_verbatim_quotation_of_a_supplied_passage_is_accepted(self):
        from .capability.recommendations import validate_advice
        rows = validate_advice(self.answer('approved the AI laboratory   budget'), [self.action], sources=self.sources)
        self.assertEqual(len(rows), 1)

    def test_paraphrase_wrong_source_or_unsupplied_quotation_is_rejected(self):
        from .capability.recommendations import validate_advice
        for quote, source in (('The council funded an AI lab', 'page-7'), ('approved the AI laboratory budget', 'page-9'),
                              ('approved the AI laboratory budget', 'page-7')):
            with self.subTest(quote=quote, source=source):
                with self.assertRaises(ValueError):
                    validate_advice(self.answer(quote, source), [self.action],
                                    sources=self.sources if (quote, source) != ('approved the AI laboratory budget', 'page-7') else [])


@unittest.skipUnless(os.environ.get('CAPABILITY_REFERENCE_EXPORT'), 'Set CAPABILITY_REFERENCE_EXPORT to a private export path.')
class ReferenceRunTests(SimpleTestCase):
    """Offline reproduction of a saved run. Generic assertions only: the export itself stays private."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.export = json.loads(Path(os.environ['CAPABILITY_REFERENCE_EXPORT']).read_text(encoding='utf-8'))
        cls.analysis = diag.analyse(cls.export)

    def test_every_indicator_payload_reproduces_its_saved_input_hash(self):
        self.assertTrue(all(b['input_hash_matches'] for b in self.analysis['batches']))

    def test_every_provider_request_reproduces_its_saved_request_hash(self):
        sent = [e for b in self.analysis['batches'] for e in b['provider_requests']]
        reserved = [c for c in self.export['assessment']['inference']['calls'] if c['kind'] == 'request_reserved']
        self.assertEqual(len(sent), len(reserved))
        self.assertTrue(all(e['request_hash_matches'] for e in sent))

    def test_blocked_batches_are_exactly_those_over_the_allowance_and_sent_nothing(self):
        for batch in self.analysis['batches']:
            blocked = batch['pre_request_limit'] == 'reviewed_evidence_allowance'
            self.assertEqual(blocked, batch['ledger_chars_as_gated'] > diag.REVIEWED_EVIDENCE_ALLOWANCE)
            self.assertEqual(blocked, not batch['model_call_attempted'])
            self.assertEqual(blocked, batch['saved_error'].startswith('Reviewed-evidence context exceeds'))

    def test_saved_decisions_replay_to_the_reported_score_bounds(self):
        replay = diag.replay_scoring(self.export)
        self.assertTrue(replay['matches_saved_result'])
        self.assertEqual((replay['lower'], replay['upper']), (replay['saved_lower'], replay['saved_upper']))

    def test_every_decision_has_one_explained_cause(self):
        causes = diag.cause_summary(self.export)['causes']
        self.assertEqual(sum(causes.values()), len(self.export['assessment']['records']))
        self.assertNotIn('provider_failure', causes)

    def test_previous_recommendation_construction_attached_the_whole_ledger(self):
        whole = diag.page_projection(self.export['reviewed_evidence'], diag.manifest_sources(self.export['source_manifest']))
        self.assertEqual(len(whole['claims']), len(self.export['reviewed_evidence']['claims']))

    def test_current_construction_blocks_no_batch_on_the_same_windows(self):
        self.assertEqual([b['indicator'] for b in self.analysis['batches'] if b['current_construction']['pre_request_limit']], [])
