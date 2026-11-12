"""Load the institution's responses to follow-up questions (skeleton: from a file; the web app screen is not built).

    python manage.py depth_load_responses responses.json            # check only
    python manage.py depth_load_responses responses.json --commit
    python manage.py depth_load_responses answers.json --by-condition --run <run id> --commit

The file is a JSON list of {"question_id", "kind": "answer"|"upload"|"dont_know", "answer", "document_ids",
"supported"}. Uploads count as supported; an answer counts as supported only when "supported" is true (for example a
consultant has seen the document). Every row is checked before anything is saved.

With --by-condition the file is instead {condition_id: {"kind", "answer", "document_ids", "supported"}}, and every
depth question of that run about that condition gets the same response (for test runs such as
docs/capability/depth_fixtures/; keys starting with "_" are ignored).
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.depth_service import DepthError, load_responses
from apps.scoring.models import DepthQuestion


class Command(BaseCommand):
    help = "Load an institution's responses to follow-up questions."

    def add_arguments(self, parser):
        parser.add_argument('responses')
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--via', default='file', help='file, college or consultant')
        parser.add_argument('--by-condition', action='store_true')
        parser.add_argument('--run', help='The run id (with --by-condition).')

    def handle(self, *args, **options):
        with open(options['responses'], encoding='utf-8') as f:
            data = json.load(f)
        if options['by_condition']:
            if not options['run']:
                raise CommandError('--by-condition needs --run.')
            answers = {k: v for k, v in data.items() if not k.startswith('_')}
            rows = [{'question_id': str(q.pk), **answers[q.condition_ids[0]]}
                    for q in DepthQuestion.objects.filter(run_ref=options['run'], kind=DepthQuestion.Kind.DEPTH)
                    if q.condition_ids[0] in answers]
            if not rows:
                raise CommandError('No depth questions of that run concern the listed conditions.')
        else:
            rows = data
        try:
            count = load_responses(rows, commit=options['commit'], via=options['via'])
        except DepthError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f'{count} responses ' + ('saved.' if options['commit'] else 'checked; nothing saved (use --commit).'))
