"""Score capability exports against a private answer key; offline, no model calls or database writes.

With several exports (e.g. repeated runs on one build and one corpus), also lists the conditions whose
decision differs between runs: an unstable decision cannot be relied on even when one run is right.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.answer_key import SCORED, check, consensus, instability


class Command(BaseCommand):
    help = 'Score assessment exports against an answer key; name the first failed stage and list unstable decisions.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('exports', nargs='+', help='Capability assessment JSON export(s).')
        parser.add_argument('--key', required=True, help='Private answer key JSON (outside the repository).')
        parser.add_argument('--output', help='New JSON result path outside the repository; refuses overwrite.')

    def handle(self, *args, **options):
        try:
            key = json.loads(Path(options['key']).read_text())
            exports = [json.loads(Path(p).read_text()) for p in options['exports']]
            results = [check(export, key) for export in exports]
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Could not check the export: {exc}') from exc
        flips = instability(results) if len(results) > 1 else []
        if options['output']:
            target = Path(options['output']).resolve()
            repository = Path(settings.BASE_DIR).resolve().parent
            if target.exists() or repository in target.parents:
                raise CommandError('Choose a new output path outside the repository.')
            target.write_text(json.dumps({'results': results, 'unstable_conditions': flips,
                                          'agreement': consensus(results) if len(results) > 1 else None}, indent=1))
        out = self.stdout.write
        for result in results:
            out(f"\nrun {result['run_id']} | key {result['answer_key']} | document {result['document']}")
            out(f"accuracy {result['correct']}/{result['scored_conditions']} = {result['accuracy']} | "
                f"outcomes {result['outcomes']} | first failed stage {result['first_failed_stage']} | "
                f"not scored {result['not_scored']}")
            for row in result['conditions']:
                if row['outcome'] != 'correct' and row['status'] in SCORED:
                    out(f"  {row['condition_id']:16} {row['outcome']:19} expected {row['expected']:8} got {row['got']:8} "
                        f"stage {row['stage']}: {row['detail']}")
            for row in result['conditions']:
                if row['status'] not in SCORED:
                    out(f"  [{row['status']}] {row['condition_id']:16} expected {row['expected']:8} got {row['got']}")
        if flips:
            out(f'\nUnstable across the {len(results)} runs ({len(flips)} conditions):')
            for flip in flips:
                out(f"  {flip['condition_id']:16} expected {flip['expected']:8} states {' / '.join(flip['states'])}")
        if len(results) > 1:
            agreed = consensus(results)
            out(f"\nAgreement of {agreed['runs']} runs (disagreements go to review): correct {agreed['correct']}, "
                f"unanimous but wrong {agreed['wrong_unanimous']}, to review {agreed['to_review']}, "
                f"accuracy of decided {agreed['accuracy_of_decided']}")
            for item in agreed['wrong']:
                out(f"  unanimous but wrong: {item['condition_id']:16} expected {item['expected']:8} got {item['got']}")
