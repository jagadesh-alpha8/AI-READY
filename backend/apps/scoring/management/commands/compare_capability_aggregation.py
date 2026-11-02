"""Read-only arithmetic sensitivity on an exported original assessment."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.experimental_ladder import compare_source_export


class Command(BaseCommand):
    help = 'Compare original cumulative bounds with independent components offline; no candidate rescore.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('export')

    def handle(self, *args, **options):
        try:
            result = compare_source_export(json.loads(Path(options['export']).read_text()))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise CommandError('A complete supported assessment export is required.') from exc
        self.stdout.write(json.dumps(result, indent=2))
