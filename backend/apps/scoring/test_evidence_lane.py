"""Extracted-evidence lane: relevant extracted AI items bring their source page into the indicator's packet."""
from django.test import SimpleTestCase

from apps.scoring.capability.engine import release
from apps.scoring.capability.reviewed_evidence import LANE_CHARS, evidence_lane, lane_relevance


def indicator(code):
    return next(i for i in release()['indicators'] if i['code'] == code)


def claim(cid, label, page, kind='ai_evidence', disposition='extracted', quote='B.Tech CSE (AI and ML) intake 120'):
    return {'id': cid, 'label': label, 'attribute': label.lower().replace(' ', '_'), 'value': '120', 'kind': kind,
            'disposition': disposition,
            'source': {'document_id': 'aicte', 'page': str(page), 'quote': quote, 'current': True}}


PAGE = {'id': 'aicte:19', 'document_id': 'aicte', 'page_number': 19,
        'text': 'Level: UG | Course: B.Tech CSE (AI and ML) intake 120 | Approved for 2024-25'}
OTHER = {'id': 'ssr:3', 'document_id': 'ssr', 'page_number': 3, 'text': 'Unrelated page.'}


class EvidenceLaneTests(SimpleTestCase):
    def test_programme_intake_routes_to_the_advanced_pathway_indicator(self):
        item = claim('c1', 'Approved Intake CSE Artificial Intelligence and Machine Learning', 19)
        self.assertGreaterEqual(lane_relevance(item, indicator('AIQIF-C5.2')), 10)
        self.assertLess(lane_relevance(item, indicator('AIQIF-C2.4')), 10)

    def test_adds_the_missing_page_once_and_keeps_retrieved_windows(self):
        ledger = {'claims': [claim('c1', 'Approved Intake CSE AI and ML', 19),
                             claim('c2', 'Approved Intake CSE AI and ML 2025', 19)]}
        context = [{**OTHER, 'text_offset': 0}]
        out, audit = evidence_lane(indicator('AIQIF-C5.2'), list(context), [PAGE, OTHER], ledger)
        self.assertEqual(out[0], context[0])
        self.assertEqual([w['id'] for w in out], ['ssr:3', 'aicte:19'])
        self.assertEqual(out[1]['evidence_role'], 'extracted_evidence')
        self.assertEqual(PAGE['text'][out[1]['text_offset']:out[1]['text_offset'] + len(out[1]['text'])], out[1]['text'])
        self.assertEqual(len(audit['added']), 1)

    def test_skips_rejected_context_and_already_present_items(self):
        ledger = {'claims': [claim('c1', 'Approved Intake CSE AI', 19, disposition='rejected'),
                             claim('c2', 'Approved Intake CSE AI', 19, kind='context')]}
        out, audit = evidence_lane(indicator('AIQIF-C5.2'), [], [PAGE], ledger)
        self.assertEqual(out, [])
        present = [{**PAGE, 'text_offset': 0}]
        out, audit = evidence_lane(indicator('AIQIF-C5.2'), list(present),
                                   [PAGE], {'claims': [claim('c3', 'Approved Intake CSE AI', 19)]})
        self.assertEqual(len(out), 1)
        self.assertEqual(audit['already_in_packet'], 1)

    def test_budget_is_respected(self):
        big = {**PAGE, 'text': 'B.Tech CSE (AI and ML) intake 120 ' + 'x' * 5000}
        sources = [{**big, 'id': f'aicte:{n}', 'page_number': n} for n in range(1, 30)]
        ledger = {'claims': [claim(f'c{n}', f'Approved Intake CSE AI {n}', n) for n in range(1, 30)]}
        _, audit = evidence_lane(indicator('AIQIF-C5.2'), [], sources, ledger)
        self.assertLessEqual(audit['used_chars'], LANE_CHARS)
