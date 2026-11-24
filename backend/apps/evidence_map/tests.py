"""The evidence map's tagging (pull request 1): the request, the checks on answers, the stored rows and the pass.

A stand-in tagger answers instead of a model; it reads the page markers of each request the way a model must, and can
be told to misbehave the ways real answers do (a page left out, a truncated answer, wrong IDs, a miscopied quotation,
a transient failure).
"""
import json
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.documents.models import Document
from apps.extraction.exceptions import AIOutputTruncated, PermanentExtractionError, RecoverableExtractionError
from apps.extraction.models import AIUsage, DocumentPage
from apps.extraction.usage import _save
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from . import spec, tagging
from .models import MapJob, MapPage

ERP = 'The institution has partnered with e-Varsity ERP to digitise data on students, faculty and staff.'
SYLLABUS = 'Course Objectives: Unit I Financial Auditing. Text Books: Auditing principles. Reference Books: ISO audit.'
COVER = 'Self-Study Report. Table of contents.'


class Tagger:
    """A stand-in model. `misbehave` names what to do wrong, and how many times."""
    model, base_url = 'claude-haiku-5-5', None

    def __init__(self, **misbehave):
        self.misbehave = dict(misbehave)
        self.calls = []

    def _once(self, name):
        if self.misbehave.get(name):
            self.misbehave[name] -= 1
            return True
        return False

    def extract_structured_data(self, *, system_prompt, user_content, response_schema, schema_name, **kwargs):
        assert response_schema == spec.SCHEMA and schema_name == spec.SCHEMA_NAME
        self.calls.append({'system': system_prompt, 'user': user_content})
        if 'cost' in self.misbehave:
            _save(provider='anthropic', model=self.model, input_tokens=self.misbehave['cost'], output_tokens=0)
        if self._once('transient'):
            raise RecoverableExtractionError('slow down', retry_after=0)
        if self._once('permanent'):
            raise PermanentExtractionError('bad request')
        pages = re.findall(r'^--- Page (\d+) ---\n(.*?)(?=^--- Page |\Z)', user_content, re.M | re.S)
        if len(pages) > 1 and self._once('truncate'):
            raise AIOutputTruncated('too long')
        rows = []
        for number, text in pages:
            tags = []
            if 'e-Varsity ERP' in text and 'C6.2' in system_prompt:
                quote = 'partnered with e-Varsity ERP to digitise data' if not self.misbehave.get('miscopy') else \
                    'partnered with eVarsity to digitize records'
                tags.append({'indicator': 'C6.2', 'requirements': ['C6.2.F1', 'C8.1.F1', 'C99.9.F9'],
                             'strength': 'direct', 'quote': quote, 'reason': 'An ERP holding institutional data.'})
            if 'Financial Auditing' in text and 'C9.2' in system_prompt:
                tags.append({'indicator': 'C9.2', 'requirements': ['C9.2.F1'], 'strength': 'topical', 'quote': '',
                             'reason': 'A course that teaches auditing.'})
                tags.append({'indicator': 'Z1', 'requirements': [], 'strength': 'direct', 'quote': 'Unit I',
                             'reason': 'Unknown indicator.'})
            page_type = 'syllabus_or_course_content' if 'Course Objectives' in text else 'report_narrative'
            rows.append({'page': int(number), 'page_type': page_type, 'tags': tags})
        if rows and self._once('omit'):
            rows = rows[:-1]
        return {'pages': rows}


def rubric():
    return spec.rubric_sources()[0]


class ChunkAndRequestTests(SimpleTestCase):
    def test_chunks_keep_pages_whole_and_in_order(self):
        pages = [{'number': n, 'text': 'x' * size} for n, size in enumerate([5000, 5000, 5000, 15000, 100], 1)]
        groups = spec.chunks(pages)
        self.assertEqual([[p['number'] for p in g] for g in groups], [[1, 2], [3], [4], [5]])
        self.assertTrue(all(sum(len(p['text']) for p in g) <= spec.CHUNK_CHARS or len(g) == 1 for g in groups))

    def test_the_request_names_the_document_and_marks_context_only_text(self):
        content = spec.user_content({'filename': 'SSR.pdf', 'type': 'naac_ssr', 'pages': 187},
                                    [{'number': 12, 'text': ERP}], {'number': 11, 'text': 'y' * 1000 + ' END'})
        self.assertIn('DOCUMENT: SSR.pdf', content)
        self.assertIn('Pages in the document: 187', content)
        self.assertIn('Context only, do not tag (end of page 11):', content)
        self.assertLessEqual(len(content.split('Context only')[1].split('--- Page')[0]), spec.CARRY_CHARS + 60)
        self.assertIn('--- Page 12 ---\n' + ERP, content)
        first = spec.user_content({'filename': 'a.pdf'}, [{'number': 1, 'text': ERP}])
        self.assertNotIn('Context only', first)

    def test_the_rubric_reaches_the_tagger_whole_or_by_area(self):
        rubric_, profiles, parts = spec.rubric_sources()
        whole = spec.system_prompts('one', rubric_, profiles, parts)
        by_area = spec.system_prompts('areas', rubric_, profiles, parts)
        ids = [spec.short(c['id']) for i in rubric_['indicators'] for c in i['conditions']]
        self.assertEqual(len(whole), 1)
        self.assertTrue(all(f'REQUIREMENT {cid}:' in whole[0][1] for cid in ids))
        self.assertEqual(len(by_area), 9)
        self.assertEqual(sum(p.count('REQUIREMENT ') for _, p in by_area), 216)
        self.assertTrue(all(p.startswith(spec.PROMPT) for _, p in whole + by_area))
        # The record-language descriptions and the parts' near-misses are there; the judge's rules are not.
        self.assertIn('Records that show it:', whole[0][1])
        self.assertIn('Not enough:', whole[0][1])
        self.assertNotIn('NAAC', spec.PROMPT)

    def test_the_map_version_follows_what_decides_a_tags_meaning_not_the_model(self):
        rubric_, profiles, parts = spec.rubric_sources()
        one = spec.map_version('one', rubric_, profiles, parts)
        self.assertEqual(one, spec.map_version('one', rubric_, profiles, parts))
        self.assertNotEqual(one, spec.map_version('areas', rubric_, profiles, parts))
        with patch.object(spec, 'PROMPT', spec.PROMPT + ' '):
            self.assertNotEqual(one, spec.map_version('one', rubric_, profiles, parts))
        changed = {**profiles, 'AIQIF-C1.1.F1': {**profiles['AIQIF-C1.1.F1'], 'query': 'Another description.'}}
        self.assertNotEqual(one, spec.map_version('one', rubric_, changed, parts))


class CheckTests(SimpleTestCase):
    def check(self, rows, pages=None):
        pages = pages or [{'number': 4, 'text': ERP}, {'number': 5, 'text': SYLLABUS}]
        return spec.validate(pages, {'pages': rows}, rubric())

    def test_requirements_go_to_their_own_indicator_and_unknown_ids_are_dropped(self):
        got = self.check([{'page': 4, 'page_type': 'report_narrative', 'tags': [
            {'indicator': 'C6.2', 'requirements': ['C6.2.F1', 'c8.1.f1', 'C99.9.F9'], 'strength': 'direct',
             'quote': 'partnered with e-Varsity ERP', 'reason': 'ERP.'}]}])
        tags = got['pages'][4]['tags']
        self.assertEqual({t['indicator']: t['requirements'] for t in tags},
                         {'AIQIF-C6.2': ['AIQIF-C6.2.F1'], 'AIQIF-C8.1': ['AIQIF-C8.1.F1']})
        self.assertEqual((got['counts']['requirement_moved'], got['counts']['requirement_unknown']), (1, 1))
        self.assertEqual(got['missing'], [5])

    def test_an_unknown_indicator_is_taken_from_its_requirements_or_dropped(self):
        got = self.check([{'page': 4, 'page_type': 'other', 'tags': [
            {'indicator': 'C42', 'requirements': ['C6.2.F2'], 'strength': 'supporting', 'quote': '', 'reason': ''},
            {'indicator': 'Z1', 'requirements': [], 'strength': 'direct', 'quote': 'ERP', 'reason': ''}]}])
        self.assertEqual([t['indicator'] for t in got['pages'][4]['tags']], ['AIQIF-C6.2'])
        self.assertEqual((got['counts']['indicator_from_requirements'], got['counts']['indicator_unknown']), (1, 1))

    def test_a_miscopied_quotation_keeps_its_tag(self):
        got = self.check([{'page': 4, 'page_type': 'report_narrative', 'tags': [
            {'indicator': 'C6.2', 'requirements': [], 'strength': 'direct', 'quote': 'eVarsity digitize records',
             'reason': ''},
            {'indicator': 'C8.1', 'requirements': [], 'strength': 'supporting',
             'quote': 'partnered   with e-Varsity\nERP', 'reason': ''}]}])
        tags = got['pages'][4]['tags']
        self.assertEqual([t['quote_found'] for t in tags], [False, True])
        self.assertEqual((got['counts']['quote_not_found'], got['counts']['quote_found']), (1, 1))

    def test_topical_tags_need_no_quotation_and_repeats_and_strays_are_dropped(self):
        tag = {'indicator': 'C9.2', 'requirements': ['C9.2.F1'], 'strength': 'topical', 'quote': '', 'reason': 'x'}
        got = self.check([{'page': 5, 'page_type': 'not_a_type', 'tags': [tag, dict(tag)]},
                          {'page': 9, 'page_type': 'other', 'tags': []}])
        self.assertEqual(len(got['pages'][5]['tags']), 1)
        self.assertEqual(got['pages'][5]['page_type'], 'other')
        self.assertEqual((got['counts']['tag_repeated'], got['counts']['pages_not_asked'],
                          got['counts']['quote_missing']), (1, 1, 0))

    def test_area_answers_merge_by_page(self):
        a = {'page_type': 'report_narrative', 'tags': [{'indicator': 'AIQIF-C1.1', 'requirements': [],
                                                        'strength': 'direct', 'quote': 'q', 'quote_found': True,
                                                        'reason': ''}]}
        b = {'page_type': 'other', 'tags': []}
        merged = spec.merge([a, b, dict(a)])
        self.assertEqual((merged['page_type'], len(merged['tags'])), ('report_narrative', 1))


class SprintMixin:
    def make_sprint(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        ssr = Document.objects.create(sprint=self.sprint, document_type='naac_ssr', original_filename='SSR.pdf',
                                      page_count=4)
        syllabi = Document.objects.create(sprint=self.sprint, document_type='syllabus',
                                          original_filename='Syllabi.pdf', page_count=2)
        texts = [COVER, ERP + ' ' + 'a' * 7000, 'Minutes of the council. ' + 'b' * 7000, 'Annual report. ' + 'c' * 300]
        for n, text in enumerate(texts, 1):
            DocumentPage.objects.create(document=ssr, page_number=n, text=text)
        DocumentPage.objects.create(document=syllabi, page_number=1, text=SYLLABUS)
        DocumentPage.objects.create(document=syllabi, page_number=2, text='  ' + COVER.upper() + '  ')  # same text
        DocumentPage.objects.create(document=syllabi, page_number=3, text='', status='unreadable')


@override_settings(EVIDENCE_MAP_MAX_COST_USD=5)
class PassTests(SprintMixin, TestCase):
    def setUp(self):
        self.make_sprint()

    def run_pass(self, tagger, **options):
        return tagging.run(self.sprint, service=tagger, concurrency=1, **options)

    def test_a_pass_tags_every_distinct_page_once(self):
        tagger = Tagger()
        job = self.run_pass(tagger)
        self.assertEqual((job.status, job.pages_total, job.pages_to_tag, job.pages_tagged, job.pages_failed),
                         ('completed', 6, 5, 5, 0))
        self.assertEqual(MapPage.objects.count(), 5)   # the cover repeated in the syllabus file is tagged once
        erp = MapPage.objects.get(text_hash=spec.text_hash(ERP + ' ' + 'a' * 7000))
        self.assertEqual(erp.page_type, 'report_narrative')
        self.assertEqual({t['indicator'] for t in erp.tags}, {'AIQIF-C6.2', 'AIQIF-C8.1'})
        self.assertTrue(all(t['quote_found'] for t in erp.tags))
        syllabus = MapPage.objects.get(text_hash=spec.text_hash(SYLLABUS))
        self.assertEqual([t['strength'] for t in syllabus.tags], ['topical'])
        self.assertEqual(job.checks.get('indicator_unknown'), 1)
        # Requests never split a page, carry the previous page as context only, and send the frozen page text.
        self.assertEqual(len(tagger.calls), job.requests)
        self.assertTrue(any('Context only, do not tag (end of page 2):' in c['user'] for c in tagger.calls))
        self.assertTrue(any(ERP in c['user'] for c in tagger.calls))

    def test_a_second_pass_sends_nothing_already_tagged(self):
        self.run_pass(Tagger())
        tagger = Tagger()
        job = self.run_pass(tagger)
        self.assertEqual((job.pages_to_tag, job.requests, len(tagger.calls)), (0, 0, 0))

    def test_a_page_left_out_is_asked_again_once_on_its_own(self):
        tagger = Tagger(omit=1)
        job = self.run_pass(tagger)
        self.assertEqual((job.pages_tagged, job.pages_failed), (5, 0))
        self.assertEqual(job.checks.get('pages_missing'), 1)
        retry = tagger.calls[1]['user']
        self.assertEqual(len(re.findall(r'^--- Page ', retry, re.M)), 1)

    def test_a_truncated_answer_is_asked_again_in_halves(self):
        tagger = Tagger(truncate=1)
        job = self.run_pass(tagger)
        self.assertEqual((job.pages_tagged, job.pages_failed), (5, 0))
        self.assertEqual(job.checks.get('truncated_split'), 1)

    def test_failures_are_recorded_and_retried_on_the_next_pass(self):
        job = self.run_pass(Tagger(transient=1))
        self.assertEqual(job.pages_failed, 0)    # one transient failure is retried
        MapPage.objects.all().delete()
        job = self.run_pass(Tagger(permanent=1))
        self.assertEqual(job.status, 'completed')
        self.assertGreater(job.pages_failed, 0)
        failed = MapPage.objects.filter(status='failed')
        self.assertTrue(failed.exists() and all('bad request' in r.error for r in failed))
        again = self.run_pass(Tagger())
        self.assertEqual(again.pages_to_tag, job.pages_failed)
        self.assertFalse(MapPage.objects.filter(status='failed').exists())

    def test_a_failure_never_replaces_a_tagged_page(self):
        self.run_pass(Tagger())
        first = MapPage.objects.get(text_hash=spec.text_hash(SYLLABUS))
        job = MapJob.objects.first()
        tagging.save(job, [{'id': 'x', 'number': 1, 'text': SYLLABUS}], {1: {'error': 'later failure'}})
        first.refresh_from_db()
        self.assertEqual((first.status, first.error), ('tagged', ''))

    def test_the_area_shape_asks_each_area_and_merges(self):
        tagger = Tagger()
        job = self.run_pass(tagger, shape='areas')
        chunks = job.chunks_total
        self.assertEqual(job.requests, 9 * chunks)
        erp = MapPage.objects.get(text_hash=spec.text_hash(ERP + ' ' + 'a' * 7000), map_version=job.map_version)
        self.assertEqual({t['indicator'] for t in erp.tags}, {'AIQIF-C6.2', 'AIQIF-C8.1'})

    def test_the_spend_cap_stops_new_requests(self):
        tagger = Tagger(cost=10_000_000)   # $1 a request at Claude Haiku 5.5's input price
        job = self.run_pass(tagger, max_cost_usd=0.5)
        self.assertEqual(job.status, 'stopped')
        self.assertEqual(len(tagger.calls), 1)
        self.assertGreaterEqual(job.spend_usd, Decimal('0.5'))
        self.assertTrue(AIUsage.objects.filter(sprint=self.sprint, stage='evidence_map').exists())
        self.assertLess(MapPage.objects.filter(status='tagged').count(), 5)

    def test_a_pilot_can_take_one_document_and_a_few_pages(self):
        job = self.run_pass(Tagger(), documents=['syllabi'], limit_pages=1)
        self.assertEqual((job.pages_to_tag, job.pages_tagged), (1, 1))

    def test_a_miscopied_quotation_is_stored_as_not_found(self):
        self.run_pass(Tagger(miscopy=True))
        erp = MapPage.objects.get(text_hash=spec.text_hash(ERP + ' ' + 'a' * 7000))
        self.assertTrue(erp.tags and not any(t['quote_found'] for t in erp.tags))


class CommandTests(SprintMixin, TestCase):
    def setUp(self):
        self.make_sprint()

    def test_dry_run_sends_and_writes_nothing(self):
        from io import StringIO
        out = StringIO()
        with patch.object(tagging, 'tagger_service', side_effect=AssertionError('no client in a dry run')), \
                override_settings(EVIDENCE_MAP_AI_API_KEY='', CAPABILITY_AI_API_KEY='', AI_MODEL='claude-haiku-5-5'):
            call_command('evidence_map_tag', str(self.sprint.pk), '--dry-run', stdout=out)
        self.assertIn('5 to tag', out.getvalue())
        self.assertFalse(MapJob.objects.exists() or MapPage.objects.exists())

    def test_tag_then_export(self):
        from io import StringIO
        with patch.object(tagging, 'tagger_service', return_value=Tagger()):
            call_command('evidence_map_tag', str(self.sprint.pk), '--concurrency', '1', stdout=StringIO())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'map.json'
            call_command('evidence_map_export', str(self.sprint.pk), '--output', str(target), stdout=StringIO())
            data = json.loads(target.read_text())
        self.assertEqual(data['coverage']['tagged'], 6)       # the repeated cover counts for both its pages
        self.assertEqual(data['coverage']['unreadable'], 1)
        self.assertEqual(len(data['pages']), 6)
        self.assertIn(len(SYLLABUS), [p['chars'] for p in data['pages']])
        self.assertEqual(data['prompt'], spec.PROMPT)
        self.assertTrue(any(t['indicator'] == 'AIQIF-C6.2' for p in data['pages'] for t in p['tags']))
        with self.assertRaises(CommandError):
            from django.conf import settings
            call_command('evidence_map_export', str(self.sprint.pk), '--output',
                         str(Path(settings.BASE_DIR) / 'map.json'), stdout=StringIO())


class ServiceTests(SimpleTestCase):
    @override_settings(EVIDENCE_MAP_AI_API_KEY='sk-ant-test', EVIDENCE_MAP_AI_MODEL='claude-haiku-5-5',
                       EVIDENCE_MAP_AI_BASE_URL='', EVIDENCE_MAP_AI_EFFORT='low')
    def test_its_own_key_and_model_with_json_output(self):
        service = tagging.tagger_service()
        self.assertEqual((service.model, service.json_output, service.effort), ('claude-haiku-5-5', True, 'low'))
        # The rubric is sent as a cached system prompt.
        sent = {}
        from types import SimpleNamespace
        service._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: sent.update(kw)))
        service._create('RUBRIC', 'pages', spec.SCHEMA, spec.SCHEMA_NAME, 10)
        self.assertEqual(sent['system'], [{'type': 'text', 'text': 'RUBRIC', 'cache_control': {'type': 'ephemeral'}}])

    def test_other_claude_requests_are_sent_as_before(self):
        from types import SimpleNamespace
        from apps.extraction.services.anthropic_client import AnthropicExtractionService
        service = AnthropicExtractionService(api_key='sk-ant-test', model='claude-haiku-5-5')
        sent = {}
        service._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: sent.update(kw)))
        service._create('SYSTEM', 'text', spec.SCHEMA, spec.SCHEMA_NAME, 10)
        self.assertEqual(sent['system'], 'SYSTEM')

    @override_settings(EVIDENCE_MAP_AI_API_KEY='sk-ant-test', EVIDENCE_MAP_AI_MODEL='')
    def test_a_key_without_a_model_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            tagging.tagger_service()

    @override_settings(EVIDENCE_MAP_AI_API_KEY='sk-ant-test', EVIDENCE_MAP_AI_MODEL='claude-haiku-5-5',
                       EVIDENCE_MAP_AI_EFFORT='extreme')
    def test_an_unknown_effort_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            tagging.tagger_service()


class ConcurrentPassTests(SprintMixin, TransactionTestCase):
    """Several requests at once (the command's default): every page still stored once, counters still add up."""

    def setUp(self):
        self.make_sprint()

    def test_a_pass_with_several_workers(self):
        job = tagging.run(self.sprint, service=Tagger(), concurrency=3)
        self.assertEqual((job.status, job.pages_tagged, job.pages_failed, job.chunks_done),
                         ('completed', 5, 0, job.chunks_total))
        self.assertEqual(MapPage.objects.filter(status='tagged').count(), 5)
