"""subject-cap-middle-v2 and mean-credit-of-three-v1 (27 Nov 2026): what the follow-up stage and the depth reserve
read from a record whose third pass is kept on its parts."""
from fractions import Fraction

from django.test import SimpleTestCase

from .capability import layer2, reserve

Q_NEW = 'The college sent this new certificate for the AI workshop.'
Q_OLD = 'The packet already held this line about the AI workshop.'
PACKET = [{'id': 'old', 'text': Q_OLD}]
POINTED = [{'id': 'old', 'text': Q_OLD}]


def cite(quote, source='new'):
    return [{'source_id': source, 'quote': quote}]


class ThreePassGuardTests(SimpleTestCase):
    def test_a_pointed_rise_needs_every_pass_including_the_third(self):
        part = {'id': 'p2', 'citations': cite(Q_OLD, 'old'), 'second_citations': cite(Q_OLD, 'old')}
        self.assertTrue(layer2.pointed_rise(part, POINTED))
        # Before mean-credit-of-three-v1 a tie-broken record kept one pass's parts, so one pass was enough exactly
        # where the passes disagreed. Now the third pass is on the part and must cite the pointed page too.
        self.assertFalse(layer2.pointed_rise({**part, 'third_citations': []}, POINTED))
        self.assertTrue(layer2.pointed_rise({**part, 'third_citations': cite(Q_OLD, 'old')}, POINTED))

    def test_a_lowering_needs_every_pass_to_find_a_contradiction(self):
        part = {'id': 'p2', 'finding': 'contradicted', 'second_finding': 'contradicted', 'citations': cite(Q_NEW),
                'second_citations': cite(Q_NEW)}
        self.assertTrue(layer2._contradicting(part, PACKET))
        self.assertFalse(layer2._contradicting({**part, 'third_finding': 'related', 'third_citations': cite(Q_NEW)},
                                               PACKET))
        self.assertTrue(layer2._contradicting({**part, 'third_finding': 'contradicted', 'third_citations': cite(Q_NEW)},
                                              PACKET))
        # One pass alone never lowers.
        self.assertFalse(layer2._contradicting({'id': 'p2', 'finding': 'contradicted', 'citations': cite(Q_NEW)},
                                               PACKET))

    def test_a_part_missing_in_any_pass_counts_as_missing(self):
        self.assertFalse(layer2._missing_in_a_pass({'credited_as': 'full', 'second_credited_as': 'related'}))
        self.assertTrue(layer2._missing_in_a_pass({'credited_as': 'full', 'second_credited_as': 'full',
                                                   'third_credited_as': 'not_found'}))

    def test_recredit_averages_three_passes(self):
        cid = 'AIQIF-C1.1.F2'
        parts = [{'id': 'p1', 'credited_as': 'full', 'second_credited_as': 'full', 'third_credited_as': 'full'},
                 {'id': 'p2', 'credited_as': 'full', 'second_credited_as': 'related', 'third_credited_as': 'not_found'}]
        # Passes: 1.0, 0.5 (subject full, the rest related: the middle step), 0.0.
        self.assertEqual(layer2._recredit(parts, cid), 0.5)


class ReserveTriggerTests(SimpleTestCase):
    def test_v3_holds_from_five_eighths(self):
        self.assertEqual(reserve.VERSION, 'depth-reserve-v3')
        self.assertEqual(reserve.MIN_CREDIT, Fraction(5, 8))
        held = {'depth_share': '0.25', 'depth_min_credit': str(reserve.MIN_CREDIT)}
        # Shown in full by one pass, at least related by the other (1 and 0.25): held, as in v2.
        self.assertTrue(reserve.holds({**held, 'credit': 0.625}))
        # Shown only in part by both passes (0.5 and 0.5): not held; it gets a missing-evidence question instead.
        self.assertFalse(reserve.holds({**held, 'credit': 0.5}))

    def test_a_v2_record_keeps_its_own_trigger(self):
        self.assertTrue(reserve.holds({'depth_share': '0.25', 'depth_min_credit': '1/2', 'credit': 0.5}))
