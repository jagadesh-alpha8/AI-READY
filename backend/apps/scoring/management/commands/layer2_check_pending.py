"""Check the second layer's waiting answers for one run (skeleton; see capability/layer2.py).

    python manage.py layer2_check_pending RUN_ID                 # check every answer whose documents are extracted
    python manage.py layer2_check_pending RUN_ID --max-calls 10

Each depth answer is searched for in its documents and the run's corpus, then checked in one model call (none when
nothing was found). Additional evidence is routed and searched (no model call). These calls are unmetered: the API's
checks job is the metered path (second_layer_jobs.py).
"""
from django.core.management.base import BaseCommand

from apps.scoring.capability import depth
from apps.scoring.capability.layer2_service import check_additional, check_pending
from apps.scoring.models import AdditionalEvidence, CapabilityRun


class Command(BaseCommand):
    help = "Check a run's waiting second-layer answers and additional evidence."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--max-calls', type=int, default=60)

    def handle(self, *args, **options):
        run_ref = options['run_id']
        counts = check_pending(run_ref, depth.default_model(), max_calls=options['max_calls'])
        self.stdout.write(f"Answers checked: {counts['checked']}; waiting: {counts['waiting']}; "
                          f"model calls: {counts['model_calls']}.")
        run = CapabilityRun.objects.filter(pk=run_ref).first()
        if run is None:
            return
        done = 0
        for item in AdditionalEvidence.objects.filter(run_ref=run_ref, status=AdditionalEvidence.Status.PENDING):
            check_additional(item, run.inputs['rubric'])
            done += item.status == AdditionalEvidence.Status.CHECKED
        self.stdout.write(f'Additional evidence checked: {done}.')
