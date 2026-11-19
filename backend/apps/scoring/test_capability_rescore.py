"""capability_rescore: an export's credits recomputed under today's rule from its stored part findings."""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from .capability.engine import documented, release
from .capability.layer2 import _recredit
from .management.commands.capability_rescore import rescore


def part(pid, first, second):
    return {'id': pid, 'credited_as': first, 'second_credited_as': second}


class RescoreTests(SimpleTestCase):
    def setUp(self):
        rubric = release()
        ids = [c['id'] for i in rubric['indicators'] for c in i['conditions']]
        self.related, self.withheld = ids[0], ids[1]
        records = [{'condition_id': cid, 'state': 'unknown', 'credit': 0.0} for cid in ids]
        # Scored when related evidence was worth 0.5: both parts related in both passes.
        records[0] = {'condition_id': self.related, 'state': 'unknown', 'credit': 0.5,
                      'parts': [part('p1', 'full', 'full'), part('p2', 'related', 'related')]}
        records[1] = {'condition_id': self.withheld, 'state': 'unknown', 'credit': 0.0, 'validation_issue': 'held',
                      'parts': [part('p1', 'full', 'full'), part('p2', 'full', 'full')]}
        self.report = {'rubric': rubric, 'assessment': {'records': records, 'result': {'score': 0.15}}}

    def test_credits_follow_todays_rule_and_nothing_else_changes(self):
        out, changes = rescore(self.report)
        record = out['assessment']['records'][0]
        self.assertEqual(record['credit'], _recredit(record['parts'], self.related))
        self.assertLess(record['credit'], 0.5)   # related evidence is worth less today
        self.assertEqual([c['condition_id'] for c in changes], [self.related])
        self.assertEqual(out['assessment']['records'][1]['credit'], 0.0)   # withheld stays withheld
        credits = {r['condition_id']: r['credit'] for r in out['assessment']['records']}
        self.assertEqual(out['assessment']['result']['score'], round(documented(credits, release())['overall'], 2))
        self.assertEqual(out['rescored']['score_before'], 0.15)
        self.assertEqual(self.report['assessment']['records'][0]['credit'], 0.5)   # the input is not changed

    def test_the_command_writes_a_file_the_comparison_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = os.path.join(folder, 'in.json'), os.path.join(folder, 'out.json')
            with open(source, 'w') as f:
                json.dump(self.report, f)
            out = StringIO()
            call_command('capability_rescore', source, '--out', target, stdout=out)
            self.assertIn("under today's rule", out.getvalue())
            with open(target) as f:
                self.assertIn('rescored', json.load(f))
