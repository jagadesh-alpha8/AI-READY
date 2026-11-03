"""Re-evaluate labelled requirements with their labelled pages supplied: separates retrieval from judgement.

Dry run by default: builds every request and reports its size without contacting a provider.
`--send` evaluates through the configured provider using production evaluate() unchanged except
for page selection. Nothing is written to the database; results go to a new folder outside the
repository. The saved assessment is never changed.
"""
import json
import math
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import pipeline_diagnostics as stages
from apps.scoring.capability.context_diagnostics import evaluation_request, gate

# Bytes per prompt token measured on the reference run (gemma4:31b); other tokenizers differ.
BYTES_PER_TOKEN = 3.19


class Command(BaseCommand):
    help = 'Oracle-context check: would the evaluator credit labelled evidence if retrieval had supplied it?'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to a capability assessment JSON export.')
        parser.add_argument('--gold', required=True, help='Private labelled-evidence JSON (see capability_context_report).')
        parser.add_argument('--output-dir', required=True, help='New directory outside the repository.')
        parser.add_argument('--send', action='store_true', help='Actually send the requests to the configured provider.')

    def handle(self, *args, **options):
        out = Path(options['output_dir']).resolve()
        repository = Path(settings.BASE_DIR).resolve().parent
        if out == repository or repository in out.parents:
            raise CommandError('Institutional diagnostics must be written outside the repository.')
        try:
            export = json.loads(Path(options['export']).read_text(encoding='utf-8'))
            gold = json.loads(Path(options['gold']).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError('Could not read the export or gold file.') from exc
        from apps.scoring.models import CapabilityRun
        from .capability_context_report import Command as Report
        run = CapabilityRun.objects.filter(pk=export['run_id']).first()
        if run is None or run.inputs_hash != export['inputs_hash']:
            raise CommandError('The database does not hold this run with matching frozen inputs.')
        rendered, _tags, _unchanged = Report.current_state(run)
        contexts, items = stages.oracle_contexts(export, rendered, gold)
        indicators = [i for i in export['rubric']['indicators'] if i['code'] in contexts]
        plan = []
        for indicator in indicators:
            request = evaluation_request(indicator, contexts[indicator['code']], ledger=export['reviewed_evidence'],
                                         scope=export['scope'], population=export['population'],
                                         reference_period=export['reference_period'])
            message = len(request['system'].encode()) + len(request['payload'].encode())
            plan.append({'indicator': indicator['code'], 'windows': len(contexts[indicator['code']]),
                         'labelled_items': len(items[indicator['code']]),
                         'labelled_windows_found': sum(i['oracle_window_found'] for i in items[indicator['code']]),
                         'pre_request_limit': gate(request)[0], 'message_bytes': message,
                         'estimated_prompt_tokens': math.ceil(message / BYTES_PER_TOKEN)})
        host = settings.AI_BASE_URL.split('/')[2] if settings.AI_BASE_URL else 'default provider'
        summary = {'provider_host': host, 'model': settings.AI_MODEL, 'requests': len(plan),
                   'estimated_prompt_tokens': sum(p['estimated_prompt_tokens'] for p in plan),
                   'output_token_allowance': settings.CAPABILITY_OUTPUT_TOKENS * len(plan),
                   'note': f'Estimate at {BYTES_PER_TOKEN} bytes per token; at most one correction request per batch may be added.'}
        try:
            out.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise CommandError('Choose a new output directory; existing reports are never overwritten.') from exc
        result = {'summary': summary, 'plan': plan, 'sent': options['send']}
        if options['send']:
            result.update(self.evaluate(export, rendered, contexts, indicators, items))
        (out / 'oracle.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps(summary, indent=2))
        self.stdout.write('Sent and evaluated.' if options['send'] else 'Dry run only: nothing was sent. Add --send to evaluate.')

    @staticmethod
    def evaluate(export, rendered, contexts, indicators, items):
        from apps.extraction.services.ai_service import get_ai_service
        from apps.scoring.capability import evaluation
        records = {r['condition_id']: r for r in export['assessment']['records']}
        # Production evaluate(), unchanged except that each batch receives its oracle context.
        with patch.object(evaluation, 'select_context', lambda indicator, sources, max_chars=18000, **kwargs: contexts[indicator['code']]):
            outcome = evaluation.evaluate(rendered, service=get_ai_service(), population=export['population'],
                                          reference_period=export['reference_period'], rubric={'indicators': indicators},
                                          scope=export['scope'], reviewed_evidence=export['reviewed_evidence'])
        fresh = {r['condition_id']: r for r in outcome['records']}
        labelled = []
        for code, rows in items.items():
            for item in rows:
                ids = [item['condition_id']] if item.get('condition_id') else [cid for cid in fresh if cid.startswith(code + '.')]
                labelled.append({'indicator': code, 'condition_id': item.get('condition_id'), 'page': item['page'],
                                 'window_found': item['oracle_window_found'],
                                 'saved_credited': any(records[c]['state'] == 'met' for c in ids),
                                 'oracle_credited': any(fresh[c]['state'] == 'met' for c in ids)})
        return {'state_changes': dict(Counter(f"{records[cid]['state']}->{row['state']}" for cid, row in fresh.items())),
                'requests_made': outcome['indicator_calls'] + outcome['correction_calls'],
                'labelled': labelled,
                'labelled_credited': {'saved': sum(r['saved_credited'] for r in labelled),
                                      'oracle': sum(r['oracle_credited'] for r in labelled), 'of': len(labelled)},
                'records': outcome['records'], 'errors': [t['error'] for t in outcome['traces'] if t['error']]}
