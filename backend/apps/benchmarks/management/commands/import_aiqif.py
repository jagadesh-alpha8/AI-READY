"""Import InGage AI-QIF v1.0 (criteria, key indicators, L3/L2/L1, weights, NAAC crosswalk)
into the benchmark library as drafts.

    python manage.py import_aiqif "source_library_work/InGage_AI_READY_AI_QIF_Master_v1_0_AI_Criteria.xlsx"
    ... --commit             # save (default: dry run)
    ... --withdraw-others    # also withdraw every other draft benchmark (e.g. the old Source Pack set)
    ... --commit --baseline  # then freeze the catalogue as the manager workbook baseline (the release
                             # assessments and CRI coverage use; services/baseline.py)
    ... --linked-by <email>  # optional: the InGage person running the import, recorded on source mappings

The workbook is the authoritative standard catalogue and Benchmark Studio is read-only, so this is the
controlled way the catalogue changes: run it without --commit first and check the listed changes.
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
        parser.add_argument('--linked-by', default='')
        parser.add_argument('--baseline', action='store_true',
                            help='After --commit, publish the catalogue as the manager workbook baseline.')

    def handle(self, *args, path, commit, withdraw_others, actor, linked_by='', baseline=False, **opts):
        reviewer = None
        if linked_by:
            from apps.accounts.models import User
            reviewer = User.objects.filter(email__iexact=linked_by, is_active=True,
                                           role__in=User.CROSS_INSTITUTION_ROLES).first()
            if reviewer is None:
                raise CommandError(f'{linked_by} is not an active InGage reviewer (super admin or consultant).')
        try:
            data = read_aiqif(path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Cannot read {path}: {exc}')
        self.stdout.write(f'Workbook: {data.workbook} (SHA-256 {data.workbook_sha256})')
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
                              reason=f'AI-QIF import from {path}', linked_by=reviewer)
        self.stdout.write(self.style.SUCCESS('COMMITTED' if commit else 'DRY RUN (nothing saved)'))
        self.stdout.write(f'  created: {dict(summary.created)}')
        self.stdout.write(f'  updated: {dict(summary.updated)}')
        refs = summary.source_refs
        self.stdout.write(f'  origin recorded: {data.workbook}, sheet "AI Benchmark Master" row per indicator; '
                          f'workbook source references: {refs["linked"]} linked, {refs["not linked"]} not linked')
        if summary.withdrawn:
            self.stdout.write(f'  withdrawn: {len(summary.withdrawn)} other draft benchmarks')
        for line in summary.locked:
            self.stdout.write(self.style.WARNING(f'  locked: {line}'))
        if summary.changes:
            self.stdout.write(f'  changes ({len(summary.changes)}):')
            for kind, ident, what in summary.changes:
                self.stdout.write(f'    {kind} {ident}: {what}')
        else:
            self.stdout.write('  no changes: the catalogue already matches this workbook')
        self._baseline(data, actor, commit, baseline)
        if not commit:
            self.stdout.write('Run again with --commit to save.')

    def _baseline(self, data, actor, commit, baseline):
        from ...services.baseline import BaselineError, publish_workbook_baseline
        if not baseline:
            return
        try:
            plan, release = publish_workbook_baseline(data.workbook, data.workbook_sha256, actor, commit=commit)
        except BaselineError as exc:
            raise CommandError(str(exc))
        if plan['unchanged']:
            self.stdout.write(f'  baseline: {plan["current"]} already is this workbook; nothing to publish')
        elif release is None:
            self.stdout.write(f'  baseline (dry run): would publish "{plan["label"]}" with {plan["indicators"]} '
                              f'indicators and retire {plan["current"] or "nothing"}')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'  baseline: published "{release.release_label}" ({plan["indicators"]} indicators); '
                f'retired {plan["current"] or "nothing"}'))
