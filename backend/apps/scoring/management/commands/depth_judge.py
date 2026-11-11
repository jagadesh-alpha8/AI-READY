"""Judge the depth of each credited condition that has answered follow-up questions (skeleton; see depth.py).

    python manage.py depth_judge export.json             # dry run
    python manage.py depth_judge export.json --commit    # save judgments and propose them as past cases

Saved judgments are proposed as past cases; a person approves them in the admin before they guide later judgments.
One model call per judged condition (--max-calls bounds it); not metered against a run budget yet.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import depth
from apps.scoring.capability.depth_service import DepthError, judge_run


class Command(BaseCommand):
    help = 'Judge the depth of credited evidence from the institution\'s answers.'

    def add_arguments(self, parser):
        parser.add_argument('export')
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--max-calls', type=int, default=40)
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        with open(options['export'], encoding='utf-8') as f:
            export = json.load(f)
        try:
            result = judge_run(export, depth.default_model(), commit=options['commit'],
                               max_calls=options['max_calls'])
        except DepthError as exc:
            raise CommandError(str(exc))
        if options['json']:
            self.stdout.write(json.dumps(result, indent=1, ensure_ascii=False, default=str))
            return
        self.stdout.write(f"Policy: {result['policy']}")
        for row in result['judged']:
            flags = ' '.join(f for f, on in (('CONTRADICTION', row['contradicts_evidence']),
                                             ('UNSUPPORTED', row['relies_on_unsupported'])) if on)
            self.stdout.write(f"{row['condition_id']}: judged {row['level']}, final {row['final_level']} "
                              f"(credit {row['provisional_credit']} -> {row['final_credit']:.4f}) {flags}\n  {row['reason']}")
        if result['unanswered']:
            self.stdout.write(f"Not judged (no response or call limit): {', '.join(result['unanswered'])}")
        if result['awaiting_reassessment']:
            self.stdout.write(f"Documents uploaded for missing evidence, awaiting extraction and reassessment: "
                              f"{result['awaiting_reassessment']}")
        self.stdout.write('Saved.' if result['saved'] else 'Dry run: nothing saved (use --commit).')
