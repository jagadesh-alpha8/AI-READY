"""Diagnose one exported assessment without inference, database writes or rescoring."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.scoring.capability.assessment_audit import diagnose
from apps.scoring.capability.engine import assess


class Command(BaseCommand):
    help = 'Audit a capability JSON export offline; no model calls or assessment writes.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to a capability assessment JSON export.')
        parser.add_argument('--output', help='Optional new diagnostic JSON output path; refuses overwrite.')

    def handle(self, *args, **options):
        try:
            report = json.loads(Path(options['export']).read_text())
            assessment = report['assessment']
            rubric = report['rubric']
            result = diagnose(assessment, rubric=rubric, manifest=report.get('source_manifest'))
            # Replay checks arithmetic only, not whether evidence interpretations were correct.
            decisions = {r['condition_id']: r['state'] for r in assessment['records']}
            result['run_id'] = report.get('run_id')
            result['arithmetic_replay_matches'] = result['record_contract']['complete'] and assess(decisions, rubric) == assessment['result']
            result['profile'] = report.get('profile')
            result['population'] = report.get('population')
            result['reference_period'] = report.get('reference_period')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError('Could not read a complete, supported capability assessment export.') from exc
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if options['output']:
            try:
                with Path(options['output']).open('x') as target:
                    target.write(text + '\n')
            except OSError as exc:
                raise CommandError('Could not create diagnostic output; choose a new writable path.') from exc
            self.stdout.write('Created offline diagnosis; no inference or database writes performed.')
        else:
            self.stdout.write(text)
