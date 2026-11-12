from types import SimpleNamespace
from django.test import SimpleTestCase
from .verification.scope import read_scope, comparable


class TablePeriodScopeTests(SimpleTestCase):
    def fact(self, period=None, name='Infrastructure expenditure'):
        return SimpleNamespace(field_key='infrastructure_expenditure', field_name=name, data_type='currency',
            source_snippet='Report table: 2024-25 | 2023-24 | 2022-23; amounts: 120 | 80 | 60',
            scope={'period':period} if period else {})

    def test_each_cell_keeps_stated_period_without_claiming_deterministic_grounding(self):
        a,b = read_scope(self.fact('2023-24')),read_scope(self.fact('2022-23'))
        self.assertEqual(a['period'],'2023-24')
        self.assertEqual(a['sources']['period'],'extraction')
        self.assertFalse(comparable(a,b)[0])

    def test_multiple_headers_without_cell_scope_remain_undated(self):
        self.assertEqual(read_scope(self.fact())['period'],'')

    def test_explicit_field_period_precedes_unrelated_table_header(self):
        s = read_scope(self.fact('2023-24',name='Infrastructure expenditure 2022-23'))
        self.assertEqual(s['period'],'2022-23')
        self.assertEqual(s['sources']['period'],'deterministic')

    def test_one_period_repeated_is_still_unambiguous(self):
        f = self.fact('2022-23');f.source_snippet='AY 2024-25 budget; FY 2024-25 expenditure.'
        self.assertEqual(read_scope(f)['period'],'2024-25')
