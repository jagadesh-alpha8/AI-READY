"""Exercise the actual offline command without Django setup, database or inference."""
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from django.core.management.base import CommandError
from .management.commands.evaluate_ladder_candidate import Command

DOCS = Path(__file__).resolve().parents[3] / 'docs/capability'


class CandidateCommandTests(TestCase):
    def setUp(self):
        self.candidate = json.loads((DOCS / 'ladder_candidate_v0_3.json').read_text())
        self.profiles = json.loads((DOCS / 'ladder_profiles_candidate_v0_2.json').read_text())
        self.cases = json.loads((DOCS / 'ladder_candidate_acceptance_cases_v0_3.json').read_text())['cases']

    def run_command(self, candidate, profiles, snapshot):
        with TemporaryDirectory() as temp:
            values = {'candidate': candidate, 'profiles': profiles, 'snapshot': snapshot}
            paths = {}
            for name, value in values.items():
                path = Path(temp) / (name + '.json')
                path.write_text(json.dumps(value))
                paths[name] = str(path)
            before = {name: Path(path).read_bytes() for name, path in paths.items()}
            out = StringIO()
            Command(stdout=out).handle(**paths)
            self.assertEqual(before, {name: Path(path).read_bytes() for name, path in paths.items()})
            return json.loads(out.getvalue())

    def test_seven_snapshots_run_without_input_writes_or_badge_awards(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                result = self.run_command(self.candidate, self.profiles, case)
                self.assertEqual(result['proposed_silver_gate']['status'], case['expected_gate'])
                self.assertEqual(result['badge_status'], 'not_awarded_uncalibrated')
                self.assertIsNone(result['headline_score'])

    def test_stale_release_hash_or_methodology_is_rejected(self):
        for key in ('methodology', 'candidate_hash', 'profile_release_hash'):
            snapshot = {**self.cases[0], key: 'obsolete'}
            with self.assertRaises(CommandError):
                self.run_command(self.candidate, self.profiles, snapshot)

    def test_malformed_objects_fail_as_command_errors(self):
        for candidate, profiles, snapshot in (
            (None, self.profiles, self.cases[0]),
            (self.candidate, None, self.cases[0]),
            (self.candidate, self.profiles, []),
            (self.candidate, self.profiles, {**self.cases[0], 'decisions': []}),
            (self.candidate, self.profiles, {**self.cases[0], 'gate_context': []}),
        ):
            with self.assertRaises(CommandError):
                self.run_command(candidate, profiles, snapshot)
