"""Depth results for an assessment run: levels, depth index, and the score with depth applied when decision 2 is
set to 'reserve'. Reads saved judgments; no model calls. Never changes the assessment's own reports.

    python manage.py depth_report export.json
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.scoring.capability.depth_service import DepthError, depth_report


class Command(BaseCommand):
    help = 'Depth results for an assessment export.'

    def add_arguments(self, parser):
        parser.add_argument('export')

    def handle(self, *args, **options):
        with open(options['export'], encoding='utf-8') as f:
            export = json.load(f)
        try:
            report = depth_report(export)
        except DepthError as exc:
            raise CommandError(str(exc))
        self.stdout.write(json.dumps(report, indent=1, ensure_ascii=False, default=str))
