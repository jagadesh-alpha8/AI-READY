"""Import InGage AI-QIF v1.0 (criteria, key indicators, L3/L2/L1, weights, NAAC crosswalk)
into the benchmark library as drafts.

    python manage.py import_aiqif "source_library_work/InGage_AI_READY_AI_QIF_Master_v1_0_AI_Criteria.xlsx"
    ... --commit             # save (default: dry run)
    ... --withdraw-others    # also withdraw every other draft benchmark (e.g. the old Source Pack set)
"""
from django.core.management.base import BaseCommand, CommandError

from ...services.aiqif_import import apply_aiqif, read_aiqif


class Command(BaseCommand):
    help = 'Import AI-QIF v1.0 from its master workbook (.xlsx) as draft benchmarks. Dry run unless --commit.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--withdraw-others', action='store_true')
        parser.add_argument('--actor', default='import_aiqif')

    def handle(self, *args, path, commit, withdraw_others, actor, **opts):
        try:
            data = read_aiqif(path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Cannot read {path}: {exc}')
        self.stdout.write(f'AI-QIF: {len(data.criteria)} criteria (weight {sum(c["weight"] or 0 for c in data.criteria)}), '
                          f'{len(data.benchmarks)} key indicators, '
                          f'{sum(len(b["crosswalk"]) for b in data.benchmarks)} NAAC crosswalk links')
        for msg in data.errors:
            self.stdout.write(self.style.ERROR(f'  SKIPPED {msg}'))
        for msg in data.warnings:
            self.stdout.write(self.style.WARNING(f'  note: {msg}'))
        if data.errors and commit:
            raise CommandError('Fix the rows above first; nothing was saved.')
        summary = apply_aiqif(data, actor=actor, commit=commit, withdraw_others=withdraw_others,
                              reason=f'AI-QIF import from {path}')
        self.stdout.write(self.style.SUCCESS('COMMITTED' if commit else 'DRY RUN (nothing saved)'))
        self.stdout.write(f'  created: {dict(summary.created)}')
        self.stdout.write(f'  updated: {dict(summary.updated)}')
        if summary.withdrawn:
            self.stdout.write(f'  withdrawn: {len(summary.withdrawn)} other draft benchmarks')
        for line in summary.locked:
            self.stdout.write(self.style.WARNING(f'  locked: {line}'))
        if not commit:
            self.stdout.write('Run again with --commit to save.')
