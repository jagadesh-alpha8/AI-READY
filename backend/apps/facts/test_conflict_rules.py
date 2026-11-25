"""Conflict rules added after reading test 13's open conflicts: option codes, name forms and initials, a misread
"≥". No database."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.facts.verification import conflicts


def fact(pk, value, *, data_type='string', field='affiliating_body', includes=(), snippet=''):
    return SimpleNamespace(pk=pk, value=value, data_type=data_type, field_key=field, field_name=field.replace('_', ' '),
                           source_snippet=snippet, scope={'includes': list(includes)}, retired_at=None,
                           status='pending', source_document=None, document=None)


class OptionCodeTests(SimpleTestCase):
    def test_option_answers_are_recognised(self):
        for value in ('A. All of the above', '(b) Any 3 of the above', 'C) None of the above', 'd. two of the above',
                      'A. Any 4 or all of the above'):
            with self.subTest(value):
                self.assertTrue(conflicts.option_code(value))
        for value in ('All of the above were trained', 'A', '42', 'Anna University', None):
            with self.subTest(value):
                self.assertFalse(conflicts.option_code(value))

    def test_an_option_code_never_forms_a_conflict(self):
        group = [fact(1, 'A. All of the above', field='ict_facilities'), fact(2, 'Wi-Fi, LMS, smart classrooms',
                                                                             field='ict_facilities')]
        self.assertEqual(conflicts.disagreements(group), [])

    def test_two_real_answers_beside_an_option_code_still_conflict(self):
        group = [fact(1, 'A. All of the above'), fact(2, 'Anna University'), fact(3, 'Madras University')]
        self.assertEqual([[f.pk for f in g] for g in conflicts.disagreements(group)], [[2, 3]])


class NameFormTests(SimpleTestCase):
    def test_initials_and_filler_words_say_the_same_thing(self):
        same = [('AICTE', 'All India Council for Technical Education'),
                ('Science & Humanities', 'Science and Humanities'),
                ('Department of Computer Science', 'Department Computer Science'),
                ('NAAC', 'National Assessment and Accreditation Council')]
        for a, b in same:
            with self.subTest(a=a, b=b):
                self.assertTrue(conflicts.same_statement(a, b, 'string'))
                self.assertTrue(conflicts.same_statement(b, a, 'string'))
                self.assertEqual(conflicts.disagreements([fact(1, a), fact(2, b)]), [])

    def test_different_names_still_conflict(self):
        for a, b in (('AICTE', 'University Grants Commission'), ('Anna University', 'Annamalai University'),
                     ('UG', 'Under Graduate'), ('CS', 'Computer Science')):
            with self.subTest(a=a, b=b):
                self.assertFalse(conflicts.same_statement(a, b, 'string'))

    def test_numbers_are_not_read_as_initials(self):
        self.assertFalse(conflicts.same_statement('120', 'one hundred twenty', 'string'))
        self.assertFalse(conflicts.same_statement('2760', '2804', 'number'))


class MisreadBoundTests(SimpleTestCase):
    def test_a_question_mark_before_a_number_reads_as_at_least(self):
        self.assertTrue(conflicts.bounds_agree(['? 50', '64'], misread=True))
        self.assertFalse(conflicts.bounds_agree(['? 50', '40'], misread=True))
        group = [fact(1, '? 50', data_type='number', field='mous'), fact(2, '64', data_type='number', field='mous')]
        self.assertEqual(conflicts.disagreements(group), [])

    def test_a_question_mark_elsewhere_is_left_alone(self):
        self.assertFalse(conflicts.bounds_agree(['50?', '64'], misread=True))

    def test_not_without_the_facts_saying_it_is_safe(self):
        # Audit 25 Nov, item 3: bare values never get the "≥" reading.
        self.assertFalse(conflicts.bounds_agree(['? 2,00,000', '3,50,000']))
        self.assertFalse(conflicts.bounds_agree(['? 50,000', '60,000']))

    def test_money_conflicts_stay_visible(self):
        # In Indian PDFs "?" before an amount is usually a lost rupee sign: ₹2,00,000 against 3,50,000 is a conflict.
        cases = [
            [fact(1, '? 2,00,000', data_type='number', field='annual_budget'),
             fact(2, '3,50,000', data_type='number', field='annual_budget')],
            [fact(1, '? 50,000', data_type='currency', field='seed_grant'),
             fact(2, '60,000', data_type='currency', field='seed_grant')],
            [fact(1, '? 50000', data_type='number', field='award', snippet='A cash award of ? 50000 is given.'),
             fact(2, '60000', data_type='number', field='award')],
        ]
        for group in cases:
            with self.subTest(group[0].field_key):
                self.assertFalse(conflicts.misread_allowed(group))
                self.assertEqual(len(conflicts.disagreements(group)), 1)

    def test_counts_keep_the_reading(self):
        group = [fact(1, '? 50', data_type='number', field='mous_signed'), fact(2, '64', data_type='number',
                                                                              field='mous_signed')]
        self.assertTrue(conflicts.misread_allowed(group))


class UndatedTests(SimpleTestCase):
    def test_undated_numbers_are_still_compared(self):
        # Test 13's possible real conflict: computers 2,760 (undated) vs 2,804 (as of 2021). A person should look.
        group = [fact(1, '2760', data_type='number', field='computers'),
                 fact(2, '2804', data_type='number', field='computers', snippet='2804 computers as of 2021')]
        self.assertEqual(len(conflicts.disagreements(group)), 1)


class SummaryTests(SimpleTestCase):
    def test_distinct_values_count_name_forms_once(self):
        group = [fact(1, 'AICTE'), fact(2, 'All India Council for Technical Education'), fact(3, 'UGC')]
        self.assertEqual(conflicts.distinct_values(group), ['AICTE', 'UGC'])
