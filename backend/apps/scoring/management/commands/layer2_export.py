"""Export a run's second layer as it stands (no model calls): follow-up questions, answers with their checks,
depth judgments, additional evidence and second-layer jobs, for reviewing the questions offline.

    python manage.py layer2_export RUN_ID --out layer2-RUN_ID.json

Answers and notes can contain the institution's own words; treat the file like an assessment export.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict

from apps.scoring.models import (AdditionalEvidence, CapabilityRun, DepthJudgment, DepthQuestion, DepthResponse,
                                 SecondLayerEvent, SecondLayerJob)


def _rows(queryset):
    out = []
    for obj in queryset:
        row = model_to_dict(obj)
        for field in ('created_at', 'updated_at', 'checked_at', 'answered_at', 'started_at', 'finished_at'):
            if hasattr(obj, field):
                row[field] = getattr(obj, field)
        row['id'] = str(obj.pk)
        out.append(row)
    return out


def export(run_ref):
    questions = DepthQuestion.objects.filter(run_ref=run_ref).order_by('rank')
    return {'run_id': run_ref,
            'questions': _rows(questions),
            'responses': _rows(DepthResponse.objects.filter(question__run_ref=run_ref).order_by('question__rank')),
            'depth_judgments': _rows(DepthJudgment.objects.filter(run_ref=run_ref).order_by('condition_id')),
            'additional_evidence': _rows(AdditionalEvidence.objects.filter(run_ref=run_ref)),
            'jobs': _rows(SecondLayerJob.objects.filter(run_id=run_ref).order_by('created_at')),
            'events': _rows(SecondLayerEvent.objects.filter(job__run_id=run_ref).order_by('created_at'))}


class Command(BaseCommand):
    help = "Export a run's follow-up questions, answers, checks, depth judgments and jobs (no model calls)."

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--out', required=True)

    def handle(self, *args, **options):
        if not CapabilityRun.objects.filter(pk=options['run_id']).exists():
            raise CommandError('Run not found.')
        data = export(options['run_id'])
        with open(options['out'], 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=DjangoJSONEncoder, ensure_ascii=False, indent=1)
        self.stdout.write(f"{len(data['questions'])} questions, {len(data['responses'])} responses, "
                          f"{len(data['depth_judgments'])} depth judgments, {len(data['jobs'])} jobs.")
