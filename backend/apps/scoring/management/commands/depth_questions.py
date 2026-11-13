"""Follow-up questions about the depth of evidence for one assessment run (skeleton; see depth.py).

    python manage.py depth_questions export.json                    # dry run: print the questions, save nothing
    python manage.py depth_questions export.json --commit           # save them for the institution
    python manage.py depth_questions export.json --commit --replace # plan again (refused once responses exist)
    python manage.py depth_questions export.json --out questions.json   # also write them to a file to send

One model call per credited condition tried, until DEPTH_MAX_QUESTIONS is used (--max-calls bounds it). These calls
are unmetered (the API's questions job is metered: second_layer_jobs.py).
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import depth
from apps.scoring.capability.depth_service import DepthError, create_questions


class Command(BaseCommand):
    help = 'Plan follow-up questions about the depth of evidence for an assessment export.'

    def add_arguments(self, parser):
        parser.add_argument('export')
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--replace', action='store_true')
        parser.add_argument('--max-calls', type=int, default=60)
        parser.add_argument('--out', help='Write the questions to this JSON file.')

    def handle(self, *args, **options):
        with open(options['export'], encoding='utf-8') as f:
            export = json.load(f)
        try:
            result = create_questions(export, depth.default_model(), commit=options['commit'],
                                      replace=options['replace'], max_calls=options['max_calls'])
        except DepthError as exc:
            raise CommandError(str(exc))
        for note in result['notes']:
            self.stdout.write(note)
        for q in result['questions']:
            self.stdout.write(f"\n#{q['rank']} [{q['kind']}] {', '.join(q['condition_ids'])}\n{q['text']}")
        if options['out']:
            with open(options['out'], 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=1, ensure_ascii=False)
        self.stdout.write('\nSaved.' if result['saved'] else '\nDry run: nothing saved (use --commit).')
