"""Whole sentences for cut-off quotations (capability/quote_context.py, quote-context-1)."""
from django.test import SimpleTestCase

from .capability import presentation, quote_context as qc

PAGE = ('2.4 IT Infrastructure\nThe firewall is upgraded to\nSonicall NSA 4700 from Sophos NXG550. The ERP system is '
        'linked to a functional biometric system which is employed to track staff attendance and student mentor-mentee '
        'system periodically.\n6.3 Faculty and Staff Empowerment Strategies 6.3.1 The institution has effective welfare '
        'measures for teaching and non-teaching staff, and other beneficiaries.\n[Table 1 on page 37 -- columns: Number of '
        'students | Number of Computers available to students for academic purposes]\n | S. NO.: | CONTENTS: category '
        'claimed in SSR | LINK: |\nDr. A. Kumar chairs the committee, which meets every month to review the')


class SentenceTests(SimpleTestCase):
    def test_a_sentence_split_at_a_line_end_is_made_whole(self):
        self.assertEqual(qc.sentence(PAGE, 'The firewall is upgraded to'),
                         'The firewall is upgraded to Sonicall NSA 4700 from Sophos NXG550.')
        self.assertEqual(qc.sentence(PAGE, 'which is employed to track staff attendance and student mentor-mentee '
                                           'system periodically.'),
                         'The ERP system is linked to a functional biometric system which is employed to track staff '
                         'attendance and student mentor-mentee system periodically.')

    def test_a_metric_number_starts_the_sentence_and_is_left_out(self):
        self.assertEqual(qc.sentence(PAGE, 'The institution has effective welfare measures for teaching and non-teaching '
                                           'staff, and other'),
                         'The institution has effective welfare measures for teaching and non-teaching staff, and other '
                         'beneficiaries.')

    def test_readable_quotes_table_rows_notes_and_missing_quotes_are_left_alone(self):
        self.assertIsNone(qc.sentence(PAGE, 'Sonicall NSA 4700 from Sophos NXG550.'))        # already readable
        self.assertIsNone(qc.sentence(PAGE, 'S. NO.: | CONTENTS: category claimed in SSR | LINK:'))
        self.assertIsNone(qc.sentence(PAGE, '[Table 1 on page 37 -- columns: Number of students | Number of Computers '
                                            'available to students for academic purposes]'))
        self.assertIsNone(qc.sentence(PAGE, 'The library is upgraded to'))                    # not on the page
        # The page ends mid-sentence: what is there is still a fragment, so nothing is printed in its place.
        self.assertIsNone(qc.sentence(PAGE, 'which meets every month to review the'))

    def test_abbreviations_do_not_end_a_sentence(self):
        page = 'Minutes. The committee chaired by Dr. A. Kumar meets every month to review the e-governance plan.'
        self.assertEqual(qc.sentence(page, 'meets every month to review the e-governance plan.'),
                         'The committee chaired by Dr. A. Kumar meets every month to review the e-governance plan.')

    def test_curly_quotes_and_dashes_in_the_quote_still_find_the_page(self):
        page = 'Review. The college\'s IT team - led by the IT Manager - ensures the campus is always connected.'
        self.assertEqual(qc.sentence(page, 'The college’s IT team – led by the IT Manager – ensures the'),
                         page.split('Review. ', 1)[1])

    def test_a_heading_run_or_a_long_stretch_is_not_a_sentence(self):
        page = 'UNDERGRADUATE DEGREE PROGRAMME Bachelor of Business Administration (Hons) Four Years CURRICULUM & SYLLABUS'
        self.assertIsNone(qc.sentence(page, 'Bachelor of Business Administration (Hons)'))
        long = 'word ' * 120 + 'and so the committee reviews the plan every term to'
        self.assertIsNone(qc.sentence(long, 'and so the committee reviews the plan every term to'))


class RecordTests(SimpleTestCase):
    def record(self):
        return {'condition_id': 'AIQIF-C6.3.O2', 'credit': 1.0,
                'citations': [{'source_id': 'p1', 'quote': 'The firewall is upgraded to'}],
                'parts': [{'id': 'p1', 'citations': [{'source_id': 'p1', 'quote': 'The firewall is upgraded to'},
                                                     {'source_id': 'p2', 'quote': 'The firewall is upgraded to'}]}]}

    def test_sentences_are_keyed_by_page_and_the_record_is_never_changed(self):
        record = self.record()
        found = qc.sentences([record], [{'id': 'p1', 'text': PAGE}])
        self.assertEqual(found, {qc.key('p1', 'The firewall is upgraded to'):
                                 'The firewall is upgraded to Sonicall NSA 4700 from Sophos NXG550.'})
        shown = qc.record_whole(record, found)
        self.assertEqual(record, self.record())                     # the stored record keeps the judge's quotation
        self.assertEqual(shown['citations'][0]['quote'], 'The firewall is upgraded to Sonicall NSA 4700 from Sophos NXG550.')
        self.assertEqual(shown['parts'][0]['citations'][0]['quote'], shown['citations'][0]['quote'])
        self.assertEqual(shown['parts'][0]['citations'][1]['quote'], 'The firewall is upgraded to')   # another page
        self.assertIs(qc.record_whole(record, {}), record)

    def test_without_a_run_there_is_nothing_to_widen(self):
        self.assertEqual(qc.for_run(None, [self.record()]), {})


class UnreadableTests(SimpleTestCase):
    def test_a_trailing_comma_or_semicolon_is_cut_off(self):
        for text in ('The network security ensures the protection of data and computer systems from cybercrime activities,',
                     'The committee reviews the audit findings and the corrective actions every semester;'):
            self.assertEqual(presentation.unreadable(text), 'cut off mid-sentence', text)
        self.assertEqual(presentation.unreadable('The committee reviews the audit findings every semester.'), '')
