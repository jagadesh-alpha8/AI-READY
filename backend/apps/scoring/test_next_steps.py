"""Next steps written for the college (issue 61): the code chooses, labels and points; the model only writes text for
actions already chosen, from the run's saved passages, and every claim is checked; anything that fails is the plain
checklist. Runs without written steps (test 13, today's live runs) render with the fallback."""
import json
import re
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from . import test_product_flow as flow   # the module, not the class: importing it would run its tests twice
from .capability import next_steps as ns
from .capability.engine import release
from .models import CapabilityNextSteps, DepthQuestion, DepthResponse, SecondLayerJob


class DoneWhenTests(SimpleTestCase):
    def test_one_checked_line_per_requirement_of_the_current_rubric(self):
        rubric = release()
        conditions = [c for i in rubric['indicators'] for c in i['conditions']]
        lines = ns._done_when_file()
        self.assertEqual(len(conditions), 216)
        self.assertEqual(set(lines), {c['id'] for c in conditions})
        for c in conditions:
            entry = lines[c['id']]
            # Written for exactly this sentence: a changed requirement is not shown with an old line.
            self.assertEqual(entry['sentence_hash'], ns.sentence_hash(c['text']), c['id'])
            line = ns.done_when(c)
            self.assertEqual(line, entry['done_when'])
            self.assertTrue(line.endswith('.') and line[0].islower() or line.startswith('AI'), c['id'])
            self.assertIsNone(re.search(r'AIQIF|\bC\d\.\d|\b[FAO]\d\b', line), c['id'])

    def test_a_changed_sentence_shows_the_sentence_not_an_old_line(self):
        condition = {'id': 'AIQIF-C1.1.F1', 'text': 'An approved plan names an AI priority and a budget.'}
        self.assertEqual(ns.done_when(condition), 'an approved plan names an AI priority and a budget.')


class LabelTests(SimpleTestCase):
    def test_labels_come_from_credit_and_answers(self):
        self.assertIsNone(ns.label('X', 1.0))
        self.assertEqual(ns.label('X', 0.25), ns.PARTLY)
        self.assertEqual(ns.label('X', 0.0), ns.NOT_FOUND)
        # "Not yet in place" (final result only) means not started; it never overrides credit.
        self.assertEqual(ns.label('X', 0.0, frozenset({'X'})), ns.NOT_STARTED)
        self.assertEqual(ns.label('X', 0.5, frozenset({'X'})), ns.PARTLY)


# ---------------------------------------------------------------- the checks, on a hand-made packet

def given(credited=True):
    passages = [
        {'id': 'P1', 'role': 'credited' if credited else 'seen', 'where': 'Self-Study Report, page 141',
         'source_id': 's1', 'text': 'The e-Varsity ERP digitises student, faculty and staff data. The Board of '
                                    'Studies approved 3 new electives in 2023.'},
        {'id': 'P2', 'role': 'seen', 'where': 'Annual Quality Assurance Report, page 9', 'source_id': 's2',
         'text': 'The Internal Quality Assurance Cell reviews feedback every semester.'},
        {'id': 'P3', 'role': 'related', 'where': 'Self-Study Report, page 113', 'source_id': 's3',
         'text': 'Faculty attended a workshop on Turnitin and DrillBit plagiarism checking.'},
    ]
    return {'college': {'name': 'Vels Institute', 'type': 'university', 'size': {}}, 'area': 'Data and infrastructure',
            'topic': 'Data readiness', 'stage': 'Set up',
            'requirements': [{'what_it_asks': 'A register identifies relevant institutional datasets or systems.',
                              'done_when': 'Done when: a register lists the relevant datasets or systems your institution holds.',
                              'label': ns.PARTLY if credited else ns.NOT_FOUND, 'what_counts': [],
                              'counts_only_as_related': []}],
            'passages': passages}


def good(credited=True):
    return {'action': 'Turn your e-Varsity ERP records into a register of the data your offices hold.',
            'have': [{'text': 'Your "e-Varsity ERP digitises student, faculty and staff data".', 'passage_ids': ['P1']}]
            if credited else [],
            'related': [{'text': 'The Internal Quality Assurance Cell already reviews feedback; a starting point, '
                                 'not a register.', 'passage_ids': ['P2']}],
            'not_found': 'We did not find a list of the datasets and systems with what each holds.',
            'first_step': 'Ask the Board of Studies and the ERP team to list each system and the data it holds.',
            'owner': {'name': 'Internal Quality Assurance Cell', 'kind': 'named_in_documents', 'passage_id': 'P2'}}


class ValidationTests(SimpleTestCase):
    def check(self, output, packet=None):
        return ns.validate(packet or given(), output)

    def test_a_grounded_step_passes_with_its_sources(self):
        text, problems = self.check(good())
        self.assertEqual(problems, [])
        self.assertEqual(text['have'][0]['sources'], ['Self-Study Report, page 141'])
        self.assertEqual(text['owner'], {'name': 'Internal Quality Assurance Cell', 'suggested': False,
                                         'source': 'Annual Quality Assurance Report, page 9'})
        text, problems = self.check(good(credited=False), given(credited=False))
        self.assertEqual(problems, [])

    def assert_rejected(self, change, words, packet=None):
        output = good()
        change(output)
        text, problems = self.check(output, packet)
        self.assertIsNone(text)
        self.assertTrue(any(words in p for p in problems), problems)

    def test_rejections(self):
        cases = [
            (lambda o: o['have'][0].update(passage_ids=['P9']), 'were not given'),
            (lambda o: o['have'][0].update(passage_ids=['P2']), 'only "credited" passages'),
            (lambda o: o['have'][0].update(text='Your "ERP covers every alumnus".'), 'not in the passages it cites'),
            (lambda o: o.update(first_step='Set aside 5 lakh for a data register.'), 'number 5'),
            (lambda o: o.update(first_step='Hold twelve meetings on it.'), 'number "twelve"'),
            (lambda o: o.update(action='You lack a data register, so build one.'), 'claims something is absent'),
            (lambda o: o.update(not_found='There is no data register.'), 'claims something is absent'),
            (lambda o: o.update(not_found='The register is still to come.'), 'did not find'),
            (lambda o: o.update(action='Meet requirement C6.2.F1 with a register.'), 'codes or internal words'),
            (lambda o: o.update(first_step='Ask Dr. Raman to list the systems.'), 'names a person'),
            (lambda o: o.update(first_step='Ask the IT team to load it into Salesforce.'), 'names "Salesforce"'),
            (lambda o: o['owner'].update(name='Data Governance Council'), 'copied exactly'),
            (lambda o: o['owner'].update(kind='suggested_role', name='IQAC', passage_id=''), 'suggested role'),
            (lambda o: o['owner'].update(kind='suggested_role', name='Prof. K. Rao', passage_id=''), 'never name a person'),
            (lambda o: o.update(action=''), 'action is empty'),
            (lambda o: o.update(action='Improve all departments.'), 'wider than the passages'),
        ]
        for change, words in cases:
            with self.subTest(words=words):
                self.assert_rejected(change, words)
        # Nothing credited: "have" stays empty; what they can build on goes under related.
        self.assert_rejected(lambda o: None, 'have must be empty', given(credited=False))

    def test_a_suggested_generic_role_passes(self):
        output = good()
        output['owner'] = {'name': 'the office responsible for quality assurance', 'kind': 'suggested_role',
                           'passage_id': ''}
        text, problems = self.check(output)
        self.assertEqual(problems, [])
        self.assertEqual(text['owner'], {'name': 'the office responsible for quality assurance', 'suggested': True,
                                         'source': None})


class WriteTests(SimpleTestCase):
    def target(self):
        packet = given()
        action = {'code': 'AIQIF-C6.2', 'title': 'Data readiness', 'area': 'Data and infrastructure',
                  'area_code': 'AIQIF-C6', 'points': 1.2, 'step': 'Set up',
                  'conditions': [{'id': 'AIQIF-C6.2.F1', 'text': 'A register identifies relevant institutional '
                                                                 'datasets or systems.'}]}
        return {'run_id': 'r', 'event_id': 1, 'actions': [action]}, packet

    def test_a_retry_fixes_the_first_answer_and_failures_fall_back(self):
        target, packet = self.target()
        answers = [dict(good(), action='You lack a register.'), good()]
        with patch.object(ns, 'packet', return_value=packet):
            out = ns.write(target, lambda *a: answers.pop(0))
        self.assertEqual((out['calls'], list(out['actions']), out['fallbacks']), (2, ['AIQIF-C6.2:AIQIF-C6.2.F1'], []))
        with patch.object(ns, 'packet', return_value=packet):
            out = ns.write(target, lambda *a: dict(good(), action='You lack a register.'))
        self.assertEqual((out['calls'], out['actions'], out['fallbacks']), (2, {}, ['AIQIF-C6.2:AIQIF-C6.2.F1']))
        self.assertTrue(out['errors']['AIQIF-C6.2:AIQIF-C6.2.F1'])

        def broken(*args):
            raise TimeoutError('slow')
        with patch.object(ns, 'packet', return_value=packet):
            out = ns.write(target, broken, skip_error=lambda exc: isinstance(exc, TimeoutError))
            self.assertEqual((out['calls'], out['fallbacks']), (1, ['AIQIF-C6.2:AIQIF-C6.2.F1']))
            with self.assertRaises(TimeoutError):   # anything else (a spent budget, a cancelled job) still stops it
                ns.write(target, broken)
            out = ns.write(target, lambda *a: good(), max_calls=0)
        self.assertEqual((out['calls'], out['errors']['AIQIF-C6.2:AIQIF-C6.2.F1']), (0, ['no call left']))


# ---------------------------------------------------------------- end to end, on the product flow's stand-in model

@override_settings(**flow.SETTINGS)
class NextStepsFlowTests(APITestCase):
    setUp = flow.ProductFlowTests.setUp
    for _name in [n for n in dir(flow.ProductFlowTests) if n.startswith('reply_') or n in (
            'model', 'service', 'assess', 'post', 'run_queued', 'document')]:
        locals()[_name] = getattr(flow.ProductFlowTests, _name)
    del _name

    def reply_next_step(self, payload):
        """A careful writer: credits only from credited passages, a generic owner, plain words."""
        self.packets = getattr(self, 'packets', []) + [payload]
        credited = [p['id'] for p in payload['passages'] if p['role'] == 'credited']
        others = [p['id'] for p in payload['passages'] if p['role'] != 'credited']
        return {'action': f"Put this in place in your {payload['topic'].lower()} work, building on what you have.",
                'have': [{'text': 'You already have part of this on record.', 'passage_ids': credited[:1]}] if credited else [],
                'related': [{'text': 'This is a starting point, not the practice itself.', 'passage_ids': others[:1]}]
                if others else [],
                'not_found': 'We did not find the rest of this in your documents.',
                'first_step': 'Ask the people involved to write down how it works today.',
                'owner': {'name': 'the office responsible for quality assurance', 'kind': 'suggested_role',
                          'passage_id': ''}}

    def detail(self, run):
        return self.client.get(f'{self.base}/{run.pk}').data

    def test_written_once_shown_everywhere_and_never_regenerated(self):
        run = self.assess()
        before = self.detail(run)
        steps = before['next_steps']
        # Without written steps: the code's choice with the plain checklist wording.
        self.assertFalse(steps['written'])
        self.assertTrue(4 <= len(steps['actions']) <= 6 or len(steps['actions']) == len(
            [k for k in {a['code'] for a in steps['actions']}]), steps['actions'])
        self.assertLessEqual(len(steps['actions']), 6)
        for a in steps['actions']:
            self.assertFalse(a['generated'])
            self.assertTrue(a['owner']['suggested'])
            for r in a['requirements']:
                self.assertIn(r['label'], (ns.PARTLY, ns.NOT_FOUND))
                self.assertTrue(r['done_when'])
        unshown = [r['condition_id'] for r in run.events.get(state='completed').payload['records']
                   if ns.credit_of(r) < 1]
        self.assertEqual(sorted(i['id'] for items in steps['checklist'].values() for i in items), sorted(unshown))
        chosen = [a['key'] for a in steps['actions']]

        self.post(f'{self.base}/{run.pk}/second-layer/jobs', {'operation': 'next_steps'}, key='steps', expect=202)
        job = self.run_queued()[0]
        self.assertEqual((job.operation, job.result['written'], job.result['fallbacks']), ('next_steps', len(chosen), 0))
        self.assertEqual(job.result['calls'], len(chosen))   # one per chosen action
        # Only the run's saved record went to the model: passages are from the judge's packets and citations.
        frozen = {s['id'] for s in run.inputs['sources']}
        for packet in self.packets:
            self.assertTrue(all(p['source_id'] in frozen for p in packet['passages']))
            self.assertNotIn('label', json.dumps(packet['college']))

        after = self.detail(run)
        self.assertNotEqual(after['version'], before['version'])
        steps = after['next_steps']
        self.assertTrue(steps['written'])
        self.assertEqual([a['key'] for a in steps['actions']], chosen)   # the same actions, now with their text
        self.assertTrue(all(a['generated'] and a['first_step'] and a['action'] for a in steps['actions']))
        self.assertEqual(steps['version'], ns.VERSION)
        # Reloads and reports read the stored text; nothing is written again.
        for _ in range(2):
            self.detail(run)
        html = self.client.get(f'{self.base}/{run.pk}/report', {'file': 'html', 'audience': 'summary'})
        self.assertIn('Ask the people involved to write down how it works today.', html.content.decode())
        self.assertIn('Done when:', html.content.decode())
        self.assertEqual(CapabilityNextSteps.objects.filter(run=run).count(), 1)
        self.assertEqual(SecondLayerJob.objects.filter(run=run, operation='next_steps').count(), 1)

        # Stored text for a different choice (a code change) is not used: that action falls back.
        row = CapabilityNextSteps.objects.get(run=run)
        row.payload = {**row.payload, 'actions': {k + '-old': v for k, v in row.payload['actions'].items()}}
        row.save()
        self.assertFalse(any(a['generated'] for a in self.detail(run)['next_steps']['actions']))

    def test_final_result_marks_not_started_from_the_answers(self):
        run = self.assess()
        missing = [r['condition_id'] for r in run.events.get(state='completed').payload['records']
                   if ns.credit_of(r) == 0]
        question = DepthQuestion.objects.create(run_ref=str(run.pk), kind='missing', indicator_code='AIQIF-C1.1',
                                                condition_ids=missing[:1], text='Is it in place?', rank=999,
                                                spec_version='t')
        DepthResponse.objects.create(question=question, kind='answer', choice='not_yet', answer='Not yet.')
        self.assertEqual(ns.not_started_for(str(run.pk)), frozenset(missing[:1]))
        # A later answer replaces it.
        DepthResponse.objects.create(question=question, kind='answer', choice='partly', answer='We have begun.')
        self.assertEqual(ns.not_started_for(str(run.pk)), frozenset())
        # At Stage 1 no answer is used: the label is never "not started".
        labels = {i['label'] for items in self.detail(run)['next_steps']['checklist'].values() for i in items}
        self.assertNotIn(ns.NOT_STARTED, labels)
