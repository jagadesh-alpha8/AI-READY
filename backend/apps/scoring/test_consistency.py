from django.test import SimpleTestCase

from apps.scoring.capability.consistency import between_runs, within_run
from apps.scoring.capability.engine import release


def export(credits_by_pass):
    rubric = release()
    ids = [c['id'] for i in rubric['indicators'] for c in i['conditions']]
    records = []
    for n, cid in enumerate(ids):
        passes = [p[n % len(p)] for p in credits_by_pass]
        records.append({'condition_id': cid, 'state': 'unknown', 'credit': sorted(passes)[len(passes) // 2],
                        'pass_credits': passes, 'citations': [], 'reason': ''})
    return {'rubric': rubric, 'assessment': {'records': records}}


class ConsistencyTests(SimpleTestCase):
    def test_identical_passes_are_fully_consistent(self):
        result = within_run(export([[1.0, 0.5, 0.0], [1.0, 0.5, 0.0]]))
        self.assertEqual((result['pass_agreement'], result['score_gap']), (1.0, 0.0))
        self.assertTrue(all(result['checks'].values()))

    def test_a_flipping_pass_fails_the_checks(self):
        result = within_run(export([[1.0, 0.0], [0.0, 1.0]]))
        self.assertEqual(result['pass_agreement'], 0.0)
        self.assertFalse(result['checks']['pass_agreement'])
        self.assertTrue(result['largest_disagreements'])

    def test_between_runs_lists_gained_conditions(self):
        new, old = export([[1.0], [1.0]]), export([[0.0], [0.0]])
        result = between_runs(new, old)
        self.assertEqual(len(result['gained']), 216)
        self.assertFalse(result['checks']['run_score_gap'])

    def test_strict_export_without_pass_credits(self):
        report = export([[1.0]])
        for r in report['assessment']['records']:
            r.pop('pass_credits')
        self.assertFalse(within_run(report)['available'])
