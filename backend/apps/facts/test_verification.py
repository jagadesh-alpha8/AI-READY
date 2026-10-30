"""The shared fact-verification pipeline and safe automation (apps/facts/verification/).

Fixtures use the platform's three roles (Super Admin, InGage Consultant, IQAC Coordinator). Page text is stored as
DocumentPage rows, exactly as the extraction pipeline saves it.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.gaps.models import GapEvent, GapItem
from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .models import (
    EvidenceRequest, EvidenceRequestDocument, ExtractedFact, FactCorrectionProposal, FactReviewHistory,
    FactVerification,
)
from .verification import conflicts, corrections, derived, engine, grounding, metrics, normalize, policy, validators

PAGE_3 = ('Table 2.1 Student enrolment 2022-23 (UG and PG programmes)\n'
          'Programme   Students\nB.E.  5,880\nM.E.  1,030\nSub total 6,910')
PAGE_5 = 'Integrated programmes 2022-23: 234 students enrolled in the five-year integrated M.Sc.'
PAGE_7 = 'The institution has 42 faculty members with AI certification.'


class VerificationBase(APITestCase):
    def setUp(self):
        self.institution = Institution.objects.create(name='MKCE', city='Karur', state='TN')
        self.other_institution = Institution.objects.create(name='Other', city='X', state='Y')
        self.iqac = self._user('iqac@mkce.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.iqac2 = self._user('iqac2@mkce.edu', User.Role.IQAC_COORDINATOR, self.institution)
        self.consultant = self._user('consultant@ingage.in', User.Role.CONSULTANT, None)
        self.outsider = self._user('iqac@other.edu', User.Role.IQAC_COORDINATOR, self.other_institution)
        self.sprint = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        self.doc = self._doc('ssr.pdf', pages={3: PAGE_3, 5: PAGE_5, 7: PAGE_7})

    @staticmethod
    def _user(email, role, institution):
        return User.objects.create_user(email=email, username=email.replace('@', '-'), password='Str0ng!DevPassw0rd',
                                        first_name='Test', last_name=role, role=role, institution=institution)

    def _doc(self, name, *, pages, sprint=None, previous=None):
        doc = Document.objects.create(sprint=sprint or self.sprint, original_filename=name, document_type='naac_ssr',
                                      status=Document.Status.PROCESSED, page_count=max(pages) + 2,
                                      previous_version=previous,
                                      version_number=(previous.version_number + 1) if previous else 1)
        for number, text in pages.items():
            DocumentPage.objects.create(document=doc, page_number=number, text=text)
        return doc

    def _fact(self, **overrides):
        values = {'sprint': self.sprint, 'document': self.doc, 'source_document': self.doc,
                  'field_name': 'AI-certified faculty', 'field_key': 'ai_certified_faculty', 'value': 42,
                  'normalized_value': 42, 'data_type': ExtractedFact.DataType.NUMBER, 'pillar': 'aiqif_c4',
                  'owner_role': 'iqac_coordinator', 'source_page': '7',
                  'source_snippet': 'The institution has 42 faculty members with AI certification.',
                  'confidence_score': 0.95, 'extraction_method': 'openai'}
        values.update(overrides)
        return ExtractedFact.objects.create(**values)

    def _students(self, value, **overrides):
        return self._fact(field_name='Total students', field_key='total_students', value=value,
                          normalized_value=value, source_page='3', source_snippet='Sub total 6,910', **overrides)


# -- 1. a value that conflicts with its own citation ---------------------------------------------------

class OwnCitationTests(VerificationBase):
    def test_extracted_6909_with_a_quote_saying_6910_is_invalid_and_never_automated(self):
        fact = self._students('6,909')
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            run = engine.verify_fact(fact, apply_policy=True)
        fact.refresh_from_db()
        self.assertEqual(run.outcome, 'invalid')
        self.assertIn('6,909 contradicts its own quote, which says 6,910', run.reason)
        self.assertEqual(run.grounding['value_support'], 'conflicts_quote')
        self.assertEqual((fact.status, fact.automation_decision), (ExtractedFact.Status.EXTRACTED, 'review'))
        self.assertEqual(fact.review_history.count(), 0)

    def test_high_confidence_never_overrides_a_failed_check(self):
        fact = self._students('6,909', confidence_score=0.999)
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            engine.verify_fact(fact, apply_policy=True)
        fact.refresh_from_db()
        self.assertEqual(fact.status, ExtractedFact.Status.EXTRACTED)

    def test_the_four_results_are_kept_apart(self):
        run = engine.verify_fact(self._fact())
        self.assertEqual(run.extraction_confidence, 0.95)  # the model's estimate, stored as such
        self.assertEqual(run.grounding['kind'], 'deterministic')
        self.assertEqual(run.validation['kind'], 'deterministic')
        self.assertEqual(run.cross_source['kind'], 'deterministic')
        self.assertEqual((run.grounding['quote'], run.validation['status'], run.cross_source['status']),
                         ('exact', 'pass', 'no_other_source'))


# -- 2/3. arithmetic and traceable calculated values -----------------------------------------------------

class DerivedValueTests(VerificationBase):
    def _derivation(self, *, includes=('integrated programmes',), excludes=()):
        return {'operation': 'sum', 'includes': list(includes), 'excludes': list(excludes), 'inputs': [
            {'label': 'UG + PG subtotal', 'value': '6,910', 'document_id': str(self.doc.id), 'source_page': '3',
             'source_snippet': 'Sub total 6,910'},
            {'label': 'Integrated', 'value': '234', 'document_id': str(self.doc.id), 'source_page': '5',
             'source_snippet': '234 students enrolled in the five-year integrated M.Sc.'}]}

    def test_a_total_from_two_pages_keeps_formula_inputs_and_citations(self):
        fact = self._students('7,144', derivation=self._derivation(),
                              scope={'includes': ['integrated programmes']})
        run = engine.verify_fact(fact)
        self.assertEqual(run.outcome, 'verified', run.reason)
        self.assertEqual(run.derivation['formula'], '6,910 + 234')
        self.assertEqual(run.derivation['computed'], '7144')
        self.assertEqual([(i['source_page'], i['document_version']) for i in run.derivation['inputs']],
                         [('3', 1), ('5', 1)])
        self.assertTrue(all(i['grounding']['quote'] == 'exact' for i in run.derivation['inputs']))
        self.assertEqual(run.risk_level, 'high')  # a calculated value is always reviewed or precedent-backed

    def test_wrong_arithmetic_is_a_fail_with_formula_and_inputs(self):
        run = engine.verify_fact(self._students('6,909', derivation=self._derivation()))
        self.assertEqual(run.outcome, 'invalid')
        calc = next(c for c in run.validation['checks'] if c['code'] == 'arithmetic')
        self.assertEqual(calc['status'], 'fail')
        self.assertEqual(calc['formula'], '6,910 + 234')
        self.assertIn('7,144', calc['detail'])

    def test_a_total_that_includes_what_the_fact_excludes_fails(self):
        fact = self._students('7,144', derivation=self._derivation(),
                              scope={'excludes': ['integrated programmes']})
        run = engine.verify_fact(fact)
        self.assertEqual(run.outcome, 'invalid')
        self.assertIn('includes integrated programmes, which the fact excludes', ' '.join(run.reasons))

    def test_an_input_not_on_its_page_blocks_verification(self):
        bad = self._derivation()
        bad['inputs'][1]['source_page'] = '7'  # 234 is on page 5
        run = engine.verify_fact(self._students('7,144', derivation=bad))
        self.assertNotEqual(run.outcome, 'verified')

    def test_percentage_arithmetic_uses_the_stated_precision(self):
        computed = derived.compute('percentage', [Decimal(120), Decimal(192)])
        self.assertTrue(derived._matches(Decimal('62.5'), computed))
        self.assertTrue(derived._matches(Decimal('63'), computed))  # 62.5 rounds half up to 63
        self.assertFalse(derived._matches(Decimal('62'), computed))


# -- 4. quotes absent from the page, and OCR variation ----------------------------------------------------

class QuoteGroundingTests(VerificationBase):
    def test_a_quote_not_on_the_cited_page_needs_review(self):
        run = engine.verify_fact(self._fact(source_page='3'))  # the quote is on page 7
        self.assertEqual((run.outcome, run.grounding['quote']), ('needs_review', 'not_found'))
        # The most specific reason first: where the number really is; the quote finding is kept too.
        self.assertIn('printed on page(s) 7', run.reason)
        self.assertIn('not on page 3', ' '.join(run.reasons))

    def test_ocr_differences_in_letters_still_match(self):
        DocumentPage.objects.filter(document=self.doc, page_number=7).update(
            text='The instituti0n has 42 facu1ty members with Al certificati on.')
        run = engine.verify_fact(self._fact())
        self.assertEqual(run.grounding['quote'], 'ocr_variant')
        self.assertEqual(run.outcome, 'verified')

    def test_a_fabricated_number_never_matches_as_an_ocr_variant(self):
        quote = 'The institution has 48 faculty members with AI certification.'
        self.assertEqual(grounding.match_quote(quote, PAGE_7)[0], 'not_found')

    def test_page_outside_the_document_is_invalid(self):
        run = engine.verify_fact(self._fact(source_page='99'))
        self.assertEqual(run.outcome, 'invalid')

    def test_missing_page_text_cannot_verify(self):
        run = engine.verify_fact(self._fact(source_page='8'))
        self.assertEqual((run.outcome, run.grounding['quote']), ('needs_review', 'unavailable'))

    def test_page_ranges_and_labels(self):
        self.assertEqual(grounding.parse_pages('Page 45'), [45])
        self.assertEqual(grounding.parse_pages('12-13'), [12, 13])
        self.assertEqual(grounding.parse_pages('pp. 4, 6'), [4, 6])


# -- 5. units, ranges and dates -------------------------------------------------------------------------

class ValidatorTests(VerificationBase):
    def _checks(self, **overrides):
        return {c['code']: c['status'] for c in validators.validate(overrides['value'], self._fact(**overrides))}

    def test_percentage_range_and_unit(self):
        self.assertEqual(self._checks(value='140', data_type='percentage', field_key='pass_pct')['percent_range'],
                         'fail')
        checks = self._checks(value='42', data_type='percentage', field_key='share')
        self.assertEqual(checks['percent_unit'], 'warn')  # the quote shows no % sign

    def test_counts_and_years(self):
        self.assertEqual(self._checks(value='-3')['count_whole'], 'fail')
        self.assertEqual(self._checks(value='2190', field_key='year_established', field_name='Year established')
                         ['year_range'], 'fail')

    def test_dates(self):
        self.assertEqual(self._checks(value='31/02/2023', data_type='date', field_key='nirf_date')['date_format'],
                         'fail')
        self.assertEqual(self._checks(value='2022-24', data_type='date', field_key='academic_year')['date_format'],
                         'fail')
        self.assertEqual(self._checks(value='15/08/2023', data_type='date', field_key='nirf_date')['date_format'],
                         'pass')

    def test_currency_stored_amount_must_match_the_printed_amount(self):
        checks = self._checks(value='Rs. 20,000', normalized_value=0.2, data_type='currency', field_key='grant')
        self.assertEqual(checks['amount_normalized'], 'fail')

    def test_normalization(self):
        self.assertEqual(normalize.parse_number('Rs. 50,00,000'), Decimal(5000000))
        self.assertEqual(normalize.parse_number('₹20,000'), Decimal(20000))  # the PDF fixture font has no ₹
        self.assertEqual(normalize.parse_number('1.2 lakh'), Decimal('120000.0'))
        self.assertIsNone(normalize.parse_number('2022-23'))
        self.assertTrue(normalize.same_value('1,234', 1234, 'number'))
        self.assertFalse(normalize.same_value('6,909', 6910, 'number'))


# -- 6/7. comparable metrics, genuine conflicts, refreshed summaries ---------------------------------------

class ConflictTests(VerificationBase):
    def setUp(self):
        super().setUp()
        self.aqar = self._doc('aqar.pdf', pages={2: 'Total students 2022-23: 7,150'})

    def _aqar_fact(self, value, snippet):
        return self._fact(document=self.aqar, source_document=self.aqar, field_name='Total students',
                          field_key='total_students', value=value, normalized_value=value, source_page='2',
                          source_snippet=snippet)

    def test_different_periods_or_populations_are_not_the_same_metric(self):
        a = self._fact(field_key='total_students', source_snippet='Total students 2022-23: 7,144', value=7144)
        b = self._aqar_fact(7300, 'Total students 2023-24: 7,300')
        self.assertEqual(conflicts.disagreements([a, b]), [])
        ug = self._fact(field_key='intake', value=600, source_snippet='UG intake 600')
        pg = self._aqar_fact(120, 'PG intake 120')
        pg.field_key = 'intake'
        pg.save()
        self.assertEqual(conflicts.disagreements([ug, pg]), [])
        self.assertEqual(engine.verify_fact(a).cross_source['status'], 'not_comparable')

    def test_printing_differences_are_not_a_conflict(self):
        a = self._fact(field_key='total_students', value='7,150', source_snippet='Total students 2022-23: 7,150')
        b = self._aqar_fact(7150, 'Total students 2022-23: 7,150')
        self.assertEqual(conflicts.disagreements([a, b]), [])

    def test_a_genuine_conflict_is_raised_and_its_summary_refreshes(self):
        from apps.gaps.services import generate_gaps_for_sprint
        a = self._fact(field_key='total_students', field_name='Total students', value=7144,
                       source_snippet='Total students 2022-23: 7,144')
        b = self._aqar_fact(7150, 'Total students 2022-23: 7,150')
        generate_gaps_for_sprint(self.sprint)
        gap = GapItem.objects.get(gap_type=GapItem.GapType.CONFLICT)
        self.assertIn('7144', gap.description)
        self.assertIn('aqar.pdf v1, page 2, 2022-23', gap.description)
        self.assertEqual(engine.verify_fact(a).outcome, 'conflicting')
        # A person corrects one side: the description is rebuilt from the facts as they are now.
        b.value = 7144
        b.status = ExtractedFact.Status.CORRECTED
        b.save()
        from apps.gaps.services import after_fact_review
        after_fact_review(b, user=self.iqac)
        gap.refresh_from_db()
        self.assertNotIn('7150', gap.description)
        self.assertEqual(gap.status, GapItem.Status.RESOLVED)  # the values now agree
        self.assertTrue(gap.events.filter(action=GapEvent.Action.SUMMARY_REFRESHED).exists())

    def test_the_ai_can_annotate_but_never_dismiss_a_conflict(self):
        from unittest.mock import MagicMock

        from apps.extraction.services.conflict_checker import OpenAIConflictChecker
        self._fact(field_key='total_students', value=7144, source_snippet='Total students 2022-23: 7,144')
        self._aqar_fact(7150, 'Total students 2022-23: 7,150')
        ai = MagicMock()
        ai.extract_structured_data.return_value = {'is_conflict': False, 'confidence': 0.99,
                                                   'explanation': 'Probably a rounding difference.'}
        gaps = OpenAIConflictChecker(openai_service=ai).check_conflicts(self.aqar, [])
        self.assertEqual(len(gaps), 1)
        self.assertIn('AI-assisted note (not a decision', gaps[0]['description'])
        self.assertEqual(gaps[0]['priority'], GapItem.Priority.MEDIUM)

    def test_an_earlier_version_of_the_same_file_is_not_a_second_source(self):
        v2 = self._doc('ssr.pdf', pages={7: 'The institution has 45 faculty members with AI certification.'},
                       previous=self.doc)
        self.doc.superseded_at = v2.created_at
        self.doc.save()
        self._fact()
        new = self._fact(document=v2, source_document=v2, value=45,
                         source_snippet='The institution has 45 faculty members with AI certification.')
        self.assertEqual(engine.verify_fact(new).cross_source['status'], 'no_other_source')


# -- 8. automation: safe, ineligible, shadow, overrides ----------------------------------------------------

class AutomationTests(VerificationBase):
    def test_enforce_confirms_a_verified_fact_as_the_rules_with_its_reasons(self):
        fact = self._fact()
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            run = engine.verify_fact(fact, apply_policy=True)
        fact.refresh_from_db()
        self.assertEqual((run.automation_decision, fact.status), ('auto_verified', ExtractedFact.Status.CONFIRMED))
        row = fact.review_history.get()
        self.assertEqual(row.decision_source, FactReviewHistory.DecisionSource.RULE)
        self.assertEqual(row.details['verification_id'], str(run.id))
        self.assertIn('quote found on page 7 of ssr.pdf v1', row.reason)

    def test_shadow_mode_records_what_it_would_do_and_changes_nothing(self):
        fact = self._fact()
        with override_settings(FACT_VERIFICATION_MODE='shadow'):
            run = engine.verify_fact(fact, apply_policy=True)
        fact.refresh_from_db()
        self.assertEqual((run.automation_decision, fact.status), ('would_auto_verify', ExtractedFact.Status.EXTRACTED))
        self.assertEqual(fact.review_history.count(), 0)

    def test_ineligible_facts_go_to_a_person_with_the_reason(self):
        cases = {
            'currency (high risk)': self._fact(field_key='grant', data_type='currency', value='Rs 42',
                                               normalized_value=42),
            'low extraction confidence': self._fact(field_key='labs', confidence_score=0.4),
            'vision fallback': self._fact(field_key='rooms', extraction_method='vision'),
        }
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            for label, fact in cases.items():
                run = engine.verify_fact(fact, apply_policy=True)
                fact.refresh_from_db()
                self.assertEqual((run.automation_decision, fact.status), ('review', 'extracted'), label)
                self.assertTrue(run.blockers, label)

    def test_an_open_conflict_blocks_automation(self):
        fact = self._fact()
        GapItem.objects.create(sprint=self.sprint, gap_type=GapItem.GapType.CONFLICT, title='x', source_fact=fact)
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            run = engine.verify_fact(fact, apply_policy=True)
        self.assertEqual((run.outcome, run.automation_decision), ('conflicting', 'review'))

    def test_a_reviewer_override_of_an_automatic_decision_is_counted(self):
        fact = self._fact()
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            engine.verify_fact(fact, apply_policy=True)
        self.client.force_authenticate(self.iqac)
        r = self.client.post(f'/api/v1/facts/{fact.id}/reject', {'reason': 'The page counts visiting faculty.'})
        self.assertEqual(r.status_code, 200, r.data)
        row = fact.review_history.get(action=FactReviewHistory.Action.REJECTED)
        self.assertTrue(row.details['overrides_auto'])
        work = metrics.workload(self.sprint)
        self.assertEqual((work['auto_verified'], work['reviewer_overrides'], work['reversed_automatic_decisions']),
                         (1, 1, 1))

    def test_bulk_confirm_skips_invalid_facts_and_can_require_verified(self):
        good, bad = self._fact(), self._students('6,909')
        engine.verify_fact(good)
        engine.verify_fact(bad)
        self.client.force_authenticate(self.iqac)
        r = self.client.post(f'/api/v1/sprints/{self.sprint.id}/facts/bulk-confirm',
                             {'fact_ids': [str(good.id), str(bad.id)], 'only_verified': True}, format='json')
        self.assertEqual(r.data['confirmed'], [str(good.id)])
        self.assertIn('invalid', r.data['skipped'][0]['reason'])

    def test_extraction_end_runs_the_pipeline_on_the_document(self):
        self._fact()
        with override_settings(FACT_VERIFICATION_MODE='shadow'):
            counts = engine.process_document(self.doc)
        self.assertEqual((counts['checked'], counts['would_auto_verify']), (1, 1))


# -- 9. precedent ----------------------------------------------------------------------------------------

@override_settings(FACT_VERIFICATION_MODE='enforce')
class PrecedentTests(VerificationBase):
    QUOTE = 'Research grants received Rs. 42 lakh in 2022-23.'

    def setUp(self):
        super().setUp()
        DocumentPage.objects.filter(document=self.doc, page_number=7).update(text=self.QUOTE)
        self.earlier = self._fact(field_key='research_grants', data_type='currency', value='Rs. 42 lakh',
                                  normalized_value=4200000, source_snippet=self.QUOTE,
                                  status=ExtractedFact.Status.CONFIRMED, reviewed_by=self.iqac)
        self.v2 = self._doc('ssr.pdf', pages={7: self.QUOTE}, previous=self.doc)

    def _new(self, **overrides):
        values = dict(document=self.v2, source_document=self.v2, field_key='research_grants', data_type='currency',
                      value='Rs. 42 lakh', normalized_value=4200000, source_snippet=self.QUOTE)
        values.update(overrides)
        return self._fact(**values)

    def test_an_exact_precedent_stands_in_for_a_person_and_names_who_decided(self):
        fact = self._new()
        run = engine.verify_fact(fact, apply_policy=True)
        fact.refresh_from_db()
        self.assertEqual((run.automation_decision, fact.status), ('precedent', 'confirmed'))
        row = fact.review_history.get()
        self.assertEqual(row.decision_source, FactReviewHistory.DecisionSource.PRECEDENT)
        self.assertEqual(row.details['precedent']['decided_by'], str(self.iqac.id))
        self.assertEqual(row.details['precedent']['fact_id'], str(self.earlier.id))

    def test_an_ambiguous_match_is_only_a_suggestion(self):
        other_quote = 'Research grants of Rs. 42 lakh were received during 2022-23 from DST.'
        DocumentPage.objects.filter(document=self.v2, page_number=7).update(text=other_quote)
        fact = self._new(source_snippet=other_quote)
        run = engine.verify_fact(fact, apply_policy=True)
        self.assertEqual((run.precedent['match'], run.automation_decision), ('partial', 'review'))
        self.assertIn('a different quote', run.precedent['differences'])

    def test_a_decision_is_never_carried_to_another_sprint(self):
        other = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        doc = self._doc('ssr.pdf', pages={7: self.QUOTE}, sprint=other)
        fact = self._new(sprint=other, document=doc, source_document=doc)
        run = engine.verify_fact(fact, apply_policy=True)
        self.assertIsNone(run.precedent)
        self.assertEqual(run.automation_decision, 'review')

    def test_a_rule_decision_is_never_a_precedent(self):
        from .auto_confirm import system_user
        self.earlier.reviewed_by = system_user()
        self.earlier.save()
        run = engine.verify_fact(self._new(), apply_policy=True)
        self.assertEqual(run.automation_decision, 'review')

    def test_a_value_is_never_proof_of_a_new_value(self):
        fact = self._new(value='Rs. 48 lakh', normalized_value=4800000)  # its own quote says 42
        run = engine.verify_fact(fact, apply_policy=True)
        self.assertEqual(run.automation_decision, 'review')


# -- 10. owner corrections -----------------------------------------------------------------------------

class CorrectionTests(VerificationBase):
    def setUp(self):
        super().setUp()
        self.fact = self._fact(status=ExtractedFact.Status.CONFIRMED, reviewed_by=self.iqac2,
                               original_value=42, original_source_page='7')
        self.aqar = self._doc('aqar.pdf', pages={4: 'AI-certified faculty as on 31.03.2023: 45'})

    def _propose(self, user=None, **body):
        self.client.force_authenticate(user or self.iqac)
        payload = {'value': 45, 'reason': 'The AQAR counts the March batch.', 'source_document_id': str(self.aqar.id),
                   'source_page': '4', 'source_snippet': 'AI-certified faculty as on 31.03.2023: 45'}
        payload.update(body)
        return self.client.post(f'/api/v1/facts/{self.fact.id}/corrections', payload, format='json')

    def test_a_proposal_changes_nothing_until_another_reviewer_approves(self):
        r = self._propose()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['verification']['outcome'], 'verified')
        self.fact.refresh_from_db()
        self.assertEqual((self.fact.value, self.fact.status), (42, 'confirmed'))
        proposal = FactCorrectionProposal.objects.get()
        # The submitter cannot approve their own correction.
        r2 = self.client.post(f'/api/v1/fact-corrections/{proposal.id}/approve', {})
        self.assertEqual(r2.status_code, 403)
        self.client.force_authenticate(self.iqac2)
        r3 = self.client.post(f'/api/v1/fact-corrections/{proposal.id}/approve', {'reason': 'Checked the AQAR.'})
        self.assertEqual(r3.status_code, 200, r3.data)
        self.fact.refresh_from_db()
        self.assertEqual((self.fact.value, self.fact.status, self.fact.source_page), (45, 'corrected', '4'))
        self.assertEqual((self.fact.original_value, self.fact.original_source_page), (42, '7'))  # never overwritten
        actions = list(self.fact.review_history.order_by('created_at').values_list('action', 'user'))
        self.assertEqual(actions, [('correction_proposed', self.iqac.id), ('corrected', self.iqac2.id)])
        approved = self.fact.review_history.get(action='corrected')
        self.assertEqual(approved.details['submitted_by'], str(self.iqac.id))

    def test_a_person_reviewed_value_cannot_be_overwritten_directly(self):
        self.client.force_authenticate(self.iqac)
        r = self.client.post(f'/api/v1/facts/{self.fact.id}/correct', {'new_value': 45, 'reason': 'x'},
                             format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(str(r.data['code']), 'correction_needs_approval')

    def test_support_is_required_and_must_be_from_this_sprint(self):
        self.assertEqual(self._propose(source_document_id=None).status_code, 400)
        other = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        foreign = self._doc('x.pdf', pages={1: '45'}, sprint=other)
        self.assertEqual(self._propose(source_document_id=str(foreign.id)).status_code, 400)
        self.assertEqual(self._propose(reason='').status_code, 400)

    def test_another_college_cannot_propose_or_see(self):
        self.assertEqual(self._propose(user=self.outsider).status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f'/api/v1/sprints/{self.sprint.id}/verification/summary').status_code, 403)

    def test_rejecting_needs_a_reason_and_a_changed_fact_makes_a_proposal_stale(self):
        self._propose()
        proposal = FactCorrectionProposal.objects.get()
        with self.assertRaises(corrections.CorrectionError):
            corrections.reject(proposal, self.iqac2, reason='')
        ExtractedFact.objects.filter(pk=self.fact.pk).update(value=43)
        with self.assertRaises(corrections.CorrectionError):
            corrections.approve(proposal, self.iqac2)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, FactCorrectionProposal.Status.STALE)


# -- 11/12. isolation and history ---------------------------------------------------------------------------

class IsolationAndHistoryTests(VerificationBase):
    def test_cross_source_never_reaches_another_sprint_or_college(self):
        other = Sprint.objects.create(institution=self.other_institution, mode=Sprint.SprintMode.QUICK_CRI)
        doc = self._doc('ssr.pdf', pages={7: PAGE_7.replace('42', '50')}, sprint=other)
        self._fact(sprint=other, document=doc, source_document=doc, value=50)
        run = engine.verify_fact(self._fact())
        self.assertEqual(run.cross_source['status'], 'no_other_source')

    def test_a_document_of_another_sprint_is_not_a_valid_citation(self):
        other = Sprint.objects.create(institution=self.institution, mode=Sprint.SprintMode.QUICK_CRI)
        doc = self._doc('ssr.pdf', pages={7: PAGE_7}, sprint=other)
        run = engine.verify_fact(self._fact(source_document=doc))
        self.assertEqual((run.outcome, run.grounding['citation']), ('invalid', 'wrong_sprint'))

    def test_dry_runs_and_reports_write_nothing(self):
        from .auto_confirm import auto_confirm
        reviewed = self._fact(field_key='reviewed', status=ExtractedFact.Status.CONFIRMED, reviewed_by=self.iqac)
        unreviewed = self._fact()
        before = list(ExtractedFact.objects.order_by('id').values())
        result = auto_confirm(ExtractedFact.objects.all(), dry_run=True)
        metrics.shadow_report(ExtractedFact.objects.all())
        metrics.historical_audit(ExtractedFact.objects.all())
        self.assertEqual(result['confirmed'], [str(unreviewed.id)])
        self.assertEqual(list(ExtractedFact.objects.order_by('id').values()), before)
        self.assertFalse(FactVerification.objects.exists())
        self.assertEqual(reviewed.review_history.count(), 0)

    def test_reprocessing_never_changes_a_persons_decision(self):
        fact = self._fact(status=ExtractedFact.Status.CORRECTED, reviewed_by=self.iqac, value=40)
        with override_settings(FACT_VERIFICATION_MODE='enforce'):
            engine.process_document(self.doc)
        fact.refresh_from_db()
        self.assertEqual((fact.status, fact.value, fact.reviewed_by_id), ('corrected', 40, self.iqac.id))
        self.assertEqual(fact.automation_decision, 'not_applicable')
        self.assertEqual(fact.review_history.count(), 0)

    def test_facts_from_before_verification_keep_their_values(self):
        fact = self._fact(status=ExtractedFact.Status.CONFIRMED, reviewed_by=self.iqac)
        self.assertEqual((fact.verification_status, fact.automation_decision, fact.original_value), ('', '', None))
        self.client.force_authenticate(self.iqac)
        row = self.client.get(f'/api/v1/facts/{fact.id}').data
        self.assertIsNone(row['verification'])
        self.assertEqual(row['status'], 'confirmed')

    def test_shadow_report_replays_the_extracted_value_not_the_correction(self):
        self._fact(field_key='a', status=ExtractedFact.Status.CONFIRMED, reviewed_by=self.iqac)
        self._students(7144, status=ExtractedFact.Status.CORRECTED, reviewed_by=self.iqac,
                       original_value='6,909')
        report = metrics.shadow_report(ExtractedFact.objects.filter(sprint=self.sprint))
        self.assertEqual(report['totals']['would_auto_and_confirmed'], 1)
        self.assertNotIn('would_auto_but_changed', report['totals'])  # 6,909 contradicts its quote: reviewed
        self.assertEqual(report['precision_if_enabled'], 1.0)


class EvidenceSubmissionVerificationTests(VerificationBase):
    def test_the_ai_assessment_citation_is_checked_against_the_pages_read(self):
        fact = self._fact(status=ExtractedFact.Status.EVIDENCE_REQUESTED)
        req = EvidenceRequest.objects.create(sprint=self.sprint, fact=fact, description='Proof',
                                             fact_status_before='extracted')
        aqar = self._doc('aqar.pdf', pages={4: 'AI-certified faculty: 42'})
        link = EvidenceRequestDocument.objects.create(
            request=req, document=aqar, analysis_quote='AI-certified faculty: 42', analysis_page_number=4,
            analysis_suggested_value='42', source_pages=[{'page_number': 4, 'text': 'AI-certified faculty: 42'}])
        result = engine.verify_evidence_link(link)
        self.assertEqual((result['quote'], result['value_support']), ('exact', 'in_quote'))
        link.analysis_quote = 'AI-certified faculty: 48'
        self.assertEqual(engine.verify_evidence_link(link)['quote'], 'not_found')


class ExtractorCalculationTests(TestCase):
    def test_calculation_inputs_must_cite_pages_of_the_chunk(self):
        from apps.extraction.services.openai_fact_extractor import _validate_calculation
        notes = []
        raw = {'operation': 'sum', 'includes': [], 'excludes': [], 'inputs': [
            {'label': 'a', 'value': '6,910', 'source_page': '3', 'source_snippet': 'Sub total 6,910'},
            {'label': 'b', 'value': '234', 'source_page': '9', 'source_snippet': '234'}]}
        self.assertEqual(_validate_calculation(raw, {'3', '5'}, notes), {})
        self.assertEqual(notes[0]['kind'], 'calculation_dropped')
        raw['inputs'][1]['source_page'] = '5'
        self.assertEqual(len(_validate_calculation(raw, {'3', '5'}, [])['inputs']), 2)

    def test_policy_defaults(self):
        self.assertEqual(policy.policy()['high']['automate'], False)
        self.assertEqual(policy.mode(), 'shadow')
