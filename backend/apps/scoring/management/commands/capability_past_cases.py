"""Past cases (capability/past_cases.py): save, release, take out, sample and audit.

    python manage.py capability_past_cases save RUN            # save a published run's cases now (normally automatic)
    python manage.py capability_past_cases release --note "..."  # cut the next numbered release
    python manage.py capability_past_cases withdraw --run RUN --reason "..."
    python manage.py capability_past_cases sample INSTITUTION   # mark about 20 cases for a person to mark
    python manage.py capability_past_cases audit                # price the AI audit of the unaudited cases (no calls)
    python manage.py capability_past_cases audit --export run.json.gz   # price it for one college's run
    python manage.py capability_past_cases audit --run --max-cost 5     # make the calls (Vijay approves the price)
"""
import uuid
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability import past_cases


class Command(BaseCommand):
    help = 'Past cases: save, release, withdraw, sample and audit.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=('save', 'release', 'withdraw', 'sample', 'audit'))
        parser.add_argument('target', nargs='?', help='A run id (save) or an institution id (sample).')
        parser.add_argument('--note', default='')
        parser.add_argument('--run-ref', dest='run_ref')
        parser.add_argument('--reason', default='')
        parser.add_argument('--export', help='audit: price the cases one exported run would add.')
        parser.add_argument('--model', help='audit: the audit model (default PAST_CASE_AUDIT_MODEL).')
        parser.add_argument('--run', action='store_true', help='audit: make the model calls.')
        parser.add_argument('--max-cost', type=float, help='audit: refuse to start above this estimated cost (USD).')
        parser.add_argument('--limit', type=int)

    def handle(self, *args, **o):
        from apps.scoring.models import PartCase
        action = o['action']
        if action == 'save':
            from apps.scoring.models import CapabilityRun
            run = CapabilityRun.objects.select_related('sprint__institution').get(pk=o['target'])
            self.stdout.write(f'{past_cases.save_for_run(run)} cases saved.')
        elif action == 'release':
            row = past_cases.cut_release(o['note'])
            self.stdout.write(f'Release {row.number}: {row.case_count} cases.')
        elif action == 'withdraw':
            try:
                count = past_cases.withdraw(run_ref=o['run_ref'], reason=o['reason'])
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write(f'{count} cases taken out; this takes effect in the next release.')
        elif action == 'sample':
            from apps.institutions.models import Institution
            picks = past_cases.draw_sample(Institution.objects.get(pk=o['target']))
            self.stdout.write(f'{len(picks)} cases added to the sample for a person to mark.')
        else:
            self.audit(o, PartCase)

    def audit(self, o, PartCase):
        if o['export']:
            from apps.scoring.capability.compact_replay import load_export
            export = load_export(o['export'])
            rows = past_cases.cases_for(export['assessment']['records'], export['assessment']['traces'],
                                        run_ref=export['run_id'], versions={}, source='stage1')
            cases = [SimpleNamespace(pk=uuid.uuid4(), **{k: r[k] for k in (
                'run_ref', 'condition_id', 'part_id', 'passages', 'passages_kind', 'final_finding')}) for r in rows]
            if o['run']:
                raise CommandError('--export only prices; audit saved cases with --run.')
        else:
            cases = list(PartCase.objects.filter(state=PartCase.State.ACTIVE, audit_mark='')
                         .order_by('run_ref', 'condition_id', 'part_id'))
        if o['limit']:
            cases = cases[:o['limit']]
        price = past_cases.price_audit(cases, o['model'])
        self.stdout.write(f"{price['cases']} cases in {price['requests']} requests to {price['model']}: about "
                          f"{price['input_tokens']:,} input and {price['output_tokens']:,} output tokens, "
                          f"${price['usd']:.2f}.")
        if not o['run']:
            self.stdout.write('Priced only: no model calls (use --run once the cost is approved).')
            return
        if o['max_cost'] is None or price['usd'] > o['max_cost']:
            raise CommandError('Give --max-cost at or above the estimate to start.')
        call = past_cases.audit_model(o['model'])
        marks = past_cases.audit_cases(cases, call, model_name=call.model_name)
        self.stdout.write(f'Marks: {dict(marks)}')
