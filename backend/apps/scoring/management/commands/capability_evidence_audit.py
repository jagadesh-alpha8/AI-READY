"""Private JSON input: rubric, reviewed_evidence, requests (prepared payloads)."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.evidence_audit import audit_request


class Command(BaseCommand):
    help = 'Audit prepared packets and optional recorded responses offline, without inference or database writes.'

    def add_arguments(self, parser):
        parser.add_argument('input')
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        target = Path(options['output']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if target == repository or repository in target.parents:
            raise CommandError('Choose a private output outside the repository.')
        if target.exists():
            raise CommandError('Refusing to overwrite an existing audit.')
        try:
            data = json.loads(Path(options['input']).read_text())
            result = {'version': 'evidence-consumption-audit-1', 'no_provider_calls': True,
                'requests': [audit_request(r, data['reviewed_evidence'], data['rubric']) for r in data['requests']]}
            with target.open('x') as output:
                json.dump(result, output, indent=2)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise CommandError('Invalid offline audit input or output; no provider request was made.') from exc
        self.stdout.write(f"Audited {len(result['requests'])} private packets. No provider requests or database writes.")
