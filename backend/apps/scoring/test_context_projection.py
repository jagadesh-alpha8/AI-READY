"""Small, synthetic checks for the current request packet, not a legacy suite."""
import json
from copy import deepcopy
from django.test import SimpleTestCase
from .capability.reviewed_evidence import for_context

QUOTE = 'Engineering learners had access to the computing laboratory during 2025-26.'
OTHER = 'The campus cafeteria introduced a new seasonal menu during the same year.'


def claim(cid, quote=QUOTE, page='1', disposition='confirmed'):
    return {'id': cid, 'attribute': 'computing_access', 'label': 'Computing access', 'value': True,
            'kind': 'context', 'disposition': disposition, 'verification': {'outcome': 'verified'},
            'scope': {'programme': 'engineering', 'period': '2025-26', 'stated': {'programme': 'engineering'}},
            'source': {'document_id': 'doc', 'page': page, 'version': 1, 'current': True, 'quote': quote},
            'original_source': {'document_id': 'doc', 'page': page, 'quote': quote},
            'decisions': [{'id': cid + '-review', 'actor_id': 'reviewer', 'timestamp': '2026-11-03',
                           'action': disposition, 'rationale': 'Checked the scoped source.'}]}


class ContextProjectionTests(SimpleTestCase):
    def setUp(self):
        self.sources = [{'id': 'page', 'document_id': 'doc', 'page_number': 1, 'text_offset': 100, 'text': QUOTE}]
        self.ledger = {'version': 'test', 'claims': [claim('a')], 'issues': [], 'review_batch': None}

    def test_selects_actual_excerpt_not_every_claim_on_page(self):
        self.ledger['claims'].append(claim('unrelated', OTHER))
        packet = for_context(self.ledger, self.sources)
        self.assertEqual([c['id'] for c in packet['claims']], ['a'])
        self.assertEqual(packet['claims'][0]['source']['passages'], [{'source_id': 'page', 'text_offset': 100}])
        self.assertNotIn(QUOTE, json.dumps(packet))  # quotation already exists in sources
        self.assertNotIn('stated', packet['claims'][0]['scope'])

    def test_preserves_connected_rejected_alternative_outside_window(self):
        self.ledger['claims'].append(claim('b', OTHER, '2', 'rejected'))
        self.ledger['issues'] = [{'id': 'conflict', 'kind': 'conflict', 'status': 'resolved',
                                  'claim_ids': ['a', 'b'], 'rationale': 'Choose a; b is a rejected alternative.'}]
        packet = for_context(self.ledger, self.sources)
        by_id = {c['id']: c for c in packet['claims']}
        self.assertEqual(by_id['b']['disposition'], 'rejected')
        self.assertFalse(by_id['b']['source']['source_support_in_selected_passages'])
        self.assertEqual(packet['issues'][0]['claim_ids'], ['a', 'b'])

    def test_unrelated_corpus_growth_does_not_grow_request_packet(self):
        before = for_context(self.ledger, self.sources)
        for index in range(200):
            c = deepcopy(claim(f'extra-{index}'))
            c['source']['document_id'] = c['original_source']['document_id'] = f'other-doc-{index}'
            self.ledger['claims'].append(c)
        self.assertEqual(for_context(self.ledger, self.sources), before)

    def test_assignment_and_tag_history_do_not_hide_effective_decision(self):
        c = self.ledger['claims'][0]
        c['decisions'].extend({'id': str(i), 'action': 'assigned', 'details': 'x' * 10000} for i in range(20))
        packet = for_context(self.ledger, self.sources)
        self.assertEqual(packet['claims'][0]['decisions'][0]['id'], 'a-review')
        self.assertLess(len(json.dumps(packet)), 2000)
