"""Compare exported capability assessment JSON offline; never invokes an AI provider."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.engine import release
from apps.scoring.capability.validation import compare_export


class Command(BaseCommand):
    help = 'Offline numerical replay, optional human-label accuracy and independent-run agreement. No inference.'

    def add_arguments(self, parser):
        parser.add_argument('assessment')
        parser.add_argument('--gold')
        parser.add_argument('--repeat')
        parser.add_argument('--rubric', help='Pinned rubric JSON when evaluating a methodology other than the installed release.')

    def handle(self, *args, **options):
        try:
            read = lambda path: json.loads(Path(path).read_text()) if path else None
            exported = read(options['assessment'])
            result = compare_export(exported, rubric=read(options['rubric']) or exported.get('rubric') or release(),
                                    gold=read(options['gold']), repeat=read(options['repeat']))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise CommandError('Invalid export, label or rubric input; use matching complete pinned snapshots.') from exc
        self.stdout.write(json.dumps(result, indent=2))
        if not result['numerical_replay_matches']:
            raise CommandError('Deterministic numerical replay does not match the exported result.')
