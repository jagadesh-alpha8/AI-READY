from copy import deepcopy
from django.test import SimpleTestCase, TestCase
from django.core.management import call_command, CommandError
from io import StringIO
import json

from apps.facts.catalogue import canonical_type, identity
from apps.facts.models import ExtractedFact
from apps.institutions.models import Institution
from apps.sprints.models import Sprint
from apps.documents.models import Document
from .models import ExtractionJob, ExtractionSnapshot, DocumentPage
from .services.openai_fact_extractor import _merge_fact
from .services.pipeline import ExtractionPipeline
from .observations import compare, freeze


def observation(value=42, period='2025-26', key='total_faculty'):
    return {'field_key': key, 'field_name': 'Faculty', 'value': value, 'normalized_value': value,
            'data_type': 'number', 'source_page': '1', 'source_snippet': f'{value} faculty {period}',
            'scope': {'period': period, 'population': 'whole institution', 'unit': 'count'},
            'confidence_score': .95, 'aiqif_mappings': []}


class ObservationIdentityTests(SimpleTestCase):
    def test_exact_aliases_share_concepts_without_guessing_new_categories(self):
        self.assertEqual(canonical_type('Total Faculty'), 'faculty_count')
        self.assertEqual(canonical_type('ai_research_strategy'), '')
        self.assertEqual(identity(observation()), identity(observation(key='faculty_count')))

    def test_periods_populations_units_and_contradictory_values_do_not_collapse(self):
        first = observation()
        variants = [observation(period='2024-25'), observation(43)]
        for part, value in [('population', 'CSE'), ('unit', 'thousands')]:
            variant = deepcopy(first); variant['scope'][part] = value; variants.append(variant)
        merged = {}
        for row in [first, *variants]:
            _merge_fact(merged, row)
        self.assertEqual(len(merged), 5)


class ObservationSnapshotTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='College', city='X', state='Y')
        self.sprint = Sprint.objects.create(institution=institution)
        self.doc = Document.objects.create(sprint=self.sprint, original_filename='ssr.pdf', checksum='same')
        DocumentPage.objects.create(document=self.doc, page_number=1, text='42 faculty across the college in 2025-26')
        self.job = ExtractionJob.objects.create(sprint=self.sprint, document=self.doc, completeness='complete', status='completed')

    def test_snapshots_are_idempotent_and_separate_from_reviewed_facts(self):
        facts = [observation()]
        freeze(self.job, facts); freeze(self.job, facts)
        self.assertEqual(ExtractionSnapshot.objects.count(), 1)
        with self.assertRaises(ValueError):
            ExtractionSnapshot.objects.update(payload={})
        ExtractionPipeline._persist_facts(self.job, facts)
        fact = ExtractedFact.objects.get()
        fact.value = 99; fact.status = 'corrected'; fact.save()
        self.assertEqual(ExtractionSnapshot.objects.get().payload['facts'][0]['value'], 42)
        output = StringIO(); call_command('extraction_observations', job=str(self.job.pk), stdout=output)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload['facts'][0]['value'], 42)
        self.assertEqual(payload['category_candidates']['unmapped_keys'], {})
        with self.assertRaises(ValueError):
            compare(payload, payload)

    def test_scoped_persistence_keeps_periods_and_conflicts_and_reuses_exact_observations(self):
        rows = [observation(), observation(period='2024-25'), observation(43)]
        ExtractionPipeline._persist_facts(self.job, rows)
        self.assertEqual(ExtractedFact.objects.count(), 3)
        ExtractionPipeline._persist_facts(self.job, rows)
        self.assertEqual(ExtractedFact.objects.count(), 3)

    def test_independent_extraction_comparison_reports_observation_changes(self):
        freeze(self.job, [observation()])
        first = ExtractionSnapshot.objects.get().payload
        second_job = ExtractionJob.objects.create(sprint=self.sprint, document=self.doc, completeness='complete', status='completed')
        freeze(second_job, [observation(key='faculty_count'), observation(43)])
        second = ExtractionSnapshot.objects.filter(job=second_job).get().payload
        report = compare(first, second)
        self.assertEqual(report['observation_jaccard'], .5)
        second['inputs']['pages_hash'] = 'changed'
        with self.assertRaises(ValueError):
            compare(first, second)
