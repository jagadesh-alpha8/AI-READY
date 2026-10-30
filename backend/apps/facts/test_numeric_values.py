"""Numbers in documents: separators, units and checking the value against the cited page (verification/numeric.py).

Reproduction: NAAC SSR section 4.1.4.1 prints the 2022-23 infrastructure expenditure as 5638.56 (INR in lakhs).
The AI returned 563856 with a quote "... 2022 23 -: 563856 ." -- the decimal point lost in both. Verification
said "PASS Number format". The page text below is page 186 of that SSR as the pipeline stores it.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import ExtractedFact
from .verification import engine, normalize

SSR_PAGE_186 = (
    'the last five years 4.1.4.1. Expenditure incurred, excluding salary, for infrastructure development and '
    'augmentation year-wise during the last five years (INR in lakhs) Answer before DVV Verification: 2022-23 '
    '2021-22 2020-21 2019-20 2018-19 6305.56 7000.70 6685.09 2032.78 959.42 Answer After DVV Verification : '
    '2022-23 2021-22 2020-21 2019-20 2018-19 5638.56 6738.70 5372.09 1738.48 567.8 Remark : DVV has considered '
    'the supporting document and made changes accordingly')
GARBLED_QUOTE = ('4.1.4.1. Expenditure incurred, excluding salary, for infrastructure development and augmentation '
                 'year-wise during the last five years (INR in lakhs) | 2022 23 -: 563856 .')
GOOD_QUOTE = ('4.1.4.1. Expenditure incurred, excluding salary, for infrastructure development and augmentation '
              'year-wise during the last five years (INR in lakhs) Answer before DVV Verification: 2022-23')


class SeparatorTests(TestCase):
    def test_decimal_points_are_never_deleted(self):
        self.assertEqual(normalize.parse_number('5638.56'), Decimal('5638.56'))
        self.assertEqual(normalize.parse_number('5,638.56'), Decimal('5638.56'))
        self.assertNotEqual(normalize.parse_number('5638.56'), Decimal('563856'))

    def test_indian_and_western_grouping(self):
        self.assertEqual(normalize.parse_number('56,38,560.50'), Decimal('5638560.50'))
        self.assertEqual(normalize.parse_number('1,00,000'), Decimal('100000'))
        self.assertEqual(normalize.parse_number('Rs. 50,00,000'), Decimal('5000000'))
        self.assertEqual(normalize.parse_number('5,638,560'), Decimal('5638560'))

    def test_ambiguous_separators_are_flagged_not_guessed(self):
        for text in ('5638,56', '1.234.567', '56,38,56'):
            self.assertIsNone(normalize.parse_number(text), text)
            self.assertTrue(normalize.number_issue(text), text)
        self.assertIn('comma as the decimal point', normalize.number_issue('5638,56'))
        # A badly grouped token reads as the numbers it shows, never glued together.
        self.assertEqual(normalize.numbers_in('5638,56'), [Decimal(5638), Decimal(56)])
        self.assertEqual(normalize.tokens('5638,56'), ['5638', '56'])

    def test_ocr_and_table_text_keep_their_decimals(self):
        from apps.extraction.services.pdf_reader import render_table
        table = {'index': 1, 'header': ['2022-23', '2021-22'], 'rows': [['5638.56', '6738.70']]}
        rendered = render_table(table, 186)
        self.assertIn('2022-23: 5638.56 | 2021-22: 6738.70', rendered)
        self.assertIn(Decimal('5638.56'), normalize.numbers_in(rendered))
        self.assertEqual(normalize.numbers_in('5638.S6'), [Decimal('5638.56')])  # OCR S for 5, inside a number


class ExtractorTests(TestCase):
    def _validate(self, value, data_type='number'):
        from apps.extraction.services.openai_fact_extractor import OpenAIFactExtractor
        raw = {'field_name': 'Infrastructure expenditure (2022-23)', 'field_key': 'infra_exp_2022_23',
               'value': value, 'data_type': data_type, 'pillar': 'aiqif_c6', 'owner_role': 'iqac_coordinator',
               'source_page': '186', 'source_snippet': GOOD_QUOTE, 'confidence_score': 1.0,
               'confidence_reason': 'Printed in the table.',
               'scope': {'period': '2022-23', 'population': None, 'unit': 'INR in lakhs', 'includes': [],
                         'excludes': []}}
        return OpenAIFactExtractor._validate_fact(raw, {'186'}, SSR_PAGE_186)

    def test_the_value_text_and_unit_are_kept_and_never_converted(self):
        fact = self._validate('5638.56')
        self.assertEqual((fact['value'], fact['value_text'], fact['scope']['unit'], fact['scope']['period']),
                         (5638.56, '5638.56', 'INR in lakhs', '2022-23'))

    def test_an_ambiguous_number_is_kept_as_text_for_a_person(self):
        fact = self._validate('5638,56')
        self.assertEqual((fact['value'], fact['normalized_value'], fact['value_text']), ('5638,56', None, '5638,56'))
        self.assertEqual(fact['tagging_notes'][0]['kind'], 'ambiguous_number')


class ValueInDocumentTests(APITestCase):
    def setUp(self):
        institution = Institution.objects.create(name='VELS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.doc = Document.objects.create(sprint=self.sprint, original_filename='NAAC SSR.pdf',
                                           document_type='naac_ssr', status=Document.Status.PROCESSED, page_count=187)
        DocumentPage.objects.create(document=self.doc, page_number=186, text=SSR_PAGE_186)
        DocumentPage.objects.create(document=self.doc, page_number=102,
                                    text='4.1.4.1 Expenditure (INR in lakhs) 2022-23 5638.56 ... 4.2.1 total 98765')

    def _fact(self, value, value_text, snippet=GOOD_QUOTE, page='186', **over):
        values = dict(
            sprint=self.sprint, document=self.doc, source_document=self.doc,
            field_name='Infrastructure development expenditure (2022-23)', field_key='infra_exp_2022_23',
            value=value, normalized_value=value, value_text=value_text, data_type='number', pillar='aiqif_c6',
            source_page=page, source_snippet=snippet, confidence_score=1.0)
        values.update(over)
        return ExtractedFact.objects.create(**values)

    def test_the_lost_decimal_point_is_invalid_with_the_page_figure(self):
        run = engine.verify_fact(self._fact(563856, '563856', snippet=GARBLED_QUOTE))
        self.assertEqual(run.outcome, 'invalid')
        self.assertEqual((run.numeric['status'], run.numeric['page_shows']), ('decimal_missing', '5638.56'))
        self.assertIn('prints 5638.56, not 563,856', run.reason)
        self.assertIn('INR in lakhs', run.numeric['unit'])
        self.assertEqual(run.numeric['source_text'], '563856')
        # Grounding names the figure the page does not print; the format check stays a format check.
        self.assertIn('does not print 563,856', ' '.join(run.grounding['detail']))
        fmt = next(c for c in run.validation['checks'] if c['code'] == 'number_format')
        self.assertEqual(fmt['label'], 'Readable as a number')
        self.assertIn('format only', fmt['detail'])
        fact = ExtractedFact.objects.get()
        self.assertEqual((fact.value, fact.status), (563856, 'extracted'))  # never silently corrected

    def test_the_printed_value_is_found_and_the_unit_is_not_applied(self):
        run = engine.verify_fact(self._fact(5638.56, '5638.56'))
        self.assertEqual(run.numeric['status'], 'found')
        self.assertEqual(Decimal(run.numeric['parsed']), Decimal('5638.56'))  # lakhs not multiplied out

    def test_a_value_on_another_page_is_flagged(self):
        run = engine.verify_fact(self._fact(98765, '98765', snippet='total 98765'))
        self.assertEqual((run.numeric['status'], run.numeric['pages']), ('other_page', [102]))
        self.assertEqual(run.outcome, 'needs_review')

    def test_a_power_of_ten_slip_is_flagged(self):
        run = engine.verify_fact(self._fact(56780, '56780', snippet='567.8'))  # the page prints 567.8 (x100)
        self.assertEqual((run.numeric['status'], run.numeric['page_shows']), ('scale_mismatch', '567.8'))
        self.assertNotEqual(run.outcome, 'verified')

    def test_a_number_not_in_the_document_needs_review(self):
        run = engine.verify_fact(self._fact(4321, '4321', snippet='4321'))
        self.assertEqual((run.numeric['status'], run.outcome), ('not_found', 'needs_review'))

    def test_an_ambiguous_value_needs_review_and_keeps_its_text(self):
        run = engine.verify_fact(self._fact('5638,56', '5638,56'))
        self.assertEqual((run.numeric['status'], run.outcome), ('ambiguous', 'needs_review'))
        self.assertIn('comma as the decimal point', run.reason)

    def test_without_stored_page_text_nothing_is_assumed(self):
        run = engine.verify_fact(self._fact(5638.56, '5638.56', page='50'))
        self.assertEqual((run.numeric['status'], run.outcome), ('page_unavailable', 'needs_review'))

    def test_a_calculated_value_is_checked_by_its_formula_instead(self):
        derivation = {'operation': 'sum', 'includes': [], 'excludes': [], 'inputs': [
            {'label': '2022-23', 'value': '5638.56', 'source_page': '186', 'source_snippet': '5638.56 6738.70'},
            {'label': '2021-22', 'value': '6738.70', 'source_page': '186', 'source_snippet': '5638.56 6738.70'}]}
        good = engine.verify_fact(self._fact(12377.26, '12377.26', snippet='5638.56 6738.70', derivation=derivation))
        self.assertEqual(good.numeric['status'], 'not_applicable')
        self.assertEqual(next(c for c in good.validation['checks'] if c['code'] == 'arithmetic')['status'], 'pass')
        bad = engine.verify_fact(self._fact(12377.62, '12377.62', snippet='5638.56 6738.70', derivation=derivation,
                                            field_key='infra_sum_bad'))
        self.assertEqual(bad.outcome, 'invalid')


class FactSearchTests(APITestCase):
    """The Facts Review search box (filters.filter_search) -- a 'value_text' annotation once collided with the
    model field of that name and every search failed with ValueError."""

    def test_search_finds_a_fact_by_its_value_and_its_extracted_text(self):
        from apps.accounts.models import User
        institution = Institution.objects.create(name='VELS')
        sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        ExtractedFact.objects.create(sprint=sprint, field_name='Infrastructure expenditure', field_key='infra_exp',
                                     value=5638.56, value_text='5638.56', data_type='number', pillar='aiqif_c6',
                                     source_snippet='x', confidence_score=0.9)
        user = User.objects.create_user(email='iqac@vels.in', username='iqac-vels', password='Str0ng!DevPassw0rd',
                                        role=User.Role.IQAC_COORDINATOR, institution=institution)
        self.client.force_authenticate(user)
        url = f'/api/v1/sprints/{sprint.id}/facts'
        for query in ('5638', '5638.56', 'infra', 'Infrastructure', 'nothing-like-this'):
            response = self.client.get(url, {'q': query})
            self.assertEqual(response.status_code, 200, query)
            self.assertEqual(response.data['count'], 0 if query == 'nothing-like-this' else 1, query)
