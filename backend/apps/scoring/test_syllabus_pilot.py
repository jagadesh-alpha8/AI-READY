from unittest import TestCase

from .capability.syllabus_pilot import compare, revision


def page(document, number, text):
    return {'id': f'{document}-{number}', 'document_id': document, 'page_number': number, 'text': text}


def declaration(year):
    return f'(Applicable to all the candidates admitted from the academic year {year}–{year + 1} onwards)'


COURSE = 'Course Objective:\nUnderstand Artificial Intelligence.\nUNIT I Search and inference'


class SyllabusPilotTests(TestCase):
    def setUp(self):
        self.sources = [
            page('syllabus', 1, 'Regulations\n' + declaration(2023)),
            page('syllabus', 2, 'Curriculum outline'),
            page('syllabus', 3, 'Regulations\n' + declaration(2025)),
            page('syllabus', 4, COURSE),
            page('syllabus', 5, 'Unreviewed appendix\n' + COURSE),
            page('other', 4, COURSE),
        ]
        self.editions = [self.edition(1, 2023), self.edition(3, 2025)]

    def edition(self, number, year):
        quote = declaration(year)
        return dict(document_id='syllabus', revision=revision(self.sources[:5]),
                    declaration_page=number, first_body_page=number + 1, last_body_page=number + 1,
                    start=12, end=12 + len(quote), quote=quote)

    def test_uses_governing_edition_and_returns_exact_spans(self):
        result = compare(self.sources, self.editions, 250)
        link = result['link']
        self.assertEqual(link['course']['source_id'], 'syllabus-4')
        self.assertEqual(link['cohort']['source_id'], 'syllabus-3')
        for span in (link['course'], link['cohort']):
            source = next(s for s in self.sources if s['id'] == span['source_id'])
            quote = source['text'][span['start']:span['end']]
            self.assertTrue(any(s['id'] == source['id'] and
                                s['text_offset'] <= span['start'] and
                                span['end'] <= s['text_offset'] + len(s['text']) and
                                s['text'][span['start'] - s['text_offset']:span['end'] - s['text_offset']] == quote
                                for s in result['structural']))
        self.assertLessEqual(sum(len(s['text']) for s in result['structural']), 250)

    def test_abstains_on_unreviewed_edition_appendix_and_other_document(self):
        result = compare(self.sources, self.editions[:1], 250)
        self.assertIsNone(result['link'])
        self.assertEqual(result['baseline'], result['structural'])

    def test_keeps_baseline_when_bundle_does_not_fit(self):
        result = compare(self.sources, self.editions, 100)
        self.assertIsNone(result['link'])
        self.assertEqual(result['baseline'], result['structural'])

    def test_rejects_invalid_provenance_and_overlapping_editions(self):
        for editions, message in [
            ([dict(self.editions[0], revision='stale')], 'different canonical'),
            ([dict(self.editions[0], start=13)], 'exact cohort'),
            ([dict(self.editions[0], last_body_page=3), self.editions[1]], 'Overlapping'),
        ]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                compare(self.sources, editions, 250)
