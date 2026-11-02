from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from .capability.engine import assess, release
from .capability.evaluation import evaluate, indicator_schema, response_audit, validate_decisions
from .capability.assessment_audit import diagnose


class AssessmentCauseAuditTests(SimpleTestCase):
    def setUp(self):
        self.rubric = release()
        self.indicator = self.rubric['indicators'][0]
        self.ids = [c['id'] for c in self.indicator['conditions']]
        self.sources = [{'id': 'page1', 'text': 'The documented AI strategy names responsible owners and intended beneficiaries.'}]

    def row(self, cid, **extra):
        return {'condition_id': cid, 'state': 'unknown', 'reason': 'The supplied passage does not establish the requirement.',
                'scope_supported': False, 'period_supported': False, 'citations': [], **extra}

    def test_exact_schema_binds_all_condition_ids_and_supplied_source_ids(self):
        schema = indicator_schema(self.indicator, self.sources)
        array = schema['properties']['conditions']
        self.assertEqual(array['minItems'], 6)
        self.assertEqual(array['maxItems'], 6)
        self.assertEqual(array['items']['properties']['condition_id']['enum'], self.ids)
        self.assertEqual(array['items']['properties']['citations']['items']['properties']['source_id']['enum'], ['page1'])
        from jsonschema import validate, ValidationError
        with self.assertRaises(ValidationError):
            validate({'conditions': [self.row(self.ids[0])]}, schema)
        with self.assertRaises(ValidationError):
            validate({'conditions': [self.row(cid) for cid in self.ids[:-1]] + [self.row('made-up')]}, schema)
        validate({'conditions': [self.row(cid) for cid in self.ids]}, schema)

    def test_rejected_candidate_and_missing_ids_remain_auditable_but_never_score(self):
        bad = self.row(self.ids[0], state='met', scope_supported=True, period_supported=True,
                       citations=[{'source_id': 'page1', 'quote': 'A fabricated quotation not present in the supplied page.'}])
        response = {'conditions': [bad]}
        validated = validate_decisions(self.indicator, response, self.sources)
        audit = response_audit(self.indicator, response, validated)
        self.assertEqual(len(audit['missing_ids']), 5)
        self.assertEqual(audit['returned_decisions'], 1)
        self.assertEqual(audit['model_response']['conditions'][0]['citations'], bad['citations'])
        self.assertTrue(all(r['state'] == 'unknown' for r in validated))
        self.assertTrue(all(not r['citations'] for r in validated))
        self.assertEqual(len(audit['validation_issues']), 6)

    def test_evaluation_passes_exact_schema_and_keeps_response_snapshot(self):
        outer = self
        class Fake:
            def extract_structured_data(self, **kwargs):
                ids = kwargs['response_schema']['properties']['conditions']['items']['properties']['condition_id']['enum']
                return {'conditions': [outer.row(cid) for cid in ids]}
        before = deepcopy(self.sources)
        evaluated = evaluate(self.sources, service=Fake(), population='Institution', reference_period='Source-specific')
        self.assertEqual(evaluated['indicator_calls'], 36)
        self.assertEqual(len(evaluated['records']), 216)
        self.assertTrue(all(t['response_audit']['returned_decisions'] == 6 for t in evaluated['traces']))
        self.assertFalse(any(t['response_audit']['missing_ids'] for t in evaluated['traces']))
        self.assertTrue(all(t['schema_hash'] != t['schema_template_hash'] for t in evaluated['traces']))
        self.assertTrue(all(t['schema_binding_version'] == 'indicator-ids-and-source-ids-0.1' for t in evaluated['traces']))
        self.assertEqual(self.sources, before)

    def fixture(self):
        records = [self.row(c['id']) for i in self.rubric['indicators'] for c in i['conditions']]
        records[0]['reason'] = 'Quote does not match a supplied source passage.'
        records[0]['validation_issue'] = ''  # Historic export bug: fixed reason survived.
        assessment = {'records': records, 'traces': [], 'result': assess({r['condition_id']: r['state'] for r in records}, self.rubric)}
        return {'run_id': 'synthetic', 'rubric': self.rubric, 'assessment': assessment,
                'source_manifest': [{'pages': [{'status': 'ok'}]}]}

    def test_historic_diagnostic_loss_is_recovered_without_changing_decisions(self):
        report = self.fixture()
        original = deepcopy(report)
        result = diagnose(report['assessment'], rubric=report['rubric'], manifest=report['source_manifest'])
        self.assertEqual(result['validator_affected_conditions'], 1)
        self.assertEqual(result['unknown_without_validator_issue'], 215)
        self.assertEqual(result['legacy_issue_fields_recovered'], 1)
        self.assertEqual(len(result['foundation_blockers']), 36)
        self.assertEqual(report, original)

    def test_duplicate_saved_records_are_not_a_complete_audit_contract(self):
        report = self.fixture()
        report['assessment']['records'].append(deepcopy(report['assessment']['records'][0]))
        result = diagnose(report['assessment'], rubric=report['rubric'])
        self.assertFalse(result['record_contract']['complete'])
        self.assertTrue(result['record_contract']['duplicate_ids'])

    def test_execution_problems_are_distinct_from_invalid_responses(self):
        report = self.fixture()
        record = report['assessment']['records'][0]
        record['validation_issue'] = 'No readable source context. Capability is unknown.'
        result = diagnose(report['assessment'], rubric=report['rubric'])
        self.assertEqual(result['validator_affected_conditions'], 0)
        self.assertEqual(result['evaluation_unavailable_conditions'], 1)

    def test_offline_command_replays_without_model_calls_and_refuses_overwrite(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / 'export.json'
            target = Path(tmp) / 'diagnosis.json'
            source.write_text(json.dumps(self.fixture()))
            call_command('audit_capability_export', str(source), output=str(target), stdout=StringIO())
            result = json.loads(target.read_text())
            self.assertTrue(result['arithmetic_replay_matches'])
            self.assertEqual(result['state_counts']['unknown'], 216)
            with self.assertRaises(CommandError):
                call_command('audit_capability_export', str(source), output=str(target), stdout=StringIO())
