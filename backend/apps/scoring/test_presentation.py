"""The plain presentation rules behind the leadership and detailed reports (capability/presentation.py)."""
from django.test import SimpleTestCase

from .capability import presentation as p


class PresentationRuleTests(SimpleTestCase):
    def test_quotes_prefer_full_sentences_about_ai_over_titles_and_table_rows(self):
        sentence = 'The focus areas of the Incubation Centre at VISTAS are Automations, IoT and Artificial Intelligence.'
        self.assertGreater(p.quote_quality(sentence, 1.0), p.quote_quality(sentence, 0.5))
        for bad in ('CURRICULUM & SYLLABUS', 'S. No: 48 | Programme: B.Tech CSE | Appeared: 58 | Passed: 56',
                    '[Table 1 on page 37 -- columns: Number of students]', '24DBBA28: 1. To introduce advanced data analysis tools.',
                    'Short.'):
            self.assertEqual(p.quote_quality(bad, 1.0), 0, bad)
        long = 'Every year the college runs an audit. ' * 10
        self.assertLessEqual(len(p.display_quote(long)), 190)
        self.assertTrue(p.display_quote(long).endswith('.'))

    def test_clean_text_drops_criterion_codes_and_names_a_document_once(self):
        names = ['NAAC SSR Latest Self-Study Report']
        text = ('The NAAC SSR Latest Self-Study Report shows audits, and registers in criteria 1 - 1.4.1 and criteria 6 - h. '
                'The NAAC SSR Latest Self-Study Report also shows surveys.')
        out = p.clean_text(text, names)
        self.assertEqual(out.count('NAAC SSR Latest Self-Study Report'), 1)
        self.assertIn('The same document also shows surveys.', out)
        self.assertNotIn('1.4.1', out)
        self.assertIn('the NAAC criterion files', out)
        self.assertEqual(p.doc_label('NAAC SSR  Latest Self-Study Report.pdf'), 'NAAC SSR Latest Self-Study Report')

    def test_one_step_per_area_the_basics_first_weakest_area_first(self):
        def indicator(code, weight):
            return {'code': code, 'pillar': code.split('.')[0], 'name': code, 'weight_units': weight,
                    'conditions': [{'id': f'{code}.{s}', 'text': f'practice {s}'} for s in ('F1', 'F2', 'A1', 'A2', 'O1', 'O2')]}
        result = {'indicators': [indicator(f'AIQIF-C{a}.{i}', 20 if i == 4 else 10) for a in (1, 2, 3, 4) for i in (1, 2, 3, 4)],
                  'documented': {'indicators': [{'code': 'AIQIF-C3.2', 'score': 10.0}]}}
        records = {f'AIQIF-C1.{i}.F{n}': {'credit': 1.0} for i in (1, 2, 3, 4) for n in (1, 2)}   # C1's basics shown
        records['AIQIF-C2.4.F1'] = {'credit': 1.0}                    # C2.4: one basic left, double weight
        records.update({f'AIQIF-C4.{i}.{s}': {'credit': 1.0} for i in (1, 2, 3, 4)
                        for s in ('F1', 'F2', 'A1', 'A2', 'O1', 'O2')})  # C4 complete: no step
        areas = [{'code': f'AIQIF-C{a}', 'score': s, 'room': 0} for a, s in ((1, 40), (2, 3), (3, 20), (4, 100))]
        actions = p.choose_actions(result, records, areas)
        self.assertEqual([a['area_code'] for a in actions], ['AIQIF-C2', 'AIQIF-C3', 'AIQIF-C1'])   # weakest first
        self.assertEqual([a['start_here'] for a in actions], [True, True, True])
        by = {a['area_code']: a for a in actions}
        # C1: every basic is shown, so its step is the next stage.
        self.assertEqual(by['AIQIF-C1']['step'], 'Put in use')
        self.assertTrue(all(c['id'].rsplit('.', 1)[-1].startswith('A') for c in by['AIQIF-C1']['conditions']))
        # C2: the basics first, then the most points: C2.4's one basic at double weight ties the others' two; on a tie
        # rubric order decides.
        self.assertEqual((by['AIQIF-C2']['code'], by['AIQIF-C2']['step']), ('AIQIF-C2.1', 'Set up'))
        # C3: at the same stage, the most points (C3.4 has double weight).
        self.assertEqual(by['AIQIF-C3']['code'], 'AIQIF-C3.4')
        self.assertTrue(all(1 <= len(a['conditions']) <= 2 for a in actions))
        self.assertEqual([a['start_here'] for a in p.choose_actions(result, records, areas, start_here=1)],
                         [True, False, False])
        # A tie on points and stage goes to the key indicator with more already in place.
        result['indicators'] = [i for i in result['indicators'] if i['code'] != 'AIQIF-C3.4']
        self.assertEqual({a['area_code']: a['code'] for a in p.choose_actions(result, records, areas)}['AIQIF-C3'],
                         'AIQIF-C3.2')


class ReadingFixesTests(SimpleTestCase):
    """26 Nov, from test 13's rendered reports: one rounding for the reports and the screens, and text that reads."""

    def test_scores_round_half_up_like_the_screens(self):
        from .capability.presentation import whole
        self.assertEqual([whole(62.5), whole(12.5), whole(26.14), whole(None)], [63, 13, 26, 0])

    def test_a_document_named_by_its_criterion_code_reads_as_words(self):
        from .capability.presentation import clean_text
        self.assertEqual(clean_text('Document criteria 1 - 1.4.2 notes action-taken reports.', []),
                         'A NAAC criterion file notes action-taken reports.')

    def test_older_fallback_text_is_not_printed_as_a_finding(self):
        from .capability.presentation import _no_prefix, _plain
        self.assertTrue(_plain({'found': 'Your Student Report, page 125 records: "Sl. No.: 5".'}))
        self.assertFalse(_plain({'found': 'The Student Report records placements.'}))
        self.assertEqual(_no_prefix('Next step: show an AI-relevant opportunity is identified.'),
                         'Show an AI-relevant opportunity is identified.')

    def test_a_quotation_too_short_to_read_is_replaced_or_left_out(self):
        from .capability.presentation import _readable_cite
        short = {'quote': 'The firewall is upgraded to', 'source_id': 'p1'}
        longer = {'quote': 'The institution upgraded its firewall after the audit of its network security.', 'source_id': 'p2'}
        self.assertEqual(_readable_cite(short, [short, longer]), longer)
        self.assertEqual(_readable_cite(short, [short]), {'quote': '', 'source_id': 'p1'})

    def test_a_number_and_its_level_never_disagree(self):
        from .capability.presentation import level
        self.assertEqual((level(39.6)['name'], level(39.4)['name']), ('Prepared', 'Getting there'))
        self.assertEqual((level(26.14)['points_to_next'], level(39.4)['points_to_next']), (14, 1))

    def test_a_done_when_line_stands_alone_and_keeps_rubric_order(self):
        from .capability.next_steps import done_when
        from .capability.engine import release
        from .capability.presentation import _and, _standalone, step_view
        by = {c['id']: c for i in release()['indicators'] for c in i['conditions']}
        alone = _and(_standalone([{'id': 'AIQIF-C1.2.F2', 'done_when': done_when(by['AIQIF-C1.2.F2'])}]))
        self.assertNotIn('those', alone)
        self.assertTrue(alone.startswith('there is a set route'))
        step = step_view({'requirements': [{'id': i, 'done_when': done_when(by[i])}
                                           for i in ('AIQIF-C4.2.F2', 'AIQIF-C4.2.F1')]})
        self.assertLess(step['done_when_text'].index('aimed at a named academic role'),
                        step['done_when_text'].index('for that role'))
