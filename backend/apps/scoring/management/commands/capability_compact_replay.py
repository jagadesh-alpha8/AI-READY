"""Replay harness for the compact re-judge (capability/compact_replay.py).

    # Test 5, offline (no model calls), on the server:
    python manage.py capability_compact_replay --run-id RUN --marks marks.tsv --test 5
    # The same away from the database: pages rebuilt from the export's packets (indicative only)
    python manage.py capability_compact_replay --export run.json.gz --marks map_marks.txt --test 5
    # A live test: first the cases and the estimated cost; --live makes the model calls (Vijay approves the spend)
    python manage.py capability_compact_replay --run-id RUN --marks marks.tsv --test 2
    python manage.py capability_compact_replay --run-id RUN --marks marks.tsv --test 2 --live --out t2.json
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import compact_replay as replay


class Command(BaseCommand):
    help = 'Replay harness for the compact re-judge, built from the marked yardstick.'

    def add_arguments(self, parser):
        parser.add_argument('--export', help='An assessment export (.json or .json.gz).')
        parser.add_argument('--run-id', help='Read the run and its frozen pages from this database.')
        parser.add_argument('--marks', required=True, help='The yardstick marks (map-marks text or a TSV).')
        parser.add_argument('--test', type=int, required=True, choices=(1, 2, 3, 4, 5, 6))
        parser.add_argument('--live', action='store_true', help='Make the model calls (tests 1 to 4 and 6).')
        parser.add_argument('--whole-sample', type=int, default=10,
                            help='How many cases also run on the whole packet (to hold cost down).')
        parser.add_argument('--limit', type=int, help='At most this many cases.')
        parser.add_argument('--out', help='Write the result to this JSON file.')

    def handle(self, *args, **options):
        if bool(options['export']) == bool(options['run_id']):
            raise CommandError('Give an export file or --run-id, not both.')
        if options['run_id']:
            from apps.scoring.capability.layer2_service import export_for_run
            export = export_for_run(options['run_id'])
            sources, frozen_map = replay.sources_from_run(options['run_id'])
            note = 'pages from the database'
        else:
            export = replay.load_export(options['export'])
            sources, frozen_map = replay.sources_from_export(export), {}
            note = ('pages rebuilt from the packets: pages no packet reached are missing and some are partial, so '
                    'this is indicative only')
        tags = frozen_map.get('pages') or {}
        marks = replay.load_marks(options['marks'])
        if options['test'] == 5:
            result = {'test': 5, 'note': note, **replay.test5(export, sources, marks, tags)}
            for cap, counts in result['counts'].items():
                self.stdout.write(f'{cap} characters: {json.dumps(counts, sort_keys=True)}')
            return self._write(options, result)
        test = 2 if options['test'] == 6 else options['test']
        found = replay.cases(test, export, sources, marks, tags, limit=options['limit'])
        if options['test'] == 6:
            found += replay.cases(3, export, sources, marks, tags, limit=options['limit'])
        sample = found[:options['whole_sample']]
        cost = {'compact': replay.estimate(found, export, tags, sources, modes=('compact',))['compact'],
                'whole': replay.estimate(sample, export, tags, sources, modes=('whole',))['whole']}
        typed = options['test'] in (2, 3, 6)
        repeats = 2 if options['test'] == 6 else 1
        factor = repeats * (2 if typed else 1)
        total = round((cost['compact']['usd'] + cost['whole']['usd']) * factor, 2)
        self.stdout.write(f"Test {options['test']}: {len(found)} cases ({len(sample)} also on the whole packet); "
                          f"estimated ${total} ({note}).")
        if not options['live']:
            self.stdout.write('Dry run: no model calls (use --live once the spend is approved).')
            return self._write(options, {'test': options['test'], 'cases': len(found), 'estimate': cost,
                                         'estimated_usd': total, 'note': note})
        from apps.scoring.capability.model_choice import scoring_service
        service = scoring_service()
        results = []
        for repeat in range(repeats):
            for n, case in enumerate(found):
                modes = ('compact', 'whole') if n < len(sample) else ('compact',)
                for mode in modes:
                    for shown in ((True, False) if typed and mode == 'compact' else (mode == 'compact',)):
                        record = replay.judge(case, export, mode, service, tags, sources, typed=shown)
                        results.append({**{k: v for k, v in case.items() if k not in ('sent', 'pointed')},
                                        'sent': [s['id'] for s in case['sent']],
                                        'pointed': [w['id'] for w in case['pointed']], 'mode': mode,
                                        'typed': shown, 'repeat': repeat, 'record': record})
        summary = replay.summarise(results)
        for key, counts in sorted(summary.items()):
            self.stdout.write(f'{key}: {json.dumps(counts, sort_keys=True)}')
        return self._write(options, {'test': options['test'], 'summary': summary, 'results': results, 'note': note})

    def _write(self, options, result):
        if options['out']:
            with open(options['out'], 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=1, default=str)
            self.stdout.write(f"Wrote {options['out']}.")
