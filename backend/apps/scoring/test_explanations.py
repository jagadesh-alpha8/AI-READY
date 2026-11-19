"""Score explanations (capability/explanations.py): the input is the run's own record, every claim is checked against
it, a rejected area is asked again once, and anything still failing gets a plain factual fallback."""
import copy

from django.test import SimpleTestCase

from .capability import explanations
from .capability.engine import release

QUOTE = 'The Governing Council approved the Strategic Plan 2023-28, which sets an AI-enabled campus as a goal.'


def writer(area, *, spoil=None):
    """A stand-in that writes a valid answer for an area input; spoil(entry, requirement) may then break one."""
    requirements, indicators = [], []
    for indicator in area['indicators']:
        indicators.append({'code': indicator['code'], 'found': 'You have a clear starting point here.',
                           'text': 'Some requirements are shown and others are next steps.', 'looked': '',
                           'next_step': 'The steps below show what to add.'})
        for requirement in indicator['requirements']:
            credited = requirement['result'] in ('shown in full', 'partly shown')
            full = requirement['result'] == 'shown in full'
            entry = {'condition_id': requirement['condition_id'],
                     'found': (f"Your {requirement['quotations'][0]['document']} shows this." if credited else ''),
                     'quote_ids': ['Q1'] if credited else [],
                     'text': 'This is shown.' if full else 'This is partly shown.' if credited else 'Not yet shown.',
                     'looked': '' if full else 'We read the documents listed for this area.',
                     'next_step': '' if full else 'Add a record that shows the missing part.'}
            if spoil:
                spoil(entry, requirement)
            requirements.append(entry)
    return {'area': {'found': 'Good foundations.', 'text': 'A solid start.', 'looked': '', 'next_step': ''},
            'indicators': indicators, 'requirements': requirements}


class ExplanationTests(SimpleTestCase):
    def setUp(self):
        rubric = release()
        self.rubric = {**rubric, 'indicators': [i for i in rubric['indicators'] if i['pillar'] == 'AIQIF-C1']}
        conditions = [c for i in self.rubric['indicators'] for c in i['conditions']]
        self.full, self.partial = conditions[0]['id'], conditions[1]['id']
        records = []
        for condition in conditions:
            cid = condition['id']
            if cid == self.full:
                records.append({'condition_id': cid, 'state': 'met', 'credit': 1.0,
                                'parts': [{'id': 'p1', 'credited_as': 'full', 'second_credited_as': 'full'},
                                          {'id': 'p2', 'credited_as': 'full', 'second_credited_as': 'full'}],
                                'citations': [{'source_id': 'page-1', 'quote': QUOTE}]})
            elif cid == self.partial:
                records.append({'condition_id': cid, 'state': 'unknown', 'credit': 0.5,
                                'parts': [{'id': 'p1', 'credited_as': 'full', 'second_credited_as': 'full'},
                                          {'id': 'p2', 'credited_as': 'not_found', 'second_credited_as': 'not_found'}],
                                'citations': [{'source_id': 'page-1', 'quote': QUOTE}]})
            else:
                records.append({'condition_id': cid, 'state': 'unknown', 'credit': 0.0, 'cause': 'assessed',
                                'parts': [], 'citations': []})
        self.target = {'run_id': 'run-1', 'event_id': 7, 'rubric': self.rubric, 'records': records,
                       'traces': [{'indicator': i['code'], 'source_ids': ['page-1', 'page-2']}
                                  for i in self.rubric['indicators']],
                       'sources': {'page-1': {'id': 'page-1', 'document_id': 'd1', 'page_number': 3},
                                   'page-2': {'id': 'page-2', 'document_id': 'd2', 'page_number': 41}},
                       'names': explanations.document_names([{'document_id': 'd1', 'filename': 'Strategic_Plan.pdf'},
                                                             {'document_id': 'd2', 'filename': 'SSR 2024.pdf'}]),
                       'merge': [], 'plan': {'condition_ids': [self.partial]}}
        self.area = explanations.area_input('AIQIF-C1', self.target)

    def model(self, *answers):
        calls = []

        def call(system, content, schema, name):
            calls.append(content)
            answer = answers[min(len(calls), len(answers)) - 1]
            return answer(self.area) if callable(answer) else answer
        call.calls = calls
        return call

    def test_the_input_is_the_record_with_documents_named(self):
        requirement = self.area['indicators'][0]['requirements'][0]
        self.assertEqual(requirement['result'], 'shown in full')
        self.assertEqual(requirement['quotations'][0], {'id': 'Q1', 'document': 'Strategic Plan, page 3', 'text': QUOTE})
        partial = self.area['indicators'][0]['requirements'][1]
        self.assertEqual(partial['result'], 'partly shown')
        self.assertTrue(partial['still_missing'])
        self.assertTrue(partial['in_priority_plan'])
        self.assertEqual(self.area['indicators'][0]['documents_read'][0]['document'], 'Strategic Plan')
        self.assertEqual(self.area['name'], 'Leadership and investment')

    def test_a_valid_answer_is_kept_whole(self):
        written = explanations.explain(self.target, self.model(writer))
        self.assertEqual((written['calls'], written['fallbacks'], written['errors']), (1, [], {}))
        self.assertEqual(len(written['requirements']), 24)
        self.assertEqual(written['requirements'][self.full]['quote_ids'], ['Q1'])
        self.assertEqual(set(written['indicators']), {i['code'] for i in self.rubric['indicators']})
        self.assertIn('AIQIF-C1', written['areas'])

    def test_every_check_catches_its_claim(self):
        def at(cid, change):
            return lambda entry, requirement: change(entry) if entry['condition_id'] == cid else None
        cases = {
            'an invented number': (self.full, lambda e: e.update(found='Your plan shows this across 40 programmes.')),
            'a quotation not in its quotes': (self.full, lambda e: e.update(found='It says "AI in every course".')),
            'an unknown quote id': (self.full, lambda e: e.update(quote_ids=['Q9'])),
            'credit without a quotation': (self.full, lambda e: e.update(quote_ids=[])),
            'an overclaim on partial credit': (self.partial, lambda e: e.update(text='This is fully in place.')),
            'found where nothing is credited': (None, lambda e: e.update(found='You have this.')),
            'no next step for a gap': (self.partial, lambda e: e.update(next_step='')),
            'no "where we looked" for a gap': (self.partial, lambda e: e.update(looked='')),
            'a next step where all is shown': (self.full, lambda e: e.update(next_step='Do more.')),
            'machinery': (self.partial, lambda e: e.update(text='AIQIF-C1.1.F2 is partly met.')),
        }
        nothing = next(r['condition_id'] for r in self.area['indicators'][0]['requirements']
                       if r['result'] == 'not yet shown')
        for name, (cid, change) in cases.items():
            with self.subTest(name):
                answer = writer(self.area, spoil=at(cid or nothing, change))
                passed, errors = explanations.validate(self.area, answer)
                self.assertTrue(errors, name)
                self.assertNotIn(cid or nothing, passed['requirements'])

    def test_quoting_exact_words_from_a_quotation_passes(self):
        answer = writer(self.area, spoil=lambda e, r: e.update(found='Your plan sets "an AI-enabled campus" as a goal.')
                        if e['condition_id'] == self.full else None)
        passed, errors = explanations.validate(self.area, answer)
        self.assertEqual(errors, [])
        self.assertIn(self.full, passed['requirements'])

    def test_a_rejected_area_is_asked_again_with_its_problems(self):
        bad = writer(self.area, spoil=lambda e, r: e.update(found='Across 40 programmes.')
                     if e['condition_id'] == self.full else None)
        model = self.model(bad, writer)
        written = explanations.explain(self.target, model)
        self.assertEqual((written['calls'], written['fallbacks']), (2, []))
        self.assertIn('your_previous_answer_had_these_problems', model.calls[1])
        self.assertIn('the number 40', model.calls[1])

    def test_what_still_fails_gets_a_plain_fallback_and_never_an_unchecked_claim(self):
        bad = writer(self.area, spoil=lambda e, r: e.update(found='Across 40 programmes.')
                     if e['condition_id'] == self.full else None)
        written = explanations.explain(self.target, self.model(bad, bad))
        self.assertEqual(written['fallbacks'], [self.full])
        fallback = written['requirements'][self.full]
        self.assertTrue(fallback['fallback'])
        self.assertIn(QUOTE[:60], fallback['found'])
        self.assertNotIn('40 programmes', str(written))
        self.assertTrue(written['errors']['AIQIF-C1'])
        # A model that returns nothing usable: every entry falls back, still complete.
        written = explanations.explain(self.target, self.model({}, {}))
        self.assertEqual(len(written['requirements']), 24)
        self.assertEqual(len(written['fallbacks']), 24 + 4 + 1)
        partial = written['requirements'][self.partial]
        self.assertTrue(partial['next_step'].startswith('Next step: show '))
        self.assertIn('Strategic Plan', partial['looked'])

    def test_attach_puts_explanations_where_the_front_end_reads_them(self):
        written = explanations.explain(self.target, self.model(writer))
        assessment = {'records': copy.deepcopy(self.target['records']),
                      'result': {'indicators': [{'code': i['code']} for i in self.rubric['indicators']],
                                 'documented': {'indicators': [{'code': i['code'], 'score': 10}
                                                               for i in self.rubric['indicators']],
                                                'pillars': [{'code': 'AIQIF-C1', 'score': 10}]}}}
        out = explanations.attach(assessment, written)
        self.assertEqual(out['records'][0]['explanation']['found'], written['requirements'][self.full]['found'])
        self.assertIsNone(out['records'][0]['explanation']['next_step'])   # empty fields read as absent
        self.assertIn('text', out['result']['indicators'][0]['explanation'])
        self.assertEqual(out['result']['documented']['pillars'][0]['explanation']['text'], 'A solid start.')
        self.assertNotIn('explanation', assessment['records'][0])   # the stored payload is never changed
        self.assertIs(explanations.attach(assessment, None), assessment)
