"""Evaluate a separately adjudicated candidate snapshot, offline only."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.experimental_candidate import digest, evaluate_candidate


class Command(BaseCommand):
    help = 'Evaluate a version-bound candidate snapshot offline; never updates an institutional assessment.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('candidate')
        parser.add_argument('profiles')
        parser.add_argument('snapshot')

    def handle(self, *args, **options):
        try:
            candidate, profiles, snapshot = [json.loads(Path(options[k]).read_text())
                                              for k in ('candidate', 'profiles', 'snapshot')]
            if (snapshot['methodology'] != candidate['version']
                    or snapshot['candidate_hash'] != digest(candidate)
                    or snapshot['profile_release_hash'] != digest(profiles)):
                raise ValueError('Snapshot release mismatch.')
            result = evaluate_candidate(candidate, profiles, snapshot['decisions'],
                                        profile_id=snapshot['profile'], gate_context=snapshot['gate_context'])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise CommandError('A valid candidate, profile release and matching adjudicated snapshot are required.') from exc
        self.stdout.write(json.dumps(result, indent=2))
