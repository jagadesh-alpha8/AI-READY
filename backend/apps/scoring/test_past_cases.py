"""Past cases, build-order steps 1 to 4 (capability/past_cases.py, standard.py). No model calls."""
from django.test import SimpleTestCase, TestCase, override_settings

from apps.institutions.models import Institution
from apps.sprints.models import Sprint

from .capability import past_cases, standard
from .models import CapabilityRun, CapabilityRunEvent, DriftLedger, PartCase

CID = 'AIQIF-C1.1.F2'
PACKET = [{'id': 'pg1', 'page_number': 4, 'document_id': 'd', 'text': 'The plan names the e-governance priority.'},
          {'id': 'pg2', 'page_number': 9, 'document_id': 'd', 'text': 'Tagged page about committees.'}]
RECORD = {'condition_id': CID, 'credit': 0.5, 'state': 'unknown', 'reason': 'Subject shown; owner partly.',
          'parts': [{'id': 'p1', 'finding': 'full', 'credited_as': 'full', 'second_finding': 'full',
                     'second_credited_as': 'full', 'citations': [{'source_id': 'pg1', 'quote': 'names the e-governance'}],
                     'second_citations': [{'source_id': 'pg1', 'quote': 'names the e-governance'}]},
                    {'id': 'p2', 'finding': 'not_found', 'credited_as': 'not_found', 'second_finding': 'not_found',
                     'second_credited_as': 'not_found', 'citations': [], 'second_citations': []}]}
TRACE = {'indicator': 'AIQIF-C1.1', 'source_excerpts': PACKET, 'evidence_map': {'windows': [
    {'id': 'pg2', 'reasons': [{'step': 'supporting', 'requirement': CID, 'requirements': [CID]}]}]}}


class CaseTests(SimpleTestCase):
    def test_a_case_per_part_with_cited_or_tagged_passages(self):
        rows = past_cases.cases_for([RECORD], [TRACE], run_ref='r', versions={'credit_rule': 'x'}, source='stage1')
        self.assertEqual([(r['part_id'], r['passages_kind'], r['own_finding']) for r in rows],
                         [('p1', 'cited', 'full'), ('p2', 'tagged', 'not_found')])
        self.assertEqual(rows[0]['passages'][0]['source_id'], 'pg1')
        self.assertEqual(rows[1]['passages'][0]['source_id'], 'pg2')   # not found: what the judge was shown

    def test_the_majority_finding(self):
        self.assertEqual(past_cases._majority(['full', 'related', 'related']), 'related')
        self.assertEqual(past_cases._majority(['full', 'related', 'not_found']), 'related')


class SavingTests(TestCase):
    def setUp(self):
        self.college = Institution.objects.create(name='Synthetic College')
        self.vistas = Institution.objects.create(name='VISTAS', is_test=True)

    def run_for(self, institution, **inputs):
        sprint = Sprint.objects.create(institution=institution)
        run = CapabilityRun.objects.create(sprint=sprint, inputs=inputs, inputs_hash='x')
        CapabilityRunEvent.objects.create(run=run, state='completed', payload={
            'result': {'score': 1}, 'records': [RECORD], 'traces': [TRACE]})
        return run

    def test_a_published_run_saves_once_and_a_test_college_never(self):
        run = self.run_for(self.college)
        self.assertEqual(past_cases.save_for_run(run), 2)
        self.assertEqual(past_cases.save_for_run(run), 0)
        self.assertEqual(past_cases.save_for_run(self.run_for(self.vistas)), 0)
        self.assertEqual(PartCase.objects.count(), 2)

    def test_a_final_result_saves_only_what_it_re_judged(self):
        run = self.run_for(self.college, second_layer={'provisional_run_id': 'p', 'merge': [
            {'condition_id': CID, 'decision': 'replaced'}, {'condition_id': 'AIQIF-C1.1.F1', 'decision': 'no rise'}]})
        past_cases.save_for_run(run)
        self.assertEqual(set(PartCase.objects.values_list('source', flat=True)), {'rejudge'})

    def test_publishing_saves_the_cases(self):
        from .capability.publication import _save_past_cases
        run = self.run_for(self.college)
        _save_past_cases(run.pk)
        self.assertEqual(PartCase.objects.filter(run_ref=str(run.pk)).count(), 2)
        _save_past_cases('00000000-0000-0000-0000-000000000000')   # never raises

    def test_release_withdraw_and_sample(self):
        past_cases.save_for_run(self.run_for(self.college))
        first = past_cases.cut_release('first')
        self.assertEqual((first.number, first.case_count), (1, 2))
        self.assertEqual(past_cases.cut_release().case_count, 0)
        with self.assertRaises(ValueError):
            past_cases.withdraw(run_ref='x', reason='')
        run_ref = PartCase.objects.first().run_ref
        self.assertEqual(past_cases.withdraw(run_ref=run_ref, reason='wrong documents'), 2)
        self.assertEqual(past_cases.draw_sample(self.college, seed=1), [])   # nothing active left
        past_cases.save_for_run(self.run_for(self.college))
        self.assertEqual(len(past_cases.draw_sample(self.college, size=1, seed=1)), 1)

    def test_vistas_is_marked_by_the_migration(self):
        from importlib import import_module
        migration = import_module('apps.institutions.migrations.0005_past_cases')
        from django.apps import apps
        Institution.objects.create(name='VELS INSTITUTE OF SCIENCE, TECHNOLOGY AND ADVANCED STUDIES (VISTAS)')
        migration.mark_vistas(apps, None)
        self.assertTrue(all(Institution.objects.filter(name__icontains='VISTAS').values_list('is_test', flat=True)))
        self.assertFalse(Institution.objects.get(name='Synthetic College').is_test)


class AuditTests(TestCase):
    def setUp(self):
        sprint = Sprint.objects.create(institution=Institution.objects.create(name='Synthetic College'))
        run = CapabilityRun.objects.create(sprint=sprint, inputs={}, inputs_hash='x')
        CapabilityRunEvent.objects.create(run=run, state='completed', payload={
            'result': {'score': 1}, 'records': [RECORD], 'traces': [TRACE]})
        past_cases.save_for_run(run)

    def test_price_then_marks_against_the_wording_alone(self):
        cases = list(PartCase.objects.all())
        price = past_cases.price_audit(cases, 'claude-sonnet-5-5')
        self.assertEqual((price['cases'], price['requests']), (2, 1))
        self.assertGreater(price['input_tokens'], 0)
        seen = {}

        def call(system, content, schema, name):
            seen['content'] = content
            ids = schema['properties']['cases']['items']['properties']['case_id']['enum']
            return {'cases': [{'case_id': ids[0], 'finding': 'full', 'mark': 'agrees', 'reason': 'Shown.'},
                              {'case_id': ids[1], 'finding': 'related', 'mark': 'disagrees', 'reason': 'Partly.'}]}
        marks = past_cases.audit_cases(cases, call, model_name='stand-in')
        self.assertEqual(marks['agrees'] + marks['disagrees'], 2)
        self.assertNotIn('ruling', seen['content'])
        self.assertEqual(PartCase.objects.exclude(audit_mark='').count(), 2)


class LedgerTests(TestCase):
    def results(self, found):
        return [{'id': str(n), 'requirement': CID, 'part': 'p2', 'expected': 'related', 'found': f,
                 'right': f == 'related'} for n, f in enumerate(found)]

    def test_baseline_then_a_move_inside_and_outside_the_noise(self):
        base = past_cases.ledger_entry(self.results(['related'] * 8), label='1.0',
                                       repeat=self.results(['related'] * 7 + ['full']))
        self.assertTrue(base.passed)
        self.assertAlmostEqual(base.noise, 0.75 / 8, places=3)
        same = past_cases.ledger_entry(self.results(['related'] * 8), label='1.1')
        self.assertTrue(same.passed)
        lean = past_cases.ledger_entry(self.results(['full'] * 8), label='1.2')
        self.assertFalse(lean.passed)
        self.assertGreater(lean.unexplained_move, 0)
        named = past_cases.ledger_entry(self.results(['full'] * 8), label='1.3',
                                        explained_by=[{'change': 'middle step', 'parts': [f'{CID}:p2']}])
        self.assertEqual(named.unexplained_move, 0)
        self.assertEqual(DriftLedger.objects.count(), 4)


class StandardTests(TestCase):
    def test_a_new_run_freezes_the_name_and_bundle(self):
        frozen = standard.frozen()
        self.assertEqual(frozen['name'], standard.PLACEHOLDER)
        self.assertIn('credit_rule', frozen['bundle'])
        self.assertEqual(len(frozen['bundle_hash']), 64)
        self.assertFalse(standard.for_run({'standard': frozen})['older'])

    @override_settings(AI_READY_STANDARD_NAME='AI-READY Standard 1.1 (December 2026)')
    def test_an_older_result_says_so(self):
        info = standard.for_run({'standard': {'name': standard.PLACEHOLDER}})
        self.assertTrue(info['older'])
        self.assertIn('Scored under AI-READY Standard 1.0 (November 2026)', info['line'])
        self.assertIn('Standard 1.1', info['line'])
        self.assertIn('Scored before we named', standard.for_run({})['line'])
