import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.documents.models import Document
from apps.extraction.models import DocumentPage
from apps.institutions.models import Institution
from apps.scoring.capability.storage import evidence_snapshot
from apps.scoring.models import CapabilityRun
from apps.sprints.models import Sprint


class ExportSprintSourcesTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(name='VISTAS')
        self.sprint = Sprint.objects.create(institution=institution, mode=Sprint.SprintMode.VERIFIED_CRI)
        doc = Document.objects.create(sprint=self.sprint, original_filename='NAAC SSR.pdf', document_type='naac_ssr',
                                      status=Document.Status.PROCESSED, page_count=3)
        DocumentPage.objects.create(document=doc, page_number=1, text='6.2.3 Implementation of e-governance')
        DocumentPage.objects.create(document=doc, page_number=2, text='Response: ERP covers finance and admission')

    def test_writes_the_same_sources_an_assessment_freezes_without_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.json'
            call_command('export_sprint_sources', str(self.sprint.pk), output=str(target))
            data = json.loads(target.read_text(encoding='utf-8'))
        manifest, sources = evidence_snapshot(self.sprint)
        self.assertEqual(data['sources'], json.loads(json.dumps(sources)))
        self.assertEqual(data['coverage']['totals']['missing_rows'], 1)
        self.assertFalse(data['coverage']['complete'])
        self.assertEqual(CapabilityRun.objects.count(), 0)

    def test_refuses_existing_output_and_unknown_sprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'x.json'
            existing.write_text('{}')
            with self.assertRaises(CommandError):
                call_command('export_sprint_sources', str(self.sprint.pk), output=str(existing))
            with self.assertRaises(CommandError):
                call_command('export_sprint_sources', 'not-a-uuid', output=str(Path(tmp) / 'y.json'))
