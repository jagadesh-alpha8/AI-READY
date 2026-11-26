"""Learning from judged runs (learn-1). No model calls."""
from django.test import SimpleTestCase, TestCase

from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from . import learn, spec, tagging
from .models import MapJob, MapPage

TEXT = 'The IQAC conducts the annual academic audit with a 52-indicator questionnaire for every department.'
OTHER = 'Principles and Practices of Management, a core course of the BBA programme in semester one.'
SOURCES = [{'id': 's1', 'document_id': 'd', 'page_number': 153, 'filename': 'SSR.pdf', 'text': TEXT},
           {'id': 's2', 'document_id': 'd', 'page_number': 9, 'filename': 'Syllabi.pdf', 'text': OTHER}]


def record(cid, credit, *parts):
    return {'condition_id': cid, 'credit': credit, 'parts': [
        {'id': f'p{n}', 'credited_as': kind, 'citations': [{'source_id': sid, 'quote': quote}]}
        for n, (kind, sid, quote) in enumerate(parts, 1)]}


class TagsFromTests(SimpleTestCase):
    def test_only_requirements_that_earned_credit_become_tags(self):
        records = [record('AIQIF-C9.1.F1', 1.0, ('full', 's1', 'annual academic audit')),
                   record('AIQIF-C9.2.O1', 0.0, ('full', 's1', 'annual academic audit'))]   # no credit: left out
        found, counts = learn.tags_from(records, SOURCES, run_id='abcdef12-0000')
        tags = found[spec.text_hash(TEXT)]
        self.assertEqual([(t['requirements'], t['strength'], t['origin']) for t in tags],
                         [(['AIQIF-C9.1.F1'], 'direct', learn.ORIGIN)])
        self.assertEqual(counts['requirement_without_credit'], 1)

    def test_full_on_partial_credit_and_related_are_supporting(self):
        records = [record('AIQIF-C9.1.O1', 0.5, ('full', 's1', 'annual academic audit'),
                          ('related', 's1', '52-indicator questionnaire'))]
        found, _ = learn.tags_from(records, SOURCES, run_id='r')
        self.assertEqual({t['strength'] for t in found[spec.text_hash(TEXT)]}, {'supporting'})

    def test_a_reviewed_not_evidence_pair_and_a_missing_quotation_are_left_out(self):
        records = [record('AIQIF-C5.1.F1', 1.0, ('full', 's2', 'Principles and Practices of Management')),
                   record('AIQIF-C9.1.F1', 1.0, ('full', 's1', 'a quotation the page does not hold'))]
        found, counts = learn.tags_from(records, SOURCES, run_id='r',
                                        exclude={('AIQIF-C5.1.F1', 'Syllabi.pdf', 9)})
        self.assertEqual(found, {})
        self.assertEqual((counts['excluded_by_review'], counts['quote_not_on_page']), (1, 1))


class StoredTests(TestCase):
    def test_learned_tags_are_added_once_and_survive_re_tagging(self):
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='College'))
        MapPage.objects.create(text_hash=spec.text_hash(TEXT), map_version='v', model='m',
                               status=MapPage.Status.TAGGED, page_type='other', tags=[])
        found, _ = learn.tags_from([record('AIQIF-C9.1.F1', 1.0, ('full', 's1', 'annual academic audit'))],
                                   SOURCES, run_id='r')
        self.assertEqual(tagging.add_tags(map_version='v', model='m', found=found), 1)
        self.assertEqual(tagging.add_tags(map_version='v', model='m', found=found), 0)   # never twice
        job = MapJob.objects.create(sprint=sprint, map_version='v', model='m', shape='areas', spend_cap_usd=1)
        tagging.save(job, [{'id': 's1', 'number': 153, 'text': TEXT}],
                     {153: {'page_type': 'report_narrative', 'tags': [
                         {'indicator': 'AIQIF-C9.1', 'requirements': ['AIQIF-C9.1.F2'], 'strength': 'supporting',
                          'quote': 'IQAC', 'quote_found': True, 'reason': 'x'}]}})
        tags = MapPage.objects.get(text_hash=spec.text_hash(TEXT)).tags
        self.assertEqual(sorted(t.get('origin') or 'tagger' for t in tags), ['judged_run', 'tagger'])

    def test_nothing_is_added_to_a_page_the_tagger_has_not_read(self):
        found, _ = learn.tags_from([record('AIQIF-C9.1.F1', 1.0, ('full', 's1', 'annual academic audit'))],
                                   SOURCES, run_id='r')
        self.assertEqual(tagging.add_tags(map_version='v', model='m', found=found), 0)
