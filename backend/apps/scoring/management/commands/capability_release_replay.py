"""The replay before a release (past cases, use 1) and the drift ledger (capability/past_cases.py).

The anchor set is judged again on its own passages, and the ledger keeps the signed move against the last replay:
explained where a named change touched the part, unexplained otherwise, with the unexplained running total against
twice the replay's repeat noise. Anchors: cases a person marked (--cases) and the marked yardstick (--export with
--marks; VISTAS, whose own runs add no cases).

    python manage.py capability_release_replay --export run.json.gz --marks map_marks.txt --cases --label "Standard 1.0"
    python manage.py capability_release_replay ... --live --repeat --explained changes.json
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import compact_replay, past_cases


class Command(BaseCommand):
    help = 'Replay the anchor set before a release and add the result to the drift ledger.'

    def add_arguments(self, parser):
        parser.add_argument('--export', help='An export whose marked pages are anchors (with --marks).')
        parser.add_argument('--marks', help='The yardstick marks.')
        parser.add_argument('--cases', action='store_true', help='Also replay the cases a person marked.')
        parser.add_argument('--label', required=False, default='')
        parser.add_argument('--explained', help='JSON file: [{"change": "...", "parts": ["AIQIF-C1.1.F2:p2"]}].')
        parser.add_argument('--repeat', action='store_true', help='Replay twice to measure the repeat noise.')
        parser.add_argument('--live', action='store_true', help='Make the model calls.')
        parser.add_argument('--note', default='')

    def handle(self, *args, **o):
        anchors, export = [], None
        if o['export']:
            if not o['marks']:
                raise CommandError('--export needs --marks.')
            export = compact_replay.load_export(o['export'])
            anchors += past_cases.anchors_from_yardstick(export, compact_replay.load_marks(o['marks']))
        if o['cases']:
            anchors += past_cases.anchors_from_cases()
        if not anchors:
            raise CommandError('No anchors: give --export and --marks, or --cases with marked cases.')
        if export is None:
            raise CommandError('An export is needed for the rubric and settings the replay judges under.')
        cases = [{'requirement': a['requirement'], 'sent': [], 'pointed': [], 'answers': [],
                  'stage1_only': False, 'passages': a['passages']} for a in anchors]
        chars = sum(len(p.get('text') or '') for a in anchors for p in a['passages'])
        calls = ((export.get('assessment') or {}).get('inference') or {}).get('calls') or []
        prices = next((c.get('configured_prices') for c in calls if c.get('configured_prices')), {'input': 1, 'output': 5})
        runs = 2 if o['repeat'] else 1
        usd = runs * compact_replay.PASSES * len(cases) * (
            (chars / max(1, len(cases)) / 3.5 + 6000) * float(prices['input'])
            + compact_replay.OUTPUT_TOKENS * float(prices['output'])) / 1e6
        self.stdout.write(f'{len(anchors)} anchors; estimated ${usd:.2f}.')
        if not o['live']:
            self.stdout.write('Dry run: no model calls (use --live once the spend is approved).')
            return
        from apps.scoring.capability.model_choice import scoring_service
        from apps.scoring.capability.standard import frozen
        service = scoring_service()

        def judge(requirement, passages):
            packet = [{**p, 'id': p['source_id'], 'text_offset': 0, 'evidence_role': 'case_passage'} for p in passages]
            case = {'requirement': requirement, 'sent': [], 'pointed': packet, 'answers': []}
            return compact_replay.judge(case, export, 'compact', service, typed=False)
        results = past_cases.replay_anchors(anchors, judge)
        repeat = past_cases.replay_anchors(anchors, judge) if o['repeat'] else None
        explained = json.load(open(o['explained'], encoding='utf-8')) if o['explained'] else []
        row = past_cases.ledger_entry(results, label=o['label'] or frozen()['name'], explained_by=explained,
                                      repeat=repeat, standard=frozen(), note=o['note'])
        self.stdout.write(f'Still right: {row.still_right:.1%}. Move: {row.signed_move:+.3f} (explained '
                          f'{row.explained_move:+.3f}, unexplained {row.unexplained_move:+.3f}); running total '
                          f'{row.running_total:+.3f} against a limit of {row.limit}. '
                          f'{"Passed." if row.passed else "Not passed: someone should look before the release."}')
