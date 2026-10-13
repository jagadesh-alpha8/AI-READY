"""Import the benchmark catalogue (pillars, evidence types, benchmarks, L3/L2/L1)
from the manager's Source Pack workbook.

    python manage.py import_benchmark_catalogue "path/to/InGage_Benchmark_Source_Pack_v0_2_Expanded_Foundation.xlsx"
    ... --commit                # save (default: dry run)
    ... --version-label v0.2    # override the version read from the Read Me title
"""
from django.core.management.base import BaseCommand, CommandError

from ...services.catalogue_import import apply_catalogue, read_catalogue


class Command(BaseCommand):
    help = 'Import the benchmark catalogue from the Source Pack (.xlsx). Dry run unless --commit.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--version-label', default=None)
        parser.add_argument('--actor', default='import_benchmark_catalogue')

    def handle(self, *args, path, commit, version_label, actor, **opts):
        try:
            cat = read_catalogue(path, version_label)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Cannot read {path}: {exc}')
        self.stdout.write(f'Source Pack {cat.version_label}: {len(cat.pillars)} pillars, '
                          f'{len(cat.evidence_types)} evidence types, {len(cat.benchmarks)} benchmarks')
        for msg in cat.errors:
            self.stdout.write(self.style.ERROR(f'  SKIPPED {msg}'))
        for msg in cat.warnings:
            self.stdout.write(self.style.WARNING(f'  note: {msg}'))
        summary = apply_catalogue(cat, actor=actor, commit=commit, reason=f'Catalogue import from {path}')
        self.stdout.write(self.style.SUCCESS('COMMITTED' if commit else 'DRY RUN (nothing saved)'))
        self.stdout.write(f'  created: {dict(summary.created)}')
        self.stdout.write(f'  updated: {dict(summary.updated)}')
        for line in summary.locked:
            self.stdout.write(self.style.WARNING(f'  locked: {line}'))
        if not commit:
            self.stdout.write('Run again with --commit to save.')
