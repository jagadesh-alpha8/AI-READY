"""Synthetic coverage for incomplete model decisions and bounded correction."""
import json
from copy import deepcopy
from unittest import TestCase
from .capability.engine import release, assess
from .capability.evaluation import evaluate, indicator_schema, validate_decisions


class ResponseContractRepairTests(TestCase):
    def setUp(self):
        self.indicator = next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C6.1')
        self.rubric = {**release(), 'indicators': [self.indicator]}
        self.quote = 'During 2024-25, Synthetic College learners had access to institutional computers.'
        self.sources = [{'id': 'synthetic-page', 'text': self.quote}]

    def row(self, state='unknown', **extra):
        return dict(state=state, reason='Synthetic scoped evidence.' if state == 'met' else 'Not established.',
            scope_supported=state == 'met', period_supported=state == 'met',
            citations=[{'source_id': 'synthetic-page', 'quote': self.quote}] if state == 'met' else [], **extra)

    def run_service(self, service):
        return evaluate(self.sources, service=service, population='Synthetic College learners',
                        reference_period='2024-25', rubric=self.rubric)

    def test_keyed_schema_requires_every_named_decision(self):
        import jsonschema
        schema = indicator_schema(self.indicator, self.sources)
        ids = schema['properties']['conditions']['required']
        response = {'conditions': {cid: self.row() for cid in ids}}
        jsonschema.validate(response, schema)
        del response['conditions'][ids[0]]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(response, schema)

    def test_incomplete_response_is_corrected_once_and_grounded_credit_survives(self):
        outer = self
        calls = []
        class Service:
            def extract_structured_data(self, **kwargs):
                payload = json.loads(kwargs['user_content']); calls.append(payload)
                ids = kwargs['response_schema']['properties']['conditions']['required']
                if len(calls) == 1:
                    return {'conditions': {ids[-1]: outer.row()}}
                return {'conditions': {cid: outer.row('met' if cid.endswith('.F1') else 'unknown') for cid in ids}}
        result = self.run_service(Service())
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[1]['indicator']['conditions']), 5)
        self.assertEqual(result['correction_calls'], 1)
        self.assertEqual(result['decisions']['AIQIF-C6.1.F1'], 'met')
        self.assertFalse(any(r['validation_issue'] for r in result['records']))
        trace = result['traces'][0]
        self.assertEqual(len(trace['initial_response_audit']['missing_ids']), 5)
        self.assertEqual(trace['correction_response_audit']['missing_ids'], [])
        self.assertEqual(trace['response_assembly'], 'validated_initial_plus_correction')

    def test_valid_initial_decisions_are_not_changed_by_correction(self):
        outer = self
        calls = []
        class Service:
            def extract_structured_data(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    return {'conditions': {'AIQIF-C6.1.F1': outer.row('met')}}
                ids = kwargs['response_schema']['properties']['conditions']['required']
                # An unsolicited replacement must not overwrite the verified initial record.
                return {'conditions': {**{cid: outer.row() for cid in ids}, 'AIQIF-C6.1.F1': outer.row()}}
        result = self.run_service(Service())
        self.assertEqual(result['decisions']['AIQIF-C6.1.F1'], 'met')
        self.assertNotIn('AIQIF-C6.1.F1', calls[1]['response_schema']['properties']['conditions']['required'])

    def test_failed_correction_is_not_an_infinite_retry_or_automatic_credit(self):
        calls = []
        class Service:
            def extract_structured_data(self, **kwargs):
                calls.append(kwargs)
                return {'state': 'met', 'condition_id': 'AIQIF-C6.1.F1'}
        result = self.run_service(Service())
        self.assertEqual(len(calls), 2)
        self.assertEqual(set(result['decisions'].values()), {'unknown'})
        self.assertTrue(all(r['validation_issue'] for r in result['records']))

    def test_valid_unknowns_do_not_trigger_paid_correction(self):
        outer = self
        calls = []
        class Service:
            def extract_structured_data(self, **kwargs):
                calls.append(kwargs)
                return {'conditions': {cid: outer.row() for cid in kwargs['response_schema']['properties']['conditions']['required']}}
        result = self.run_service(Service())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['correction_calls'], 0)

    def test_invalid_quote_cannot_score_even_after_correction(self):
        outer = self
        class Service:
            def extract_structured_data(self, **kwargs):
                rows = {cid: outer.row() for cid in kwargs['response_schema']['properties']['conditions']['required']}
                cid = next(iter(rows))
                rows[cid] = outer.row('met')
                rows[cid]['citations'][0]['quote'] = 'A made-up passage that does not occur in any supplied evidence.'
                return {'conditions': rows}
        result = self.run_service(Service())
        self.assertEqual(set(result['decisions'].values()), {'unknown'})

    def test_keyed_value_cannot_override_its_required_identity(self):
        rows = validate_decisions(self.indicator, {'conditions': {'AIQIF-C6.1.F1': self.row('met', condition_id='AIQIF-C6.1.F2')}}, self.sources)
        self.assertTrue(all(r['state'] == 'unknown' for r in rows))


class JSONBoundaryTests(TestCase):
    def test_complete_fenced_or_prose_wrapped_response_still_parses(self):
        from apps.extraction.services.openai_client import _loads_lenient
        self.assertEqual(_loads_lenient('```json\n{"conditions": {}}\n```'), {'conditions': {}})
        self.assertEqual(_loads_lenient('Result: {"conditions": {}} Done.'), {'conditions': {}})

    def test_duplicate_members_and_truncated_outer_values_are_never_salvaged(self):
        from apps.extraction.services.openai_client import _loads_lenient
        for text in ['{"conditions": [1], "conditions": [2]}',
                     '{"conditions": [{"state": "met"}',
                     '{"conditions": []} {"conditions": []}',
                     '{"conditions": {"same": {}, "same": {}}}']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                _loads_lenient(text)

    def test_compatible_provider_corrects_duplicate_keys_instead_of_dropping_decisions(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from django.test import override_settings
        from apps.extraction.services.openai_client import OpenAIExtractionService
        sdk = MagicMock()
        def completion(content):
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason='stop',
                message=SimpleNamespace(content=content))])
        sdk.chat.completions.create.side_effect = [completion('{"conditions": [1], "conditions": [2]}'),
                                                   completion('{"conditions": {"a": {"state": "unknown"}}}')]
        with override_settings(AI_RATE_LIMIT_ENABLED=False):
            service = OpenAIExtractionService(api_key='synthetic-key', model='synthetic-model',
                client=sdk, base_url='https://synthetic.example/v1')
            response = service.extract_structured_data(system_prompt='Return decisions', user_content='Synthetic data',
                response_schema={'type': 'object'}, schema_name='synthetic')
        self.assertEqual(sdk.chat.completions.create.call_count, 2)
        self.assertEqual(response['conditions']['a']['state'], 'unknown')
