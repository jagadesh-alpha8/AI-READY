"""An explicit, isolated diagnostic execution, with no automatic assessment dispatch."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.db import connection,transaction
from apps.scoring.capability.bounded_probe import prepare,bounded_policy,execute
from apps.scoring.capability.storage import digest,evidence_snapshot
from apps.scoring.capability.reviewed_evidence import snapshot


class Command(BaseCommand):
    help='Execute a bounded private evidence/advice probe on an explicitly named disposable database.'

    def add_arguments(self,parser):
        parser.add_argument('input')
        parser.add_argument('--output',required=True)
        parser.add_argument('--execute',action='store_true')
        parser.add_argument('--disposable-database',help='Must exactly match the configured database NAME.')
        parser.add_argument('--sprint-id')
        parser.add_argument('--advice-cases',type=int,default=3)

    def handle(self,*args,**options):
        output=Path(options['output']).resolve();repo=Path(settings.BASE_DIR).resolve().parent
        if output.exists() or output==repo or repo in output.parents:
            raise CommandError('Choose an unused private output outside the repository.')
        if not 0<=options['advice_cases']<=3:
            raise CommandError('At most three advice cases are allowed.')
        plan=json.loads(Path(options['input']).read_text())
        if not options['execute']:
            self.stdout.write('Prepared requests only. Live execution requires --execute, --sprint-id and an explicitly named disposable database. No provider or database was accessed.')
            return
        if (not options['disposable_database'] or not options['sprint_id']
                or str(connection.settings_dict['NAME'])!=options['disposable_database']):
            raise CommandError('Configured database must match --disposable-database and a sprint is required.')
        if not settings.CAPABILITY_ASSESSMENT_ENABLED or (options['advice_cases'] and not settings.CAPABILITY_RECOMMENDATIONS_ENABLED):
            raise CommandError('Configured assessment/advice execution is disabled.')
        if not (settings.AI_API_KEY or settings.OPENAI_API_KEY):
            raise CommandError('No provider key is configured; no request was made.')
        from apps.extraction.services.ai_service import get_ai_service
        from apps.extraction.pricing import positive_token_prices
        from apps.scoring.capability.provider import MeteredService
        from apps.scoring.models import CapabilityRun,CapabilityExecution,CapabilityRunEvent
        from apps.sprints.models import Sprint
        service=get_ai_service()
        if not positive_token_prices(service.model):
            raise CommandError('Positive configured input and output prices are required; no request was made.')
        policy=bounded_policy()
        with transaction.atomic():
            sprint=Sprint.objects.select_for_update().get(pk=options['sprint_id'])
            if CapabilityExecution.objects.filter(sprint=sprint,status__in=['running','queued']).exists():
                raise CommandError('An execution is already active in this disposable sprint.')
            _,corpus=evidence_snapshot(sprint)
            current=prepare(plan,snapshot(sprint),corpus)
            inputs={'diagnostic_only':True,'execution_policy':policy,'probe_plan':current}
            run=CapabilityRun.objects.create(sprint=sprint,inputs=inputs,inputs_hash=digest(inputs))
            execution=CapabilityExecution.objects.create(run=run,sprint=sprint,status='running',
                idempotency_key='bounded-probe:'+str(run.pk),request_hash=digest(current))
        with output.open('x') as handle:
            json.dump({'diagnostic_only':True,'run_id':str(run.pk),'execution_completed':False,'status':'started'},handle)
        meter=None
        try:
            meter=MeteredService(service,execution)
            def checkpoint(case):
                CapabilityRunEvent.objects.create(run=run,state='partial',
                    payload={'kind':'bounded_probe_case','diagnostic_only':True,'case':case})
            result=execute(current,meter,advice_cases=options['advice_cases'],on_result=checkpoint)
            result['run_id']=str(run.pk)
        except Exception as exc:
            result={'diagnostic_only':True,'run_id':str(run.pk),'execution_completed':False,
                'stop_reason':type(exc).__name__,'inference':meter.metadata() if meter else None}
        execution.refresh_from_db()
        result['requests_reserved']=execution.requests_reserved;result['usd_reserved']=str(execution.usd_reserved)
        result['policy']=policy
        status='completed' if result['execution_completed'] else 'failed'
        execution.status=status;execution.save(update_fields=['status','heartbeat_at'])
        CapabilityRunEvent.objects.create(run=run,state=status,payload={'kind':'bounded_probe','diagnostic_only':True,'output_hash':digest(result)})
        with output.open('w') as handle:json.dump(result,handle,indent=2)
        self.stdout.write(f"Diagnostic {status}; reserved requests={execution.requests_reserved}, configured-price USD={execution.usd_reserved}. No assessment was published.")
