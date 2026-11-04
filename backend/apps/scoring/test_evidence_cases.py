"""Support alternatives are packet diagnostics, not automated judgement labels."""
from copy import deepcopy
from django.test import SimpleTestCase
from .capability.evidence_cases import validate_cases, packet_coverage, VERSION
from .capability.storage import digest


class EvidenceCaseTests(SimpleTestCase):
    def setUp(self):
        self.sources = [{'id': 'p', 'document_id': 'd', 'page_number': 1,
                         'text': 'The ERP automates examinations. The LMS supports learner coursework. Approval was recorded.'}]
        self.rubric = {'indicators': [{'code': 'I', 'conditions': [
            {'id': 'a', 'text': 'A digital service has a purpose.'},
            {'id': 'b', 'text': 'An approved syllabus has substantive content.'}]}]}
        def quote(text, doc='d'):
            return {'document_id': doc, 'page': 1, 'quote': text}
        self.positive = {'condition_id': 'a', 'assertion': self.rubric['indicators'][0]['conditions'][0]['text'],
            'positive_bundles': [{'id': 'erp', 'citations': [quote('The ERP automates examinations.')]},
                {'id': 'lms', 'citations': [quote('The LMS supports learner coursework.')]}], 'insufficient_controls': []}
        self.control = {'condition_id': 'b', 'assertion': self.rubric['indicators'][0]['conditions'][1]['text'],
            'positive_bundles': [], 'insufficient_controls': [{'id': 'approval_only',
                'citations': [quote('Approval was recorded.')], 'expected_on_this_packet': 'unknown',
                'reason': 'Approval alone does not identify substantive syllabus content.'}]}
        self.pack = {'version': VERSION, 'source_corpus_hash': digest(self.sources),
                     'rubric_hash': digest(self.rubric), 'cases': [self.positive, self.control]}

    def coverage(self, text, cases=None, doc='d'):
        return packet_coverage(cases or self.pack['cases'], self.rubric, self.sources, budget=1000,
            selector=lambda *args, **kwargs: [{**self.sources[0], 'document_id': doc, 'text': text, 'text_offset': 0}])

    def test_valid_case_pack_preserves_alternatives_and_controls(self):
        self.assertEqual(validate_cases(self.pack, self.rubric, self.sources), self.pack['cases'])

    def test_alternative_support_counts_when_original_quote_is_missing(self):
        result = self.coverage('The LMS supports learner coursework.')
        self.assertEqual(result['positive_cases_with_known_support'], 1)
        self.assertEqual(result['cases'][0]['matched_bundle_ids'], ['lms'])
        self.assertFalse(result['assessment_decisions_tested'])

    def test_all_citations_within_bundle_are_required(self):
        case = deepcopy(self.positive)
        case['positive_bundles'] = [{'id': 'combined', 'citations':
            self.positive['positive_bundles'][0]['citations'] + self.positive['positive_bundles'][1]['citations']}]
        self.assertEqual(self.coverage('The ERP automates examinations.', [case])['positive_cases_with_known_support'], 0)
        self.assertEqual(self.coverage(self.sources[0]['text'], [case])['positive_cases_with_known_support'], 1)

    def test_wrong_document_cannot_satisfy_a_bundle(self):
        self.assertEqual(self.coverage(self.sources[0]['text'], doc='foreign')['positive_cases_with_known_support'], 0)

    def test_controls_have_no_positive_coverage_denominator(self):
        result = self.coverage('Approval was recorded.')
        self.assertEqual(result['positive_cases'], 1)
        self.assertEqual(result['cases_without_verified_positive'], 1)
        self.assertIsNone(result['cases'][1]['known_positive_bundle_present'])

    def test_stale_or_ungrounded_cases_are_rejected(self):
        for field in ('source_corpus_hash', 'rubric_hash'):
            pack = deepcopy(self.pack)
            pack[field] = 'wrong'
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_cases(pack, self.rubric, self.sources)
        pack = deepcopy(self.pack)
        pack['cases'][0]['positive_bundles'][0]['citations'][0]['quote'] = 'Invented purpose.'
        with self.assertRaises(ValueError):
            validate_cases(pack, self.rubric, self.sources)

    def test_duplicate_requirements_and_changed_assertions_are_rejected(self):
        pack = deepcopy(self.pack)
        pack['cases'].append(deepcopy(pack['cases'][0]))
        with self.assertRaises(ValueError):
            validate_cases(pack, self.rubric, self.sources)
        pack = deepcopy(self.pack)
        pack['cases'][0]['assertion'] = 'An easier criterion.'
        with self.assertRaises(ValueError):
            validate_cases(pack, self.rubric, self.sources)

    def test_whitespace_normalization_does_not_change_provenance(self):
        self.assertEqual(self.coverage('The LMS supports\nlearner coursework.')['positive_cases_with_known_support'], 1)
