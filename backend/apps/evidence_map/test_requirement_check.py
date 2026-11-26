"""The requirement check (check-1): the closest untagged pages per requirement, checked once more. No model calls."""
import json
from unittest.mock import patch

from django.test import TestCase

from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from . import packet, requirement_check as check, spec, tagging
from .models import MapJob, MapPage

CORRECTION = ('Evidence correction log: Answer before DVV Verification: 100. Answer after DVV Verification: 133. '
              'Remark: the earlier record is preserved and the reason for the change is stated.')
INDEX = 'List of documents uploaded: evidence index of the source records used for the assessment, document repository.'
TAGGED = 'Evidence index already tagged: the source records register for the assessment is maintained.'
SPORTS = 'Annual sports day was held on the main ground with many events.'
UNREAD = 'Evidence correction register with the earlier record and reason for change, never read by the tagger.'


def documents(*pages):
    return [{'document_id': 'doc', 'filename': 'NAAC SSR.pdf', 'type': 'report', 'pages': len(pages),
             'readable': [{'id': f'p{n}', 'number': n, 'text': t} for n, t in enumerate(pages, 1)], 'unreadable': 0}]


class Fake:
    """Answers as the model would: tags the correction page for C9.2 (one quotation that is on the page, one that is
    not) and the index page for another indicator."""
    model = 'm'

    def __init__(self):
        self.requests = []

    def extract_structured_data(self, **kwargs):
        self.requests.append(kwargs)
        content = kwargs['user_content']
        pages = []
        for n, block in enumerate(content.split('--- Page ')[1:], 1):
            tags = []
            if 'DVV Verification' in block:
                tags = [{'indicator': 'C9.2', 'requirements': ['C9.2.A2'], 'strength': 'direct',
                         'quote': 'Answer before DVV Verification: 100. Answer after DVV Verification: 133.',
                         'reason': 'Before and after values with a remark.'},
                        {'indicator': 'C9.2', 'requirements': ['C9.2.A2'], 'strength': 'supporting',
                         'quote': 'A sentence that is not on this page at all.', 'reason': 'x'}]
            elif 'List of documents uploaded' in block:
                tags = [{'indicator': 'C9.1', 'requirements': ['C9.1.F1'], 'strength': 'supporting',
                         'quote': 'List of documents uploaded', 'reason': 'x'}]
            pages.append({'page': n, 'page_type': 'other', 'tags': tags})
        return {'pages': pages}


class RequirementCheckTests(TestCase):
    def setUp(self):
        self.sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        rubric, profiles, parts = spec.rubric_sources()
        self.version = spec.map_version('areas', rubric, profiles, parts)
        for text, tags in ((CORRECTION, []), (INDEX, []), (SPORTS, []),
                           (TAGGED, [{'indicator': 'AIQIF-C9.2', 'requirements': ['AIQIF-C9.2.F1'],
                                      'strength': 'direct', 'quote': 'Evidence index', 'quote_found': True,
                                      'reason': 'x'}])):
            MapPage.objects.create(text_hash=spec.text_hash(text), map_version=self.version, model='m',
                                   status=MapPage.Status.TAGGED, page_type='other', tags=tags)
        self.docs = documents(CORRECTION, INDEX, TAGGED, SPORTS, UNREAD)

    def plan(self, **kw):
        with patch.object(tagging, 'sprint_documents', return_value=self.docs):
            return check.plan(self.sprint, map_version=self.version, model='m', indicators=['AIQIF-C9.2'], **kw)

    def run_check(self, service):
        with patch.object(tagging, 'sprint_documents', return_value=self.docs):
            return check.run(self.sprint, map_version=self.version, model='m', indicators=['AIQIF-C9.2'],
                             service=service, max_cost_usd=1)

    def test_candidates_are_read_pages_without_a_strong_tag_that_the_search_ranks_close(self):
        work = self.plan()
        texts = {p['text'] for w in work['work'] for p in w['pages']}
        self.assertIn(CORRECTION, texts)
        self.assertIn(INDEX, texts)
        self.assertNotIn(TAGGED, texts)     # already a strong tag for the indicator
        self.assertNotIn(SPORTS, texts)     # no word in common with any requirement
        self.assertNotIn(UNREAD, texts)     # the tagger never read it: no row to add to
        self.assertEqual(work['requests'], 1)
        self.assertLessEqual(self.plan(per_requirement=1)['pages'], 6)

    def test_only_the_indicators_strong_tags_with_a_found_quotation_are_added(self):
        job = self.run_check(Fake())
        self.assertEqual(job.status, MapJob.Status.COMPLETED)
        row = MapPage.objects.get(text_hash=spec.text_hash(CORRECTION))
        self.assertEqual(len(row.tags), 1)
        added = row.tags[0]
        self.assertEqual((added['indicator'], added['strength'], added['origin']),
                         ('AIQIF-C9.2', 'direct', check.ORIGIN))
        self.assertEqual(MapPage.objects.get(text_hash=spec.text_hash(INDEX)).tags, [])   # another indicator's tag
        self.assertEqual(job.checks['check_tags_kept'], 1)
        self.assertEqual(job.checks['check_quote_not_found'], 1)
        self.assertEqual(job.checks['check_tag_not_kept'], 1)

    def test_the_request_names_the_indicator_and_every_page_with_its_document(self):
        service = Fake()
        self.run_check(service)
        request = service.requests[0]
        self.assertIn(check.NOTE, request['system_prompt'])
        self.assertIn('INDICATOR C9.2', request['system_prompt'])
        self.assertIn('(document: NAAC SSR.pdf, its page 1)', request['user_content'])

    def test_a_page_is_checked_once_per_map_version(self):
        service = Fake()
        self.run_check(service)
        again = self.plan()
        texts = {p['text'] for w in again['work'] for p in w['pages']}
        self.assertNotIn(INDEX, texts)
        self.assertNotIn(CORRECTION, texts)   # now tagged, and asked before

    def test_checked_tags_survive_a_new_tagging_answer_and_reach_the_packet(self):
        self.run_check(Fake())
        job = MapJob.objects.create(sprint=self.sprint, map_version=self.version, model='m', shape='areas',
                                    spend_cap_usd=1)
        page = {'id': 'p1', 'number': 1, 'text': CORRECTION}
        tagging.save(job, [page], {1: {'page_type': 'other', 'tags': []}})
        row = MapPage.objects.get(text_hash=spec.text_hash(CORRECTION))
        self.assertEqual([t.get('origin') for t in row.tags], [check.ORIGIN])
        frozen = packet.freeze([{'id': 'p1', 'document_id': 'doc', 'page_number': 1, 'text': CORRECTION}],
                               map_version=self.version, model='m')
        from apps.scoring.capability.engine import release
        indicator = next(i for i in release()['indicators'] if i['code'] == 'AIQIF-C9.2')
        _, trace = packet.build(indicator, [{'id': 'p1', 'document_id': 'doc', 'page_number': 1, 'text': CORRECTION}],
                                frozen, cap=60000, keyword_fill=lambda pages, n: [])
        self.assertEqual(trace['windows'][0]['reasons'][0]['origin'], check.ORIGIN)
        self.assertEqual(trace['windows'][0]['reasons'][0]['step'], 'direct')

    def test_a_failed_request_leaves_the_pages_unchecked(self):
        from apps.extraction.exceptions import PermanentExtractionError

        class Refusing(Fake):
            def extract_structured_data(self, **kwargs):
                raise PermanentExtractionError('400')
        job = self.run_check(Refusing())
        self.assertEqual(job.checks['check_request_failed'], 1)
        self.assertEqual(job.checks['asked'], {})
        self.assertTrue(self.plan()['pages'] > 0)
        json.dumps(job.checks)
