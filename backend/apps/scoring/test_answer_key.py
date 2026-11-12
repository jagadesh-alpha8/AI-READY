"""Answer-key scoring: outcomes, first failed stage, other-document credits, instability, frozen-source export."""
import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.institutions.models import Institution
from apps.scoring.capability.answer_key import check, consensus, instability
from apps.scoring.capability.storage import digest
from apps.scoring.models import CapabilityRun
from apps.sprints.models import Sprint

QUOTE = 'Development of a diagnostic bot for optometry'


def export(states, *, packet=('p2',), excerpt=QUOTE, frozen=('p1', 'p2', 'p3'), citations=None):
    """Synthetic export: one key document (pages p1..p3) and one other document (o1)."""
    records = [{'condition_id': cid, 'state': s, 'citations': (citations or {}).get(cid, [])} for cid, s in states.items()]
    return {
        'run_id': 'run-1',
        'scope': {'source_ids': list(frozen) + ['o1']},
        'source_manifest': [
            {'document_id': 'd1', 'filename': 'NAAC SSR Self-Study Report.pdf',
             'pages': [{'page_id': f'p{n}', 'number': n} for n in (1, 2, 3)]},
            {'document_id': 'd2', 'filename': 'syllabus.pdf', 'pages': [{'page_id': 'o1', 'number': 1}]},
        ],
        'assessment': {'records': records, 'traces': [
            {'indicator': 'AIQIF-C7.1', 'source_ids': list(packet),
             'source_excerpts': [{'id': pid, 'text': f'... {excerpt} ...'} for pid in packet]},
            {'indicator': 'AIQIF-C3.1', 'source_ids': ['o1'], 'source_excerpts': []},
        ]},
    }


KEY = {'version': 'k1', 'document': {'match': 'Self-Study'}, 'conditions': {
    'AIQIF-C7.1.F1': {'expected': 'met', 'status': 'confirmed', 'evidence': [{'page': 2, 'quote': QUOTE}]},
    'AIQIF-C7.1.F2': {'expected': 'unknown', 'status': 'draft', 'evidence': []},
    'AIQIF-C3.1.F2': {'expected': 'unknown', 'status': 'draft', 'evidence': []},
    'AIQIF-C7.1.O1': {'expected': 'unknown', 'status': 'needs_decision', 'evidence': []},
}}


def row(result, cid):
    return next(r for r in result['conditions'] if r['condition_id'] == cid)


class AnswerKeyCheckTests(SimpleTestCase):
    states = {'AIQIF-C7.1.F1': 'met', 'AIQIF-C7.1.F2': 'unknown', 'AIQIF-C3.1.F2': 'unknown', 'AIQIF-C7.1.O1': 'met'}

    def test_all_correct_scores_only_settled_conditions(self):
        result = check(export(self.states), KEY)
        self.assertEqual((result['correct'], result['scored_conditions'], result['accuracy']), (3, 3, 1.0))
        self.assertEqual(result['not_scored'], {'needs_decision': 1})

    def test_missed_credit_with_passage_in_packet_is_a_judgment_failure(self):
        result = check(export({**self.states, 'AIQIF-C7.1.F1': 'unknown'}), KEY)
        r = row(result, 'AIQIF-C7.1.F1')
        self.assertEqual((r['outcome'], r['stage']), ('missed_credit', 'judgment'))

    def test_first_failed_stage_walks_source_packet_page_then_passage(self):
        missed = {**self.states, 'AIQIF-C7.1.F1': 'unknown'}
        self.assertEqual(row(check(export(missed, frozen=('p1', 'p3')), KEY), 'AIQIF-C7.1.F1')['stage'], 'source_integrity')
        self.assertEqual(row(check(export(missed, packet=('p1',)), KEY), 'AIQIF-C7.1.F1')['stage'], 'packet_page')
        self.assertEqual(row(check(export(missed, excerpt='an unrelated window'), KEY), 'AIQIF-C7.1.F1')['stage'],
                         'packet_passage')

    def test_unsupported_credit_and_other_document_credit_are_separated(self):
        states = {**self.states, 'AIQIF-C7.1.F2': 'met', 'AIQIF-C3.1.F2': 'met'}
        result = check(export(states, citations={
            'AIQIF-C7.1.F2': [{'source_id': 'p3', 'quote': 'x'}],
            'AIQIF-C3.1.F2': [{'source_id': 'o1', 'quote': 'y'}]}), KEY)
        self.assertEqual((row(result, 'AIQIF-C7.1.F2')['outcome'], row(result, 'AIQIF-C7.1.F2')['stage']),
                         ('unsupported_credit', 'judgment'))
        self.assertEqual(row(result, 'AIQIF-C3.1.F2')['outcome'], 'other_document_credit')
        self.assertEqual((result['scored_conditions'], result['not_scored']),
                         (2, {'out_of_scope': 1, 'needs_decision': 1}))

    def test_correct_credit_citing_no_key_evidence_page_is_flagged(self):
        cited = lambda page: check(export(self.states, citations={
            'AIQIF-C7.1.F1': [{'source_id': page, 'quote': 'q'}]}), KEY)
        self.assertEqual(cited('p3')['correct_but_citation_off_key_evidence'], ['AIQIF-C7.1.F1'])
        self.assertEqual(cited('p2')['correct_but_citation_off_key_evidence'], [])

    def test_key_document_must_match_exactly_one_export_document(self):
        with self.assertRaises(ValueError):
            check(export(self.states), {**KEY, 'document': {'match': '.pdf'}})

    def test_instability_lists_conditions_whose_state_differs_between_runs(self):
        a = check(export(self.states), KEY)
        b = check(export({**self.states, 'AIQIF-C7.1.F1': 'unknown'}), KEY)
        self.assertEqual(instability([a, b]), [
            {'condition_id': 'AIQIF-C7.1.F1', 'expected': 'met', 'states': ['met', 'unknown']}])

    def test_agreement_routes_disagreements_to_review_and_keeps_unanimous_errors_visible(self):
        a = check(export({**self.states, 'AIQIF-C7.1.F2': 'met'}, citations={
            'AIQIF-C7.1.F2': [{'source_id': 'p3', 'quote': 'x'}]}), KEY)
        b = check(export({**self.states, 'AIQIF-C7.1.F1': 'unknown', 'AIQIF-C7.1.F2': 'met'}, citations={
            'AIQIF-C7.1.F2': [{'source_id': 'p3', 'quote': 'x'}]}), KEY)
        agreed = consensus([a, b])
        self.assertEqual((agreed['correct'], agreed['wrong_unanimous'], agreed['to_review']), (1, 1, 1))
        self.assertEqual(agreed['wrong'], [{'condition_id': 'AIQIF-C7.1.F2', 'expected': 'unknown', 'got': 'met'}])
        self.assertEqual(agreed['review'][0]['condition_id'], 'AIQIF-C7.1.F1')
        self.assertEqual(agreed['accuracy_of_decided'], 0.5)

    def test_command_scores_several_exports_and_reports_instability(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, states in (('a', self.states), ('b', {**self.states, 'AIQIF-C7.1.F1': 'unknown'})):
                path = Path(tmp) / f'{name}.json'
                path.write_text(json.dumps(export(states)))
                paths.append(str(path))
            key = Path(tmp) / 'key.json'
            key.write_text(json.dumps(KEY))
            out = io.StringIO()
            call_command('capability_answer_key_check', *paths, '--key', str(key), stdout=out)
        self.assertIn('accuracy 3/3 = 1.0', out.getvalue())
        self.assertIn('accuracy 2/3', out.getvalue())
        self.assertIn('Unstable across the 2 runs (1 conditions)', out.getvalue())
        self.assertIn('correct 2, unanimous but wrong 0, to review 1', out.getvalue())


class ExportRunSourcesTests(TestCase):
    def test_exports_only_the_matching_documents_pages_in_order(self):
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='U', city='C', state='S'),
                                       mode=Sprint.SprintMode.VERIFIED_CRI)
        inputs = {'manifest': [{'document_id': 'd1', 'filename': 'NAAC SSR Self-Study.pdf', 'expected_pages': 2},
                               {'document_id': 'd2', 'filename': 'syllabus.pdf', 'expected_pages': 1}],
                  'sources': [{'id': 's2', 'document_id': 'd1', 'page_number': 2, 'text': 'second'},
                              {'id': 'o1', 'document_id': 'd2', 'page_number': 1, 'text': 'other'},
                              {'id': 's1', 'document_id': 'd1', 'page_number': 1, 'text': 'first'}]}
        run = CapabilityRun.objects.create(sprint=sprint, inputs=inputs, inputs_hash=digest(inputs))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'ssr.json'
            call_command('export_run_sources', str(run.pk), '--match', 'Self-Study', '--output', str(target),
                         stdout=io.StringIO())
            data = json.loads(target.read_text())
            self.assertEqual([p['text'] for p in data['pages']], ['first', 'second'])
            self.assertTrue(data['inputs_hash_verified'])
            with self.assertRaises(CommandError):  # never overwrites
                call_command('export_run_sources', str(run.pk), '--match', 'Self-Study', '--output', str(target))
