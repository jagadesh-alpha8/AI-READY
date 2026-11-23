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

    def test_actions_cover_the_areas_with_most_to_gain_first_at_most_two_per_area(self):
        def indicator(code, weight):
            return {'code': code, 'pillar': code.split('.')[0], 'name': code, 'weight_units': weight,
                    'conditions': [{'id': f'{code}.{s}', 'text': f'practice {s}'} for s in ('F1', 'F2', 'A1', 'A2', 'O1', 'O2')]}
        result = {'indicators': [indicator(f'AIQIF-C{a}.{i}', 10) for a in (1, 2, 3) for i in (1, 2, 3, 4)]}
        records = {f'AIQIF-C1.{i}.F{n}': {'credit': 1.0} for i in (1, 2, 3, 4) for n in (1, 2)}   # C1's foundations shown
        areas = [{'code': f'AIQIF-C{a}', 'room': r} for a, r in ((1, 5), (2, 30), (3, 20))]
        actions = p.choose_actions(result, records, {}, {}, areas, [], 120, limit=5)
        self.assertEqual(len(actions), 5)
        by_area = {}
        for a in actions:
            by_area[a['area_code']] = by_area.get(a['area_code'], 0) + 1
        self.assertLessEqual(max(by_area.values()), 2)
        c1 = [a for a in actions if a['area_code'] == 'AIQIF-C1']
        self.assertTrue(all(a['step'] == 'Put in use' for a in c1))   # the first unfinished stage
        self.assertTrue(all(a['lead'] for a in actions))
        self.assertEqual(actions, sorted(actions, key=lambda a: -a['points']))
